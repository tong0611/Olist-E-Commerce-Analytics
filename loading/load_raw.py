"""Load raw Parquet files from the S3 lake into Snowflake OLIST.RAW, then
reconcile loaded row counts against the extraction manifest.

Examples:
    python -m loading.load_raw --bootstrap                 # create stage / tables (idempotent)
    python -m loading.load_raw --date 2017-11-24
    python -m loading.load_raw --start 2017-11-20 --end 2017-11-26

Design
------
* ELT: every RAW table is (RAW_DATA VARIANT + file metadata). Typing and
  cleaning happen in dbt staging, so source schema drift never breaks a load.
* COPY INTO keeps 64 days of load metadata per file, so re-running a date
  does not duplicate data. A re-extracted (overwritten) file has a new ETag
  and IS reloaded -> dbt staging dedupes on the latest file version.
* Reconciliation: rows in RAW for the manifest's batch_id must equal the
  manifest's row count, per table. Any mismatch fails the run and is logged
  to AUDIT.LOAD_RECONCILIATION.
"""
from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Optional

from ingestion.tables import TABLES
from loading.snowflake_client import SnowflakeSettings, connect

log = logging.getLogger("loading.load_raw")

STAGE = "RAW.LAKE_STAGE"


def bootstrap_statements(lake_bucket: str) -> list[str]:
    if not lake_bucket:
        raise ValueError("S3_BUCKET must be set to create the stage")
    stmts = [
        "CREATE FILE FORMAT IF NOT EXISTS RAW.FF_PARQUET TYPE = PARQUET USE_LOGICAL_TYPE = TRUE",
        "CREATE FILE FORMAT IF NOT EXISTS RAW.FF_JSON TYPE = JSON",
        f"""CREATE STAGE IF NOT EXISTS {STAGE}
              URL = 's3://{lake_bucket}/raw/'
              STORAGE_INTEGRATION = OLIST_S3_LAKE
              FILE_FORMAT = RAW.FF_PARQUET""",
    ]
    for spec in TABLES:
        stmts.append(
            f"""CREATE TABLE IF NOT EXISTS RAW.{spec.name.upper()} (
                  RAW_DATA            VARIANT,
                  _SOURCE_FILE        STRING,
                  _FILE_ROW_NUMBER    NUMBER,
                  _FILE_LAST_MODIFIED TIMESTAMP_NTZ,
                  _LOADED_AT          TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
                )"""
        )
    stmts += [
        """CREATE TABLE IF NOT EXISTS AUDIT.COPY_HISTORY (
             BUSINESS_DATE DATE, TABLE_NAME STRING, FILE STRING, STATUS STRING,
             ROWS_PARSED NUMBER, ROWS_LOADED NUMBER, FIRST_ERROR STRING,
             COPIED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP())""",
        """CREATE TABLE IF NOT EXISTS AUDIT.LOAD_RECONCILIATION (
             BUSINESS_DATE DATE, BATCH_ID STRING, TABLE_NAME STRING,
             EXPECTED_ROWS NUMBER, LOADED_ROWS NUMBER, STATUS STRING,
             CHECKED_AT TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP())""",
    ]
    return stmts


def copy_statement(table: str, business_date: date) -> str:
    return f"""
        COPY INTO RAW.{table.upper()} (RAW_DATA, _SOURCE_FILE, _FILE_ROW_NUMBER, _FILE_LAST_MODIFIED)
        FROM (
            SELECT $1, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER, METADATA$FILE_LAST_MODIFIED
            FROM @{STAGE}/olist/{table}/dt={business_date.isoformat()}/
        )
        PATTERN = '.*[.]parquet'
        ON_ERROR = ABORT_STATEMENT"""


@dataclass
class CopyResult:
    file: Optional[str]
    status: str
    rows_parsed: int = 0
    rows_loaded: int = 0
    first_error: Optional[str] = None


def parse_copy_results(description, rows) -> list[CopyResult]:
    """COPY returns one row per file, or a single 'status' row when there was
    nothing new to load ("Copy executed with 0 files processed.")."""
    cols = [d[0].lower() for d in description]
    if "file" not in cols:
        return []
    out = []
    for row in rows:
        r = dict(zip(cols, row))
        out.append(CopyResult(r["file"], r["status"], r.get("rows_parsed") or 0,
                              r.get("rows_loaded") or 0, r.get("first_error")))
    return out


