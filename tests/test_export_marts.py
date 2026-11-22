"""Tests for the CSV export (no Snowflake: a fake cursor simulates UNLOAD + GET)."""
from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

import pytest

from publishing.export_marts import (
    count_csv_rows,
    get_statement,
    run_export,
    unload_statement,
    with_retries,
)

CSV_BODY = (
    'order_id,is_revenue_order,purchase_date,revenue,comment\n'
    'o1,TRUE,2017-11-24,100.50,"multi\nline"\n'
    'o2,FALSE,2017-11-24,0.00,\n'
)


class FakeCursor:
    """Answers the 4 statements export_table issues; GET writes a gz file."""

    def __init__(self, rows_in_table=2, body=CSV_BODY):
        self.rows_in_table = rows_in_table
        self.body = body
        self.description = None
        self._one = None
        self.statements = []

    def execute(self, sql):
        self.statements.append(sql.strip())
        if "LIMIT 0" in sql:
            self.description = [("ORDER_ID",), ("IS_REVENUE_ORDER",), ("PURCHASE_DATE",), ("REVENUE",), ("COMMENT",)]
        elif sql.startswith("SELECT COUNT(*)"):
            self._one = (self.rows_in_table,)
        elif sql.startswith("GET"):
            m = re.search(r"/(\w+)\.csv\.gz 'file://(.+)/'", sql)
            table, local = m.group(1), Path(m.group(2))
            with gzip.open(local / f"{table}.csv.gz", "wt", encoding="utf-8") as f:
                f.write(self.body)

    def fetchone(self):
        return self._one


class FakeConn:
    def __init__(self, cur):
        self.cur = cur

    def cursor(self):
        return self.cur


def test_unload_statement():
    sql = unload_statement("fct_orders", ["ORDER_ID", "REVENUE"])
    assert 'ORDER_ID AS "order_id", REVENUE AS "revenue"' in sql
    assert "COPY INTO @~/olist_exports/fct_orders.csv.gz" in sql
    assert "SINGLE = TRUE" in sql and "HEADER = TRUE" in sql


def test_get_statement_quotes_paths_with_spaces():
    expected = "GET @~/olist_exports/dim_date.csv.gz 'file:///tmp/my dir/'"
    assert get_statement("dim_date", Path("/tmp/my dir")) == expected


def test_count_csv_rows_handles_quoted_newlines(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text(CSV_BODY)
    assert count_csv_rows(p) == 2


def test_export_writes_csv_and_manifest(tmp_path):
    cur = FakeCursor()
    m = run_export(FakeConn(cur), tmp_path, tables=["fct_orders"])
    assert m["tables"]["fct_orders"]["rows"] == 2
    assert m["tables"]["fct_orders"]["columns"][0] == "order_id"
    assert (tmp_path / "fct_orders.csv").read_text() == CSV_BODY
    assert json.loads((tmp_path / "_manifest.json").read_text())["tables"]["fct_orders"]["rows"] == 2
    assert not list(tmp_path.glob("*.tmp"))
    assert any(s.startswith("COPY INTO") for s in cur.statements)


def test_retries_transient_failures_then_succeeds():
    calls, sleeps = [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise OSError("throughput of 0 B/s")
        return "ok"

    assert with_retries(flaky, "GET x", sleep=sleeps.append) == "ok"
    assert sleeps == [2.0, 4.0]


def test_retries_give_up_after_last_attempt():
    def always_fails():
        raise OSError("stalled")

    with pytest.raises(OSError):
        with_retries(always_fails, "GET x", attempts=3, sleep=lambda s: None)


def test_row_count_mismatch_fails(tmp_path):
    with pytest.raises(RuntimeError, match="CSV has 2 rows but Snowflake has 3"):
        run_export(FakeConn(FakeCursor(rows_in_table=3)), tmp_path, tables=["fct_orders"])
