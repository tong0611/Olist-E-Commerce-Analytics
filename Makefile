PY := .venv/bin/python
DATE ?= 2017-11-24

.PHONY: setup db-up db-down download seed extract backfill test clean-lake tf-init tf-plan tf-apply s3-check snowflake-render sf-bootstrap load load-range dbt-deps dbt-build dbt-docs dbt-freshness

setup:            ## create virtualenv and install dependencies
	/opt/homebrew/bin/python3.12 -m venv .venv
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r requirements-dev.txt
	@test -f .env || cp .env.example .env

db-up:            ## start the Postgres source database
	docker compose up -d --wait postgres

db-down:
	docker compose down

download:         ## download Olist CSVs from Kaggle
	bash scripts/download_data.sh

seed:             ## load CSVs into Postgres
	$(PY) scripts/seed_postgres.py

extract:          ## extract one day:  make extract DATE=2017-11-24
	$(PY) -m ingestion.extract --date $(DATE)

backfill:         ## make backfill START=2017-01-01 END=2017-01-31
	$(PY) -m ingestion.extract --start $(START) --end $(END) --include-static

test:
	$(PY) -m pytest -q

clean-lake:
	rm -rf data/lake

# --- Phase 2: AWS infrastructure ---
TF := terraform -chdir=infra/terraform

tf-init:
	$(TF) init

tf-plan:
	$(TF) plan -out=phase2.tfplan

tf-apply:
	$(TF) apply phase2.tfplan

s3-check:         ## confirm the pipeline role can write to the lake
	aws sts get-caller-identity --profile olist-ingestion
	aws s3 ls s3://$$(terraform -chdir=infra/terraform output -raw lake_bucket)/raw/ --profile olist-ingestion

# --- Phase 5: Snowflake ---
snowflake-render: ## fill snowflake/01_account_setup.sql -> build/ (paste into Snowsight)
	$(PY) scripts/render_snowflake_setup.py

sf-bootstrap:     ## create stage + RAW/AUDIT tables
	$(PY) -m loading.load_raw --bootstrap

load:             ## make load DATE=2017-11-24
	$(PY) -m loading.load_raw --date $(DATE)

load-range:       ## make load-range START=2017-11-20 END=2017-11-26
	$(PY) -m loading.load_raw --start $(START) --end $(END)

# --- Phase 6: dbt ---
DBT := bash scripts/dbt.sh

dbt-deps:
	$(DBT) deps

dbt-build:        ## run + test every model (fails on any error-severity test)
	$(DBT) build

dbt-docs:         ## generate and serve the dbt docs site with lineage graph
	$(DBT) docs generate && $(DBT) docs serve --port 8081

dbt-freshness:
	$(DBT) source freshness
