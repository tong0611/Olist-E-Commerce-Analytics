"""Extract business days of Olist data from Postgres into the raw data lake.

    python -m ingestion.extract --date 2017-11-24
    python -m ingestion.extract --start 2017-01-01 --end 2017-01-31 --include-static

Lake layout (Hive-style partitions):
    raw/olist/<table>/dt=YYYY-MM-DD/<table>.parquet
    raw/_manifests/dt=YYYY-MM-DD/manifest.json      written last = success marker

File names are deterministic, so re-running a day overwrites it.
"""
from __future__ import annotations

import argparse
import json
import logging
import uuid
from collections.abc import Collection, Iterable
from datetime import UTC, date, datetime, time, timedelta

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from ingestion.config import Settings
from ingestion.dates import add_date_args, daterange, resolve_date_range
from ingestion.storage import Storage, get_storage
from ingestion.tables import TABLES, Mode, TableSpec

log = logging.getLogger(__name__)

DAILY = (Mode.INCREMENTAL, Mode.SNAPSHOT)


def table_key(table: str, business_date: date) -> str:
    return f"raw/olist/{table}/dt={business_date.isoformat()}/{table}.parquet"


def manifest_key(business_date: date) -> str:
    return f"raw/_manifests/dt={business_date.isoformat()}/manifest.json"


def read_table(engine: Engine, spec: TableSpec, business_date: date, schema: str) -> pd.DataFrame:
    start = datetime.combine(business_date, time.min)
    params = {"start": start, "end": start + timedelta(days=1)} if spec.mode is Mode.INCREMENTAL else {}
    with engine.connect() as conn:
        return pd.read_sql(text(spec.query.format(schema=schema)), conn, params=params)


def to_parquet(df: pd.DataFrame) -> bytes:
    # microsecond timestamps: Snowflake and Glue reject nanosecond precision
    return df.to_parquet(index=False, compression="snappy", coerce_timestamps="us", allow_truncated_timestamps=True)


def run_extract(
    business_date: date,
    engine: Engine,
    storage: Storage,
    schema: str,
    modes: Collection[Mode] = DAILY,
    tables: Iterable[TableSpec] = TABLES,
) -> dict:
    """Extract one business date; returns the manifest (also written to the lake)."""
    extracted_at = datetime.now(UTC).isoformat()
    batch_id = f"{business_date.isoformat()}_{uuid.uuid4().hex[:8]}"
    manifest = {"batch_id": batch_id, "business_date": business_date.isoformat(), "extracted_at": extracted_at,
                "tables": {}}

    for spec in (s for s in tables if s.mode in modes):
        df = read_table(engine, spec, business_date, schema)
        uri = None
        if len(df):  # empty days appear in the manifest but write no file
            lineage = df.assign(_batch_id=batch_id, _business_date=business_date.isoformat(),
                                _extracted_at=extracted_at)
            uri = storage.write_bytes(table_key(spec.name, business_date), to_parquet(lineage),
                                      "application/octet-stream")
        manifest["tables"][spec.name] = {"mode": spec.mode.value, "rows": len(df), "uri": uri}
        log.info("%-30s %-11s %8d rows", spec.name, spec.mode, len(df))

    storage.write_bytes(manifest_key(business_date), json.dumps(manifest, indent=2).encode(), "application/json")
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_date_args(p, p.add_mutually_exclusive_group(required=True))
    p.add_argument("--include-static", action="store_true", help="also extract static tables (geolocation)")
    return resolve_date_range(p, p.parse_args(argv))


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)
    settings = Settings.from_env()
    engine = create_engine(settings.sqlalchemy_url)
    storage = get_storage(settings)

    dates = list(daterange(args.start, args.end))
    for i, d in enumerate(dates):
        # The source keeps no history for snapshot and static tables, so a backfill
        # takes static tables once (first day) and snapshots once (last day).
        modes = {Mode.INCREMENTAL}
        if i == len(dates) - 1:
            modes.add(Mode.SNAPSHOT)
        if args.include_static and i == 0:
            modes.add(Mode.STATIC)
        log.info("=== business date %s -> %s ===", d, settings.lake_target)
        manifest = run_extract(d, engine, storage, settings.pg_schema, modes)
        rows = sum(t["rows"] for t in manifest["tables"].values())
        log.info("batch %s: %d rows across %d tables", manifest["batch_id"], rows, len(manifest["tables"]))


if __name__ == "__main__":
    main()
