PY := .venv/bin/python
DATE ?= 2017-11-24

.PHONY: setup db-up db-down download seed extract backfill test clean-lake tf-init tf-plan tf-apply s3-check

setup:            ## create virtualenv and install dependencies
	python3 -m venv .venv
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
