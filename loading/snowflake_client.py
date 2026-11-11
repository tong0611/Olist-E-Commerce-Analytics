"""Snowflake connection for the loader (key-pair auth, no passwords)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import ingestion.config  # noqa: F401  (loads .env)


@dataclass(frozen=True)
class SnowflakeSettings:
    account: str
    user: str
    private_key_path: str
    role: str
    warehouse: str
    database: str
    lake_bucket: str

    @classmethod
    def loader_from_env(cls) -> "SnowflakeSettings":
        account = os.getenv("SNOWFLAKE_ACCOUNT", "")
        if not account:
            raise ValueError("SNOWFLAKE_ACCOUNT is not set (e.g. myorg-myaccount) - see .env.example")
        return cls(
            account=account,
            user=os.getenv("SNOWFLAKE_LOADER_USER", "OLIST_LOADER_SVC"),
            private_key_path=str(
                Path(os.getenv("SNOWFLAKE_LOADER_KEY", "~/.snowflake/keys/olist_loader_rsa_key.p8")).expanduser()
            ),
            role=os.getenv("SNOWFLAKE_LOADER_ROLE", "OLIST_LOADER"),
            warehouse=os.getenv("SNOWFLAKE_LOADER_WAREHOUSE", "OLIST_LOAD_WH"),
            database=os.getenv("SNOWFLAKE_DATABASE", "OLIST"),
            lake_bucket=os.getenv("S3_BUCKET", ""),
        )


    @classmethod
    def transformer_from_env(cls) -> "SnowflakeSettings":
        """The dbt service user: owns the MARTS schema, used for exports too."""
        base = cls.loader_from_env()
        return cls(
            account=base.account,
            user=os.getenv("SNOWFLAKE_DBT_USER", "OLIST_DBT_SVC"),
            private_key_path=str(
                Path(os.getenv("SNOWFLAKE_DBT_KEY", "~/.snowflake/keys/olist_dbt_rsa_key.p8")).expanduser()
            ),
            role="OLIST_TRANSFORMER",
            warehouse="OLIST_TRANSFORM_WH",
            database=base.database,
            lake_bucket=base.lake_bucket,
        )


def connect(cfg: SnowflakeSettings, query_tag: str = "olist-pipeline:loader"):
    import snowflake.connector

    return snowflake.connector.connect(
        account=cfg.account,
        user=cfg.user,
        authenticator="SNOWFLAKE_JWT",
        private_key_file=cfg.private_key_path,
        role=cfg.role,
        warehouse=cfg.warehouse,
        database=cfg.database,
        session_parameters={"QUERY_TAG": query_tag},
    )
