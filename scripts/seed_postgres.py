"""Load the Olist Kaggle CSVs into the Postgres source database.

Usage:
    python scripts/seed_postgres.py                 # uses data/source/
    python scripts/seed_postgres.py --csv-dir path/to/csvs

Uses Postgres COPY (fast bulk load). Re-running is safe: every table is
truncated before it is loaded.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ingestion.config import Settings  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = PROJECT_ROOT / "sql" / "source" / "schema.sql"

CSV_TO_TABLE = {
    "olist_customers_dataset.csv": "customers",
    "olist_orders_dataset.csv": "orders",
    "olist_order_items_dataset.csv": "order_items",
    "olist_order_payments_dataset.csv": "order_payments",
    "olist_order_reviews_dataset.csv": "order_reviews",
    "olist_products_dataset.csv": "products",
    "olist_sellers_dataset.csv": "sellers",
    "product_category_name_translation.csv": "product_category_translation",
    "olist_geolocation_dataset.csv": "geolocation",
}


def read_header(path: Path) -> list[str]:
    # utf-8-sig strips the BOM some of the Kaggle files start with
    with path.open(encoding="utf-8-sig") as f:
        return [c.strip().strip('"') for c in f.readline().strip().split(",")]


def load_csv(cur, path: Path, schema: str, table: str) -> int:
    columns = read_header(path)
    cur.execute(sql.SQL("TRUNCATE {}.{}").format(sql.Identifier(schema), sql.Identifier(table)))
    copy_stmt = sql.SQL("COPY {}.{} ({}) FROM STDIN WITH (FORMAT csv, HEADER true)").format(
        sql.Identifier(schema),
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(c) for c in columns),
    )
    with path.open(encoding="utf-8-sig") as f:
        cur.copy_expert(copy_stmt.as_string(cur), f)
    cur.execute(sql.SQL("SELECT COUNT(*) FROM {}.{}").format(sql.Identifier(schema), sql.Identifier(table)))
    return cur.fetchone()[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv-dir", type=Path, default=PROJECT_ROOT / "data" / "source")
    args = parser.parse_args()

    missing = [name for name in CSV_TO_TABLE if not (args.csv_dir / name).exists()]
    if missing:
        sys.exit(f"Missing CSV files in {args.csv_dir}: {missing}\nRun `make download` first.")

    settings = Settings.from_env()
    conn = psycopg2.connect(
        host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_db,
        user=settings.pg_user, password=settings.pg_password,
    )
    try:
        with conn, conn.cursor() as cur:
            cur.execute(SCHEMA_FILE.read_text())
            for csv_name, table in CSV_TO_TABLE.items():
                rows = load_csv(cur, args.csv_dir / csv_name, settings.pg_schema, table)
                print(f"  loaded {table:<30} {rows:>10,} rows")
        print("Source database seeded.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
