PY    := .venv/bin/python
DBT   := bash scripts/dbt.sh
TF    := terraform -chdir=infra/terraform
DATE  ?= 2017-11-24

.PHONY: help setup db-up db-down download seed extract backfill load load-range sf-bootstrap snowflake-render \
        dbt-deps dbt-build dbt-docs export day airflow-up airflow-down test lint tf-init tf-plan tf-apply s3-check

help:             ## list targets
	@grep -E '^[a-z0-9-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-17s %s\n", $$1, $$2}'

# --- local setup -------------------------------------------------------------
setup:            ## virtualenv, dependencies and .env
	python3.12 -m venv .venv
	$(PY) -m pip install -q --upgrade pip -r requirements-dev.txt
	@test -f .env || cp .env.example .env

db-up:            ## start the Postgres source database
	docker compose up -d --wait postgres

db-down:          ## stop it (data persists in a Docker volume)
	docker compose down

download:         ## Olist CSVs from Kaggle -> data/source/
	bash scripts/download_data.sh

seed:             ## CSVs -> Postgres
	$(PY) -m scripts.seed_postgres

# --- pipeline ----------------------------------------------------------------
extract:          ## one business date -> lake:   make extract DATE=2017-11-24
	$(PY) -m ingestion.extract --date $(DATE)

backfill:         ## a range -> lake:             make backfill START=... END=...
	$(PY) -m ingestion.extract --start $(START) --end $(END) --include-static

load:             ## lake -> Snowflake RAW + reconciliation:   make load DATE=...
	$(PY) -m loading.load_raw --date $(DATE)

load-range:       ## make load-range START=... END=...
	$(PY) -m loading.load_raw --start $(START) --end $(END)

dbt-build:        ## build and test every dbt model
	$(DBT) build

day: extract load dbt-build  ## run one business date end to end

export:           ## dbt marts -> exports/*.csv
	$(PY) -m publishing.export_marts

dbt-deps:
	$(DBT) deps

airflow-up:       ## Airflow UI on http://localhost:8080
	docker compose --profile airflow up -d --build --wait

airflow-down:
	docker compose --profile airflow down

dbt-docs:         ## dbt docs with lineage graph on :8081
	$(DBT) docs generate && $(DBT) docs serve --port 8081

# --- quality -----------------------------------------------------------------
test:             ## unit tests (no Docker, AWS or Snowflake needed)
	$(PY) -m pytest

lint:
	.venv/bin/ruff check .

# --- one-time infrastructure ---------------------------------------------------
tf-init:
	$(TF) init

tf-plan:          ## S3 lake, IAM roles, budget
	$(TF) plan -out=olist.tfplan

tf-apply:
	$(TF) apply olist.tfplan

s3-check:         ## confirm the pipeline role can reach the lake
	aws s3 ls s3://$$($(TF) output -raw lake_bucket)/raw/ --profile olist-ingestion

snowflake-render: ## fill snowflake/01_account_setup.sql -> build/ (run it in Snowsight)
	$(PY) scripts/render_snowflake_setup.py

sf-bootstrap:     ## stage, RAW and AUDIT tables
	$(PY) -m loading.load_raw --bootstrap
