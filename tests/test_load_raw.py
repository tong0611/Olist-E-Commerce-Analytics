"""Unit tests for the Snowflake loader's pure logic (no Snowflake connection)."""
from __future__ import annotations

from datetime import date

import pytest

from ingestion.tables import TABLES
from loading.load_raw import (
    Reconciliation,
    bootstrap_statements,
    copy_statement,
    parse_args,
    parse_copy_results,
    tables_to_reconcile,
)

COPY_COLS = [("file",), ("status",), ("rows_parsed",), ("rows_loaded",), ("error_limit",),
             ("errors_seen",), ("first_error",)]


def test_copy_targets_one_date_partition():
    sql = copy_statement("order_items", date(2017, 11, 24))
    assert "RAW.ORDER_ITEMS" in sql
    assert "@RAW.LAKE_STAGE/olist/order_items/dt=2017-11-24/" in sql
    assert "METADATA$FILENAME" in sql


def test_parse_copy_results_loaded_files():
    rows = [("s3://b/raw/olist/orders/dt=2017-11-24/orders.parquet", "LOADED", 1176, 1176, 1, 0, None)]
    [r] = parse_copy_results(COPY_COLS, rows)
    assert (r.status, r.rows_loaded) == ("LOADED", 1176)


def test_parse_copy_results_nothing_new():
    assert parse_copy_results([("status",)], [("Copy executed with 0 files processed.",)]) == []


def test_tables_to_reconcile_skips_empty_tables():
    manifest = {"tables": {"orders": {"rows": 5}, "order_reviews": {"rows": 0}}}
    assert tables_to_reconcile(manifest) == [("orders", 5)]


def test_reconciliation_status():
    assert Reconciliation("orders", 10, 10).status == "MATCH"
    assert Reconciliation("orders", 10, 9).status == "MISMATCH"


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
