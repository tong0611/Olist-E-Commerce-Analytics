"""Unit tests for the Snowflake loader's pure logic (no Snowflake connection)."""
from __future__ import annotations

from datetime import date

import pytest

from ingestion.extract import table_key
from ingestion.tables import TABLES
from loading.load_raw import (
    Reconciliation,
    bootstrap_statements,
    business_date_from_path,
    chunks,
    copy_statement,
    files_by_table,
    parse_args,
    parse_copy_results,
    reconcile,
    relative_file,
    tables_to_reconcile,
)

COPY_COLS = [("file",), ("status",), ("rows_parsed",), ("rows_loaded",), ("error_limit",),
             ("errors_seen",), ("first_error",)]
D1, D2 = date(2017, 11, 24), date(2017, 11, 25)
MANIFESTS = {
    D1: {"batch_id": "b1", "tables": {"orders": {"rows": 3}, "order_reviews": {"rows": 0}}},
    D2: {"batch_id": "b2", "tables": {"orders": {"rows": 2}, "order_reviews": {"rows": 1}}},
}


def test_business_date_from_path():
    assert business_date_from_path("s3://b/raw/olist/orders/dt=2017-11-24/orders.parquet") == "2017-11-24"
    assert business_date_from_path("no-date-here") is None
    assert business_date_from_path(None) is None


def test_relative_file_matches_extractor_layout():
    assert table_key("orders", D1).endswith("orders/" + relative_file("orders", D1))


def test_copy_lists_explicit_files():
    sql = copy_statement("order_items", ["dt=2017-11-24/order_items.parquet"])
    assert "RAW.ORDER_ITEMS" in sql
    assert "FROM @RAW.LAKE_STAGE/olist/order_items/" in sql
    assert "FILES = ('dt=2017-11-24/order_items.parquet')" in sql


def test_files_by_table_skips_empty_tables():
    assert files_by_table(MANIFESTS) == {
        "orders": ["dt=2017-11-24/orders.parquet", "dt=2017-11-25/orders.parquet"],
        "order_reviews": ["dt=2017-11-25/order_reviews.parquet"],
    }


def test_reconcile_by_batch_id():
    counts = {"orders": {"b1": 3, "b2": 1, "old-batch": 99}, "order_reviews": {"b2": 1}}
    checks = {(c.business_date, c.table): c.status for c in reconcile(MANIFESTS, counts)}
    assert checks == {
        (D1, "orders"): "MATCH",
        (D2, "orders"): "MISMATCH",       # 2 expected, 1 loaded
        (D2, "order_reviews"): "MATCH",
    }


def test_parse_copy_results_loaded_files():
    rows = [("s3://b/raw/olist/orders/dt=2017-11-24/orders.parquet", "LOADED", 1176, 1176, 1, 0, None)]
    [r] = parse_copy_results(COPY_COLS, rows)
    assert (r.status, r.rows_loaded) == ("LOADED", 1176)


def test_parse_copy_results_nothing_new():
    assert parse_copy_results([("status",)], [("Copy executed with 0 files processed.",)]) == []


def test_tables_to_reconcile_skips_empty_tables():
    assert tables_to_reconcile(MANIFESTS[D1]) == [("orders", 3)]


def test_reconciliation_status():
    assert Reconciliation(D1, "b", "orders", 10, 10).status == "MATCH"
    assert Reconciliation(D1, "b", "orders", 10, 9).status == "MISMATCH"


def test_chunks_respects_copy_file_limit():
    assert [len(c) for c in chunks(list(range(2500)), 1000)] == [1000, 1000, 500]


def test_bootstrap_creates_every_raw_table():
    stmts = " ".join(bootstrap_statements("my-bucket"))
    assert "URL = 's3://my-bucket/raw/'" in stmts
    for spec in TABLES:
        assert f"RAW.{spec.name.upper()} (" in stmts
    with pytest.raises(ValueError):
        bootstrap_statements("")


def test_cli_requires_valid_range():
    assert parse_args(["--bootstrap"]).bootstrap
    with pytest.raises(SystemExit):
        parse_args(["--start", "2017-11-26", "--end", "2017-11-20"])
