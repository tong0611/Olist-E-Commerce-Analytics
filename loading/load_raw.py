"""Load raw Parquet from the S3 lake into Snowflake OLIST.RAW, then reconcile
loaded row counts against the extraction manifests.

    python -m loading.load_raw --bootstrap                 # stage, RAW and AUDIT tables (idempotent)
    python -m loading.load_raw --date 2017-11-24
    python -m loading.load_raw --start 2016-09-04 --end 2018-10-17

* RAW tables hold the whole record as VARIANT plus file metadata; typing happens
  in dbt, so source schema changes never break a load.
* The manifests list exactly which files exist, so each table gets one
  `COPY ... FILES = (...)` for the whole date range.
* COPY's load metadata makes re-runs no-ops. A re-extracted file has a new ETag
  and is loaded again; dbt staging keeps the latest version.
* Rows in RAW for each manifest's batch_id must equal the manifest's count.
  Every check goes to AUDIT.LOAD_RECONCILIATION and a mismatch fails the run.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

from ingestion.dates import add_date_args, daterange, resolve_date_range
from ingestion.tables import TABLES
from loading.snowflake_client import SnowflakeSettings, connect

log = logging.getLogger(__name__)

STAGE = "RAW.LAKE_STAGE"
MAX_FILES_PER_COPY = 1000  # Snowflake's limit for FILES = (...)


def bootstrap_statements(lake_bucket: str) -> list[str]:
    if not lake_bucket:
        raise ValueError("S3_BUCKET must be set to create the stage")
    raw_tables = [
        f"""CREATE TABLE IF NOT EXISTS RAW.{spec.name.upper()} (
              RAW_DATA VARIANT, _SOURCE_FILE STRING, _FILE_ROW_NUMBER NUMBER,
              _FILE_LAST_MODIFIED TIMESTAMP_NTZ, _LOADED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP())"""
        for spec in TABLES
    ]
    return [
        "CREATE FILE FORMAT IF NOT EXISTS RAW.FF_PARQUET TYPE = PARQUET USE_LOGICAL_TYPE = TRUE",
        "CREATE FILE FORMAT IF NOT EXISTS RAW.FF_JSON TYPE = JSON",
        f"""CREATE STAGE IF NOT EXISTS {STAGE} URL = 's3://{lake_bucket}/raw/'
              STORAGE_INTEGRATION = OLIST_S3_LAKE FILE_FORMAT = RAW.FF_PARQUET""",
        *raw_tables,
        """CREATE TABLE IF NOT EXISTS AUDIT.COPY_HISTORY (
             BUSINESS_DATE DATE, TABLE_NAME STRING, FILE STRING, STATUS STRING, ROWS_PARSED NUMBER,
             ROWS_LOADED NUMBER, FIRST_ERROR STRING, COPIED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP())""",
        """CREATE TABLE IF NOT EXISTS AUDIT.LOAD_RECONCILIATION (
             BUSINESS_DATE DATE, BATCH_ID STRING, TABLE_NAME STRING, EXPECTED_ROWS NUMBER,
             LOADED_ROWS NUMBER, STATUS STRING, CHECKED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP())""",
    ]


def relative_file(table: str, business_date: date) -> str:
    """Path under @STAGE/olist/<table>/ (matches ingestion.extract.table_key)."""
    return f"dt={business_date.isoformat()}/{table}.parquet"


def business_date_from_path(path: str | None) -> str | None:
    """'s3://.../orders/dt=2017-11-24/orders.parquet' -> '2017-11-24'"""
    m = re.search(r"dt=(\d{4}-\d{2}-\d{2})", path or "")
    return m and m.group(1)


def copy_statement(table: str, files: list[str]) -> str:
    file_list = ", ".join(f"'{f}'" for f in files)
    return f"""
        COPY INTO RAW.{table.upper()} (RAW_DATA, _SOURCE_FILE, _FILE_ROW_NUMBER, _FILE_LAST_MODIFIED)
        FROM (SELECT $1, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, METADATA$FILE_LAST_MODIFIED
              FROM @{STAGE}/olist/{table}/)
        FILES = ({file_list})
        ON_ERROR = ABORT_STATEMENT"""


@dataclass
class CopyResult:
    file: str
    status: str
    rows_parsed: int
    rows_loaded: int
    first_error: str | None


def parse_copy_results(description, rows) -> list[CopyResult]:
    """One row per file, or a single 'status' row when nothing was new."""
    cols = [d[0].lower() for d in description]
    if "file" not in cols:
        return []
    records = (dict(zip(cols, row, strict=True)) for row in rows)
    return [CopyResult(r["file"], r["status"], r.get("rows_parsed") or 0, r.get("rows_loaded") or 0,
                       r.get("first_error")) for r in records]


@dataclass
class Reconciliation:
    business_date: date
    batch_id: str
    table: str
    expected: int
    loaded: int

    @property
    def status(self) -> str:
        return "MATCH" if self.expected == self.loaded else "MISMATCH"


def tables_to_reconcile(manifest: dict) -> list[tuple[str, int]]:
    """(table, rows) for every table the manifest says has data."""
    return [(name, t["rows"]) for name, t in manifest["tables"].items() if t["rows"] > 0]


def files_by_table(manifests: dict[date, dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for d, m in sorted(manifests.items()):
        for name, _ in tables_to_reconcile(m):
            out[name].append(relative_file(name, d))
    return dict(out)


def reconcile(manifests: dict[date, dict], counts: dict[str, dict[str, int]]) -> list[Reconciliation]:
    """counts: table -> {batch_id: rows in RAW}"""
    return [
        Reconciliation(d, m["batch_id"], name, expected, counts.get(name, {}).get(m["batch_id"], 0))
        for d, m in sorted(manifests.items())
        for name, expected in tables_to_reconcile(m)
    ]


def chunks(items: list, size: int) -> Iterator[list]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def read_manifests(cur, start: date, end: date) -> dict[date, dict]:
    cur.execute(f"SELECT $1 FROM @{STAGE}/_manifests/ (FILE_FORMAT => 'RAW.FF_JSON', PATTERN => '.*manifest[.]json')")
    manifests = (json.loads(raw) for (raw,) in cur.fetchall())
    return {d: m for m in manifests if start <= (d := date.fromisoformat(m["business_date"])) <= end}


def load_range(conn, start: date, end: date) -> list[Reconciliation]:
    cur = conn.cursor()
    manifests = read_manifests(cur, start, end)
    missing = [d for d in daterange(start, end) if d not in manifests]
    if missing:
        raise RuntimeError(f"{len(missing)} date(s) have no manifest (extraction not finished), e.g. {missing[:3]}")
    log.info("found %d manifest(s) for %s .. %s", len(manifests), start, end)

    files = files_by_table(manifests)
    for name, table_files in files.items():
        results: list[CopyResult] = []
        for batch in chunks(table_files, MAX_FILES_PER_COPY):
            cur.execute(copy_statement(name, batch))
            results += parse_copy_results(cur.description, cur.fetchall())
        if results:
            cur.executemany(
                "INSERT INTO AUDIT.COPY_HISTORY "
                "(BUSINESS_DATE, TABLE_NAME, FILE, STATUS, ROWS_PARSED, ROWS_LOADED, FIRST_ERROR) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                [(business_date_from_path(r.file), name, r.file, r.status, r.rows_parsed, r.rows_loaded,
                  r.first_error) for r in results],
            )
        log.info("%-30s %4d file(s), %4d newly loaded, %9d rows", name, len(table_files),
                 sum(r.status == "LOADED" for r in results), sum(r.rows_loaded for r in results))

    counts = {}
    for name in files:
        cur.execute(f"SELECT RAW_DATA:_batch_id::STRING, COUNT(*) FROM RAW.{name.upper()} GROUP BY 1")
        counts[name] = dict(cur.fetchall())

    checks = reconcile(manifests, counts)
    cur.executemany(
        "INSERT INTO AUDIT.LOAD_RECONCILIATION "
        "(BUSINESS_DATE, BATCH_ID, TABLE_NAME, EXPECTED_ROWS, LOADED_ROWS, STATUS) VALUES (%s, %s, %s, %s, %s, %s)",
        [(c.business_date.isoformat(), c.batch_id, c.table, c.expected, c.loaded, c.status) for c in checks],
    )
    return checks


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--bootstrap", action="store_true", help="create file formats, stage, RAW and AUDIT tables")
    add_date_args(p, group)
    return resolve_date_range(p, p.parse_args(argv))


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("snowflake").setLevel(logging.ERROR)
    args = parse_args(argv)
    cfg = SnowflakeSettings.loader_from_env()

    with connect(cfg, query_tag="olist-pipeline:loader") as conn:
        if args.bootstrap:
            for stmt in bootstrap_statements(cfg.lake_bucket):
                conn.cursor().execute(stmt)
            log.info("bootstrap complete: stage %s and %d RAW tables", STAGE, len(TABLES))
            return

        checks = load_range(conn, args.start, args.end)
        failures = [c for c in checks if c.status != "MATCH"]
        for c in failures:
            log.error("MISMATCH %s %-28s expected %8d loaded %8d", c.business_date, c.table, c.expected, c.loaded)
        if failures:
            raise SystemExit(f"Reconciliation failed for {len(failures)} of {len(checks)} table-day checks")
        log.info("reconciliation passed: %d table-day checks, %d rows", len(checks), sum(c.loaded for c in checks))


if __name__ == "__main__":
    main()
