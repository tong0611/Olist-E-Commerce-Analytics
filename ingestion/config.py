"""Runtime settings, read from environment variables (and .env)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# `AWS_PROFILE=` (blank) in .env would make boto3 look for a profile named "".
if os.environ.get("AWS_PROFILE") == "":
    del os.environ["AWS_PROFILE"]


@dataclass(frozen=True)
class Settings:
    pg_host: str
    pg_port: int
    pg_db: str
    pg_user: str
    pg_password: str
    pg_schema: str
    lake_target: str  # "local" or "s3"
    local_lake_dir: str
    s3_bucket: str
    aws_region: str
    aws_profile: str | None  # None = default credential chain

    @classmethod
    def from_env(cls) -> Settings:
        env = os.getenv
        return cls(
            pg_host=env("PG_HOST", "localhost"),
            pg_port=int(env("PG_PORT", "5432")),
            pg_db=env("PG_DB", "olist"),
            pg_user=env("PG_USER", "olist"),
            pg_password=env("PG_PASSWORD", "olist"),
            pg_schema=env("PG_SCHEMA", "olist"),
            lake_target=env("LAKE_TARGET", "local").lower(),
            local_lake_dir=env("LOCAL_LAKE_DIR", "./data/lake"),
            s3_bucket=env("S3_BUCKET", ""),
            aws_region=env("AWS_REGION", "us-east-1"),
            aws_profile=env("AWS_PROFILE") or None,
        )

    @property
    def sqlalchemy_url(self) -> str:
        return f"postgresql+psycopg2://{self.pg_user}:{self.pg_password}@{self.pg_host}:{self.pg_port}/{self.pg_db}"
