"""Unit tests for the extractor, run against an in-memory SQLite database
that mimics the Postgres source schema (no Docker needed)."""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from ingestion.extract import manifest_key, parse_args, run_extract, table_key
from ingestion.storage import LocalStorage
from ingestion.tables import TABLES

DAY = date(2017, 11, 24)


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE orders (order_id TEXT, customer_id TEXT, order_status TEXT, order_purchase_timestamp TIMESTAMP)"))
        c.execute(text("CREATE TABLE order_items (order_id TEXT, order_item_id INT, product_id TEXT, seller_id TEXT, price REAL)"))
        c.execute(text("CREATE TABLE order_payments (order_id TEXT, payment_sequential INT, payment_type TEXT, payment_value REAL)"))
        c.execute(text("CREATE TABLE customers (customer_id TEXT, customer_unique_id TEXT, customer_state TEXT)"))
        c.execute(text("CREATE TABLE order_reviews (review_id TEXT, order_id TEXT, review_score INT, review_creation_date TIMESTAMP)"))
        c.execute(text("CREATE TABLE products (product_id TEXT, product_category_name TEXT)"))
        c.execute(text("CREATE TABLE sellers (seller_id TEXT, seller_state TEXT)"))
        c.execute(text("CREATE TABLE product_category_translation (product_category_name TEXT, product_category_name_english TEXT)"))
        c.execute(text("CREATE TABLE geolocation (geolocation_zip_code_prefix TEXT, geolocation_lat REAL)"))

        c.execute(text("""INSERT INTO orders VALUES
            ('o1','c1','delivered','2017-11-23 23:59:59'),   -- day before
            ('o2','c2','delivered','2017-11-24 00:00:00'),   -- window start (included)
            ('o3','c3','shipped',  '2017-11-24 18:30:00'),
            ('o4','c4','delivered','2017-11-25 00:00:00')    -- window end (excluded)"""))
        c.execute(text("""INSERT INTO order_items VALUES
            ('o1',1,'p1','s1',10.0),('o2',1,'p1','s1',20.0),('o2',2,'p2','s1',5.0),('o3',1,'p2','s1',7.5)"""))
        c.execute(text("INSERT INTO order_payments VALUES ('o2',1,'credit_card',25.0),('o3',1,'boleto',7.5),('o4',1,'voucher',1.0)"))
        c.execute(text("INSERT INTO customers VALUES ('c1','u1','SP'),('c2','u2','RJ'),('c3','u1','SP'),('c4','u3','MG')"))
        c.execute(text("""INSERT INTO order_reviews VALUES
            ('r1','o1',5,'2017-11-24 00:00:00'),('r2','o0',3,'2017-11-20 00:00:00')"""))
        c.execute(text("INSERT INTO products VALUES ('p1','beleza_saude'),('p2','esporte_lazer')"))
        c.execute(text("INSERT INTO sellers VALUES ('s1','SP')"))
        c.execute(text("INSERT INTO product_category_translation VALUES ('beleza_saude','health_beauty')"))
        c.execute(text("INSERT INTO geolocation VALUES ('01037',-23.5)"))
    return eng


def test_incremental_window_is_half_open(engine, tmp_path):
    m = run_extract(DAY, engine, LocalStorage(str(tmp_path)), schema="main")
    t = m["tables"]
    assert t["orders"]["rows"] == 2          # o2, o3
    assert t["order_items"]["rows"] == 3     # items of o2 + o3
    assert t["order_payments"]["rows"] == 2
    assert t["customers"]["rows"] == 2       # c2, c3
    assert t["order_reviews"]["rows"] == 1   # r1 (late-arriving review for yesterday's order)
    assert t["products"]["rows"] == 2        # snapshot = full table
    assert "geolocation" not in t            # static skipped by default

    orders = pd.read_parquet(tmp_path / table_key("orders", DAY))
    assert sorted(orders["order_id"]) == ["o2", "o3"]


def test_metadata_columns_and_manifest(engine, tmp_path):
    m = run_extract(DAY, engine, LocalStorage(str(tmp_path)), schema="main", include_static=True)
    df = pd.read_parquet(tmp_path / table_key("order_items", DAY))
    assert {"_batch_id", "_business_date", "_extracted_at"} <= set(df.columns)
    assert (df["_business_date"] == "2017-11-24").all()
    assert (df["_batch_id"] == m["batch_id"]).all()

    on_disk = json.loads((tmp_path / manifest_key(DAY)).read_text())
    assert on_disk["tables"]["geolocation"]["rows"] == 1
    assert set(on_disk["tables"]) == {s.name for s in TABLES}


def test_empty_day_writes_manifest_but_no_files(engine, tmp_path):
    empty_day = date(2016, 1, 1)
    m = run_extract(empty_day, engine, LocalStorage(str(tmp_path)), schema="main")
    assert m["tables"]["orders"] == {"mode": "incremental", "rows": 0, "uri": None}
    assert not (tmp_path / table_key("orders", empty_day)).exists()
    assert (tmp_path / manifest_key(empty_day)).exists()


def test_rerun_is_idempotent(engine, tmp_path):
    storage = LocalStorage(str(tmp_path))
    run_extract(DAY, engine, storage, schema="main")
    run_extract(DAY, engine, storage, schema="main")
    files = list((tmp_path / "raw/olist/orders").rglob("*.parquet"))
    assert len(files) == 1
    assert len(pd.read_parquet(files[0])) == 2


def test_cli_validation():
    assert parse_args(["--date", "2017-11-24"]).date == DAY
    with pytest.raises(SystemExit):
        parse_args(["--start", "2017-01-02"])
    with pytest.raises(SystemExit):
        parse_args(["--start", "2017-01-05", "--end", "2017-01-01"])
