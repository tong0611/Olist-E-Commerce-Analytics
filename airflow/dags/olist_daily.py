"""Daily Olist pipeline: extract -> load + reconcile -> dbt build.

The store is replayed nine years behind real time: the run on 2026-11-24
processes Olist's 2017-11-24 (Black Friday). Trigger the DAG with a
`business_date` to run any day by hand.
"""
from __future__ import annotations

from datetime import date, timedelta

import pendulum
from airflow.exceptions import AirflowSkipException
from airflow.sdk import Param, dag, task

REPO = "/opt/olist"
VENV = "/home/airflow/pipeline/bin"
REPLAY_OFFSET = date(2026, 11, 24) - date(2017, 11, 24)
FIRST_DAY, LAST_DAY = date(2016, 9, 4), date(2018, 10, 17)


@dag(
    schedule="@daily",
    start_date=pendulum.datetime(2026, 11, 22, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5), "execution_timeout": timedelta(minutes=30)},
    params={
        "business_date": Param(
            None, type=["null", "string"], format="date",
            description="Olist date to process. Empty = today minus the replay offset.",
        )
    },
    tags=["olist"],
)
def olist_daily():
    @task
    def business_date(params=None, logical_date=None, dag_run=None) -> str:
        if params["business_date"]:
            day = date.fromisoformat(params["business_date"])
        else:
            day = (logical_date or dag_run.run_after).date() - REPLAY_OFFSET
        if not FIRST_DAY <= day <= LAST_DAY:
            raise AirflowSkipException(f"{day} is outside the Olist data ({FIRST_DAY} .. {LAST_DAY})")
        return day.isoformat()

    @task.bash(cwd=REPO)
    def extract(day: str) -> str:
        return f"{VENV}/python -m ingestion.extract --date {day}"

    @task.bash(cwd=REPO)
    def load(day: str) -> str:
        return f"{VENV}/python -m loading.load_raw --date {day}"

    @task.bash(cwd=f"{REPO}/dbt")
    def dbt_build() -> str:
        return f"{VENV}/dbt build --profiles-dir ."

    day = business_date()
    extract(day) >> load(day) >> dbt_build()


olist_daily()
