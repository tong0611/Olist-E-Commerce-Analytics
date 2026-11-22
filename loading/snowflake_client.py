"""Snowflake connections for the pipeline's service users (key-pair auth, no passwords)."""
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
    def _from_env(cls, prefix: str, user: str, key_file: str, role: str, warehouse: str) -> SnowflakeSettings:
        account = os.getenv("SNOWFLAKE_ACCOUNT")
        if not account:
            raise ValueError("SNOWFLAKE_ACCOUNT is not set (e.g. myorg-myaccount); see .env.example")
        key = os.getenv(f"SNOWFLAKE_{prefix}_KEY", f"~/.snowflake/keys/{key_file}")
        return cls(
            account=account,
            user=os.getenv(f"SNOWFLAKE_{prefix}_USER", user),
            private_key_path=str(Path(key).expanduser()),
            role=os.getenv(f"SNOWFLAKE_{prefix}_ROLE", role),
            warehouse=os.getenv(f"SNOWFLAKE_{prefix}_WAREHOUSE", warehouse),
            database=os.getenv("SNOWFLAKE_DATABASE", "OLIST"),
            lake_bucket=os.getenv("S3_BUCKET", ""),
        )

    @classmethod
    def loader_from_env(cls) -> SnowflakeSettings:
        """Writes RAW and AUDIT."""
        return cls._from_env("LOADER", "OLIST_LOADER_SVC", "olist_loader_rsa_key.p8", "OLIST_LOADER", "OLIST_LOAD_WH")

    @classmethod
    def transformer_from_env(cls) -> SnowflakeSettings:
        """The dbt user: owns STAGING, INTERMEDIATE and MARTS."""
        return cls._from_env("DBT", "OLIST_DBT_SVC", "olist_dbt_rsa_key.p8", "OLIST_TRANSFORMER", "OLIST_TRANSFORM_WH")


def connect(cfg: SnowflakeSettings, query_tag: str):
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
        enable_server_session_keep_alive_auto_detection=False,  # always log out on close
    )
