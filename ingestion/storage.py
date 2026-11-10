"""Data lake writers. Same interface for the local filesystem and S3, so the
pipeline can be developed offline and switched to AWS with one env var."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol

from ingestion.config import Settings


class Storage(Protocol):
    def write_bytes(self, key: str, data: bytes, content_type: Optional[str] = None) -> str: ...


class LocalStorage:
    def __init__(self, base_dir: str) -> None:
        self.base_dir = Path(base_dir).resolve()

    def write_bytes(self, key: str, data: bytes, content_type: Optional[str] = None) -> str:
        path = self.base_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic rename: readers never see half-written files
        return path.as_uri()


class S3Storage:
    def __init__(self, bucket: str, region: str, profile: Optional[str] = None) -> None:
        import boto3  # imported lazily so local mode doesn't need AWS deps configured

        if not bucket:
            raise ValueError("S3_BUCKET must be set when LAKE_TARGET=s3")
        self.bucket = bucket
        self.client = boto3.Session(profile_name=profile, region_name=region).client("s3")

    def write_bytes(self, key: str, data: bytes, content_type: Optional[str] = None) -> str:
        extra = {"ContentType": content_type} if content_type else {}
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, **extra)
        return f"s3://{self.bucket}/{key}"


def get_storage(settings: Settings) -> Storage:
    if settings.lake_target == "s3":
        return S3Storage(settings.s3_bucket, settings.aws_region, settings.aws_profile)
    if settings.lake_target == "local":
        return LocalStorage(settings.local_lake_dir)
    raise ValueError(f"Unknown LAKE_TARGET {settings.lake_target!r} (expected 'local' or 's3')")
