"""Export the dbt marts from Snowflake to CSV, for tools without a Snowflake connector.

    python -m publishing.export_marts                  # -> exports/
    python -m publishing.export_marts --out-dir /tmp/x

Each table is unloaded inside Snowflake (`COPY INTO @~`, one gzipped CSV), downloaded
with a single GET and decompressed. That is far faster than fetching rows through the
client. Files are swapped in atomically and every CSV's row count is checked against
the table. Writes exports/<table>.csv and exports/_manifest.json.
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
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from loading.snowflake_client import SnowflakeSettings, connect

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STAGE_DIR = "@~/olist_exports"

MARTS = [
    "fct_orders", "fct_order_items", "dim_customers", "dim_products", "dim_sellers", "dim_date",
    "mart_revenue_monthly", "mart_customer_cohorts", "mart_product_performance",
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


def with_retries[T](fn: Callable[[], T], what: str, attempts: int = 4, base_delay: float = 2.0,
                 sleep: Callable[[float], None] = time.sleep) -> T:
    """Retry transient failures (e.g. a stalled GET) with exponential backoff: 2s, 4s, 8s."""
    for attempt in range(1, attempts):
        try:
            return fn()
        except Exception as exc:  # the connector raises OperationalError on network stalls
            delay = base_delay * 2 ** (attempt - 1)
            log.warning("%s failed (attempt %d/%d): %s; retrying in %.0fs", what, attempt, attempts, exc, delay)
            sleep(delay)
    return fn()


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
    manifest = {"exported_at": datetime.now(UTC).isoformat(), "tables": {}}
    with tempfile.TemporaryDirectory(prefix="olist_export_") as tmp:
        for t in tables:
            info = export_table(conn, t, out_dir, Path(tmp))
            manifest["tables"][t] = info
            log.info("%-28s %8d rows  %2d cols  %6.1f MB", t, info["rows"], len(info["columns"]), info["bytes"] / 1e6)
    (out_dir / "_manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("snowflake").setLevel(logging.ERROR)
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-dir", type=Path, default=PROJECT_ROOT / "exports")
    args = p.parse_args(argv)

    with connect(SnowflakeSettings.transformer_from_env(), query_tag="olist-pipeline:export") as conn:
        m = run_export(conn, args.out_dir.resolve())
    log.info("exported %d tables to %s", len(m["tables"]), args.out_dir)


if __name__ == "__main__":
    main()
