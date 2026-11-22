FROM apache/airflow:3.3.2-python3.12

# The pipeline gets its own virtualenv, so its dependencies (dbt, pandas,
# the Snowflake connector) never clash with Airflow's.
COPY requirements.txt /tmp/requirements.txt
RUN PIP_USER=false python -m venv /home/airflow/pipeline \
 && PIP_USER=false /home/airflow/pipeline/bin/pip install --no-cache-dir -q -r /tmp/requirements.txt
