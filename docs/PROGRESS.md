# Progress log

## Status (2026-11-10)

| # | Phase | Status |
|---|---|---|
| 1 | Postgres source DB + Python incremental extraction | ✅ |
| 2 | AWS S3 lake + IAM (Terraform) | ✅ |
| 5 | Snowflake: storage integration, RAW loads, reconciliation | ✅ |
| 6 | dbt: 22 models, 105 tests | ✅ |
| 8 | **Tableau Public** dashboards (switched from Power BI: no Windows machine) | ⬜ next |
| 7 | Airflow daily DAG | ⬜ |
| 3 | Lambda real-time order events | ⬜ |
| 4 | Glue raw → processed | ⬜ |
| 9 | CI (GitHub Actions) + monitoring | ⬜ |

Build order was changed to get an end-to-end pipeline with dashboards first:
5 → 6 → 8 → 7 → 3 → 4 → 9.

## Data currently loaded
- Full Olist history (2016-09-04 .. 2018-10-17, 774 business dates) extracted to S3 and loaded into Snowflake.
- 3,156 table-day reconciliation checks: all MATCH.
- `dbt build`: 103 pass, 2 intended warnings (256 payment/value mismatches, 8 delivered orders without a date).
- Total revenue R$15,735,527.03 · 99,441 orders · 96,096 customers · AOV R$160.23. All tie to the source DB.

## Next session: Phase 8 (Tableau)
1. `publishing/export_marts.py`: after `dbt build`, export the MARTS tables from Snowflake to CSV
   (Tableau Public can't connect to Snowflake, so it reads files).
2. Tableau build guide: 3 dashboards (Revenue overview; Customers & retention; Products), with calculated fields.
3. Publish to Tableau Public and add the link and screenshots to the README.
4. Open question: is the author a student? If so, get the free Tableau Desktop license for a live-Snowflake screenshot.

## Resuming the environment
```bash
cd olist-ecommerce-pipeline
open -a Docker                 # then wait for the whale icon to settle
make db-up                     # Postgres source DB (data persists in the Docker volume)
make test                      # 21 Python tests
make dbt-build                 # rebuild + test marts in Snowflake (warehouse auto-resumes)
```
Snowflake warehouses auto-suspend after 60s, so nothing bills while idle. The Snowflake trial ends ~2026-12-10.