@dataclass
class Reconciliation:
    table: str
    expected: int
    loaded: int

    @property
    def status(self) -> str:
        return "MATCH" if self.expected == self.loaded else "MISMATCH"


def tables_to_reconcile(manifest: dict) -> list[tuple[str, int]]:
    """Tables the manifest says have data for this batch."""
    return [(name, t["rows"]) for name, t in manifest["tables"].items() if t["rows"] > 0]


def read_manifest(cur, business_date: date) -> Optional[dict]:
    cur.execute(
        f"SELECT $1 FROM @{STAGE}/_manifests/dt={business_date.isoformat()}/manifest.json "
        "(FILE_FORMAT => 'RAW.FF_JSON')"
    )
    row = cur.fetchone()
    return json.loads(row[0]) if row else None


def load_date(conn, business_date: date) -> list[Reconciliation]:
    cur = conn.cursor()
    manifest = read_manifest(cur, business_date)
    if manifest is None:
        raise RuntimeError(f"No manifest for {business_date}: extraction did not finish for that date")

    for name, _ in tables_to_reconcile(manifest):
        cur.execute(copy_statement(name, business_date))
        results = parse_copy_results(cur.description, cur.fetchall())
        if not results:
            log.info("%-30s no new files (already loaded)", name)
        for r in results:
            log.info("%-30s %-8s %8d rows  %s", name, r.status, r.rows_loaded, r.file)
            cur.execute(
                "INSERT INTO AUDIT.COPY_HISTORY (BUSINESS_DATE, TABLE_NAME, FILE, STATUS, ROWS_PARSED, ROWS_LOADED, FIRST_ERROR) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (business_date.isoformat(), name, r.file, r.status, r.rows_parsed, r.rows_loaded, r.first_error),
            )

    checks = []
    for name, expected in tables_to_reconcile(manifest):
        cur.execute(
            f"SELECT COUNT(*) FROM RAW.{name.upper()} WHERE RAW_DATA:_batch_id::STRING = %s",
            (manifest["batch_id"],),
        )
        rec = Reconciliation(name, expected, cur.fetchone()[0])
        checks.append(rec)
        cur.execute(
            "INSERT INTO AUDIT.LOAD_RECONCILIATION (BUSINESS_DATE, BATCH_ID, TABLE_NAME, EXPECTED_ROWS, LOADED_ROWS, STATUS) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (business_date.isoformat(), manifest["batch_id"], name, rec.expected, rec.loaded, rec.status),
        )
    return checks


def daterange(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--bootstrap", action="store_true", help="create file formats, stage, RAW/AUDIT tables")
    g.add_argument("--date", type=date.fromisoformat)
    g.add_argument("--start", type=date.fromisoformat)
    p.add_argument("--end", type=date.fromisoformat)
    args = p.parse_args(argv)
    if args.start and (not args.end or args.end < args.start):
        p.error("--start needs an --end on or after it")
    return args


def main(argv: Optional[list[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("snowflake").setLevel(logging.WARNING)
    args = parse_args(argv)
    cfg = SnowflakeSettings.loader_from_env()

    with connect(cfg) as conn:
        if args.bootstrap:
            cur = conn.cursor()
            for stmt in bootstrap_statements(cfg.lake_bucket):
                cur.execute(stmt)
            log.info("bootstrap complete: stage %s and %d RAW tables ready", STAGE, len(TABLES))
            return

        dates = [args.date] if args.date else list(daterange(args.start, args.end))
        failures = []
        for d in dates:
            log.info("=== loading business date %s ===", d)
            for rec in load_date(conn, d):
                log.info("reconcile %-30s expected %8d loaded %8d  %s", rec.table, rec.expected, rec.loaded, rec.status)
                if rec.status != "MATCH":
                    failures.append((d, rec))
        if failures:
            raise SystemExit(f"Reconciliation failed for {len(failures)} table-days: "
                             + ", ".join(f"{d}:{r.table}" for d, r in failures))
        log.info("all %d date(s) loaded and reconciled", len(dates))


if __name__ == "__main__":
    main()
