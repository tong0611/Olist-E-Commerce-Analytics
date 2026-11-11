"""Export the dbt MARTS tables from Snowflake to CSV for Tableau Public.

Tableau Public can't connect to Snowflake, so the last pipeline step
"publishes" the marts as files. Run after `dbt build` succeeds.

    python -m publishing.export_marts                  # -> exports/
    python -m publishing.export_marts --out-dir /tmp/x

How: each table is UNLOADED inside Snowflake (`COPY INTO @~` -> one gzipped
CSV in the service user's stage), then downloaded with a single GET and
decompressed. Fetching result sets row-by-row through the client is far
slower (many small result chunks); server-side unload is the standard way
to move data out of a warehouse.

Output:
    exports/<table>.csv          lower-case headers, ISO dates, NULL = empty
    exports/_manifest.json       row counts, columns and export time per file

Files are swapped in atomically, and the row count in every CSV is checked
against the table in Snowflake.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import logging
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, TypeVar

from loading.snowflake_client import SnowflakeSettings, connect

log = logging.getLogger("publishing.export_marts")
T = TypeVar("T")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STAGE_DIR = "@~/olist_exports"

# What each dashboard uses:
#   Revenue overview      -> mart_revenue_monthly, fct_orders
#   Customers & retention -> dim_customers, mart_customer_cohorts
#   Products              -> mart_product_performance, fct_order_items, dim_products, dim_sellers
MARTS = [
    "fct_orders",
    "fct_order_items",
    "dim_customers",
    "dim_products",
    "dim_sellers",
    "dim_date",
    "mart_revenue_monthly",
    "mart_customer_cohorts",
    "mart_product_performance",
]


def unload_statement(table: str, columns: list[str]) -> str:
    # quoted lower-case aliases become the CSV header
    select_list = ", ".join(f'{c} AS "{c.lower()}"' for c in columns)
    return f"""
        COPY INTO {STAGE_DIR}/{table}.csv.gz
        FROM (SELECT {select_list} FROM MARTS.{table.upper()})
        FILE_FORMAT = (
            TYPE = CSV
            COMPRESSION = GZIP
            FIELD_OPTIONALLY_ENCLOSED_BY = '"'
            NULL_IF = ()          -- NULL -> bare empty field (not "")
            DATE_FORMAT = 'YYYY-MM-DD'
            TIMESTAMP_FORMAT = 'YYYY-MM-DD HH24:MI:SS'
        )
        HEADER = TRUE
        SINGLE = TRUE
        OVERWRITE = TRUE
        MAX_FILE_SIZE = 1073741824"""


def get_statement(table: str, local_dir: Path) -> str:
    # quoted file URI: the project path contains a space
    return f"GET {STAGE_DIR}/{table}.csv.gz 'file://{local_dir.as_posix()}/'"


def with_retries(fn: Callable[[], T], what: str, attempts: int = 4, base_delay: float = 2.0,
                 sleep: Callable[[float], None] = time.sleep) -> T:
    """Retry transient failures (e.g. a stalled download from Snowflake's
    result storage) with exponential backoff: 2s, 4s, 8s."""
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # connector raises OperationalError for network stalls
            if attempt == attempts:
                raise
            delay = base_delay * 2 ** (attempt - 1)
            log.warning("%s failed (attempt %d/%d): %s - retrying in %.0fs", what, attempt, attempts, exc, delay)
            sleep(delay)
    raise AssertionError("unreachable")


def count_csv_rows(path: Path) -> int:
    """Data rows (excluding header), honouring quoted newlines."""
    with path.open(newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.reader(f)) - 1


def decompress_into_place(gz_path: Path, dest: Path) -> None:
    tmp = dest.with_suffix(".csv.tmp")
    with gzip.open(gz_path, "rb") as src, tmp.open("wb") as out:
        shutil.copyfileobj(src, out)
    tmp.replace(dest)  # atomic: Tableau never sees a half-written file


def export_table(conn, table: str, out_dir: Path, download_dir: Path) -> dict:
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM MARTS.{table.upper()} LIMIT 0")
    columns = [d[0] for d in cur.description]
    cur.execute(f"SELECT COUNT(*) FROM MARTS.{table.upper()}")
    expected = cur.fetchone()[0]

    cur.execute(unload_statement(table, columns))
    with_retries(lambda: cur.execute(get_statement(table, download_dir)), f"GET {table}")

    dest = out_dir / f"{table}.csv"
    decompress_into_place(download_dir / f"{table}.csv.gz", dest)
    written = count_csv_rows(dest)
    if written != expected:
        raise RuntimeError(f"{table}: CSV has {written} rows but Snowflake has {expected}")
    return {"rows": written, "columns": [c.lower() for c in columns], "bytes": dest.stat().st_size}


def run_export(conn, out_dir: Path, tables: list[str] = MARTS) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"exported_at": datetime.now(timezone.utc).isoformat(), "tables": {}}
    with tempfile.TemporaryDirectory(prefix="olist_export_") as tmp:
        for t in tables:
            info = export_table(conn, t, out_dir, Path(tmp))
            manifest["tables"][t] = info
            log.info("%-28s %8d rows  %2d cols  %6.1f MB", t, info["rows"], len(info["columns"]), info["bytes"] / 1e6)
    (out_dir / "_manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main(argv: Optional[list[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("snowflake").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-dir", type=Path, default=PROJECT_ROOT / "exports")
    args = p.parse_args(argv)

    with connect(SnowflakeSettings.transformer_from_env(), query_tag="olist-pipeline:export") as conn:
        m = run_export(conn, args.out_dir.resolve())
    log.info("exported %d tables to %s", len(m["tables"]), args.out_dir)


if __name__ == "__main__":
    main()
