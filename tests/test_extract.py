"""Extractor tests against the SQLite source fixture."""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from ingestion.dates import daterange
from ingestion.extract import manifest_key, parse_args, run_extract, table_key
from ingestion.storage import LocalStorage
from ingestion.tables import TABLES, Mode
from tests.conftest import DAY


def extract(engine, tmp_path, **kwargs) -> dict:
    return run_extract(DAY, engine, LocalStorage(str(tmp_path)), schema="main", **kwargs)


def test_incremental_window_is_half_open(engine, tmp_path):
    t = extract(engine, tmp_path)["tables"]
    assert t["orders"]["rows"] == 2  # o2, o3
    assert t["order_items"]["rows"] == 3  # items of o2 and o3
    assert t["order_payments"]["rows"] == 2
    assert t["customers"]["rows"] == 2  # c2, c3
    assert t["order_reviews"]["rows"] == 1  # r1: a late-arriving review for yesterday's order
    assert t["products"]["rows"] == 2  # snapshot = full table
    assert "geolocation" not in t  # static tables are opt-in
    assert sorted(pd.read_parquet(tmp_path / table_key("orders", DAY))["order_id"]) == ["o2", "o3"]


def test_lineage_columns_and_manifest(engine, tmp_path):
    m = extract(engine, tmp_path, modes=set(Mode))
    df = pd.read_parquet(tmp_path / table_key("order_items", DAY))
    assert (df["_business_date"] == "2017-11-24").all()
    assert (df["_batch_id"] == m["batch_id"]).all()
    assert "_extracted_at" in df

    on_disk = json.loads((tmp_path / manifest_key(DAY)).read_text())
    assert on_disk["tables"]["geolocation"]["rows"] == 1
    assert set(on_disk["tables"]) == {s.name for s in TABLES}


def test_empty_day_writes_manifest_but_no_files(engine, tmp_path):
    empty_day = date(2016, 1, 1)
    m = run_extract(empty_day, engine, LocalStorage(str(tmp_path)), schema="main")
    assert m["tables"]["orders"] == {"mode": "incremental", "rows": 0, "uri": None}
    assert not (tmp_path / table_key("orders", empty_day)).exists()
    assert (tmp_path / manifest_key(empty_day)).exists()


def test_modes_select_tables(engine, tmp_path):
    t = extract(engine, tmp_path, modes={Mode.INCREMENTAL})["tables"]
    assert "products" not in t and "sellers" not in t
    assert t["orders"]["rows"] == 2


def test_rerun_is_idempotent(engine, tmp_path):
    extract(engine, tmp_path)
    extract(engine, tmp_path)
    [file] = (tmp_path / "raw/olist/orders").rglob("*.parquet")
    assert len(pd.read_parquet(file)) == 2


def test_daterange_is_inclusive():
    assert list(daterange(DAY, date(2017, 11, 26))) == [DAY, date(2017, 11, 25), date(2017, 11, 26)]


def test_cli_validation():
    args = parse_args(["--date", "2017-11-24"])
    assert (args.start, args.end) == (DAY, DAY)
    for bad in (["--start", "2017-01-02"], ["--start", "2017-01-05", "--end", "2017-01-01"]):
        with pytest.raises(SystemExit):
            parse_args(bad)
