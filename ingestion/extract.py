"""Extract one business day of Olist data from Postgres into the raw data lake.

Examples:
    python -m ingestion.extract --date 2017-11-24
    python -m ingestion.extract --date 2017-01-05 --include-static
    python -m ingestion.extract --start 2017-01-01 --end 2017-01-31   # backfill

Lake layout (Hive-style partitions, which Glue/Athena/Snowflake understand):
    raw/olist/<table>/dt=YYYY-MM-DD/<table>.parquet
    raw/_manifests/dt=YYYY-MM-DD/manifest.json      <- written LAST = success marker

File names are deterministic, so re-running a day overwrites it (idempotent).
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from ingestion.config import Settings
from ingestion.storage import Storage, get_storage
from ingestion.tables import INCREMENTAL, STATIC, TABLES, TableSpec

log = logging.getLogger("ingestion.extract")

RAW_PREFIX = "raw/olist"
MANIFEST_PREFIX = "raw/_manifests"


def table_key(table: str, business_date: date) -> str:
    return f"{RAW_PREFIX}/{table}/dt={business_date.isoformat()}/{table}.parquet"


def manifest_key(business_date: date) -> str:
    return f"{MANIFEST_PREFIX}/dt={business_date.isoformat()}/manifest.json"


def extract_table(engine: Engine, spec: TableSpec, business_date: date, schema: str) -> pd.DataFrame:
    start = datetime.combine(business_date, time.min)
    params = {"start": start, "end": start + timedelta(days=1)} if spec.mode == INCREMENTAL else {}
    with engine.connect() as conn:
        return pd.read_sql(text(spec.query.format(schema=schema)), conn, params=params)


def add_metadata(df: pd.DataFrame, business_date: date, batch_id: str, extracted_at: datetime) -> pd.DataFrame:
    """Lineage columns: which run produced each row, and when."""
    out = df.copy()
    out["_batch_id"] = batch_id
    out["_business_date"] = business_date.isoformat()
    out["_extracted_at"] = extracted_at.isoformat()
    return out


def to_parquet_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    # microsecond timestamps: avoids nanosecond-precision issues in Snowflake/Glue
    pq.write_table(
        pa.Table.from_pandas(df, preserve_index=False),
        buf,
        compression="snappy",
        coerce_timestamps="us",
        allow_truncated_timestamps=True,
    )
    return buf.getvalue()


def run_extract(
    business_date: date,
    engine: Engine,
    storage: Storage,
    schema: str,
    include_static: bool = False,
    tables: Iterable[TableSpec] = TABLES,
) -> dict:
    extracted_at = datetime.now(timezone.utc)
    batch_id = f"{business_date.isoformat()}_{uuid.uuid4().hex[:8]}"
    manifest: dict = {
        "batch_id": batch_id,
        "business_date": business_date.isoformat(),
        "extracted_at": extracted_at.isoformat(),
        "tables": {},
    }

    for spec in tables:
        if spec.mode == STATIC and not include_static:
            continue
        df = extract_table(engine, spec, business_date, schema)
        entry: dict = {"mode": spec.mode, "rows": int(len(df)), "uri": None}
        if len(df):  # empty days are recorded in the manifest but produce no file
            df = add_metadata(df, business_date, batch_id, extracted_at)
            entry["uri"] = storage.write_bytes(
                table_key(spec.name, business_date), to_parquet_bytes(df), "application/octet-stream"
            )
        manifest["tables"][spec.name] = entry
        log.info("%-30s %-11s %8d rows", spec.name, spec.mode, entry["rows"])

    storage.write_bytes(
        manifest_key(business_date), json.dumps(manifest, indent=2).encode(), "application/json"
    )
    return manifest


def daterange(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--date", type=date.fromisoformat, help="single business date (YYYY-MM-DD)")
    g.add_argument("--start", type=date.fromisoformat, help="backfill start date (inclusive)")
    p.add_argument("--end", type=date.fromisoformat, help="backfill end date (inclusive)")
    p.add_argument("--include-static", action="store_true", help="also extract static tables (geolocation)")
    args = p.parse_args(argv)
    if args.start and not args.end:
        p.error("--start requires --end")
    if args.start and args.end < args.start:
        p.error("--end must not be before --start")
    return args


def main(argv: Optional[list[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)
    settings = Settings.from_env()
    engine = create_engine(settings.sqlalchemy_url)
    storage = get_storage(settings)

    dates = [args.date] if args.date else list(daterange(args.start, args.end))
    for i, d in enumerate(dates):
        log.info("=== extracting business date %s -> %s ===", d, settings.lake_target)
        # static tables only need to be pulled once per run
        manifest = run_extract(d, engine, storage, settings.pg_schema, include_static=args.include_static and i == 0)
        total = sum(t["rows"] for t in manifest["tables"].values())
        log.info("batch %s done: %d rows across %d tables", manifest["batch_id"], total, len(manifest["tables"]))


if __name__ == "__main__":
    main()
