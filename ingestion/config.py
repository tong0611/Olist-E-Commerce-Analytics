"""Runtime configuration, read from environment variables (or a .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional (e.g. inside Lambda/Airflow)
    pass

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
    lake_target: str          # "local" or "s3"
    local_lake_dir: str
    s3_bucket: str
    aws_region: str
    aws_profile: Optional[str]  # None = default credential chain (env vars, IAM role, ...)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            pg_host=os.getenv("PG_HOST", "localhost"),
            pg_port=int(os.getenv("PG_PORT", "5432")),
            pg_db=os.getenv("PG_DB", "olist"),
            pg_user=os.getenv("PG_USER", "olist"),
            pg_password=os.getenv("PG_PASSWORD", "olist"),
            pg_schema=os.getenv("PG_SCHEMA", "olist"),
            lake_target=os.getenv("LAKE_TARGET", "local").lower(),
            local_lake_dir=os.getenv("LOCAL_LAKE_DIR", "./data/lake"),
            s3_bucket=os.getenv("S3_BUCKET", ""),
            aws_region=os.getenv("AWS_REGION", "us-east-1"),
            aws_profile=os.getenv("AWS_PROFILE") or None,
        )

    @property
    def sqlalchemy_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )
