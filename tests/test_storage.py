"""S3 storage tests against mocked AWS (moto): no real credentials needed."""
from __future__ import annotations

import json

import boto3
import pandas as pd
import pytest
from moto import mock_aws

from ingestion.extract import manifest_key, run_extract, table_key
from ingestion.storage import S3Storage
from tests.conftest import DAY

BUCKET = "test-lake"


@pytest.fixture()
def s3(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def test_s3_write_returns_uri(s3):
    uri = S3Storage(BUCKET, "us-east-1").write_bytes("raw/x/a.json", b"{}", "application/json")
    assert uri == f"s3://{BUCKET}/raw/x/a.json"
    obj = s3.get_object(Bucket=BUCKET, Key="raw/x/a.json")
    assert obj["ContentType"] == "application/json"


def test_missing_bucket_name_is_rejected():
    with pytest.raises(ValueError, match="S3_BUCKET"):
        S3Storage("", "us-east-1")


def test_extract_end_to_end_to_s3(s3, engine, tmp_path):
    run_extract(DAY, engine, S3Storage(BUCKET, "us-east-1"), schema="main")

    keys = {o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET)["Contents"]}
    assert table_key("orders", DAY) in keys
    assert manifest_key(DAY) in keys

    manifest = json.loads(s3.get_object(Bucket=BUCKET, Key=manifest_key(DAY))["Body"].read())
    assert manifest["tables"]["orders"]["uri"] == f"s3://{BUCKET}/{table_key('orders', DAY)}"

    local = tmp_path / "orders.parquet"
    s3.download_file(BUCKET, table_key("orders", DAY), str(local))
    assert len(pd.read_parquet(local)) == 2
