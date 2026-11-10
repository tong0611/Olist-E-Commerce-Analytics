-- =============================================================================
-- Olist pipeline: one-time Snowflake account setup  (run as ACCOUNTADMIN)
--
-- Template: the double-brace placeholders are filled by `make snowflake-render`, which writes
-- build/01_account_setup.sql. Paste THAT file into a Snowsight worksheet and
-- choose "Run All". Safe to re-run (IF NOT EXISTS / OR REPLACE where harmless).
-- =============================================================================

USE ROLE ACCOUNTADMIN;

-- ---------------------------------------------------------------------------
-- 1. Cost guardrail: cap monthly credits, suspend warehouses if exceeded
-- ---------------------------------------------------------------------------
CREATE RESOURCE MONITOR IF NOT EXISTS OLIST_MONTHLY_MONITOR
  WITH CREDIT_QUOTA = 20
       FREQUENCY = MONTHLY
       START_TIMESTAMP = IMMEDIATELY
  TRIGGERS ON 75 PERCENT DO NOTIFY
           ON 100 PERCENT DO SUSPEND
           ON 110 PERCENT DO SUSPEND_IMMEDIATE;

-- ---------------------------------------------------------------------------
-- 2. Roles (functional, least privilege) rolled up to SYSADMIN
-- ---------------------------------------------------------------------------
CREATE ROLE IF NOT EXISTS OLIST_LOADER      COMMENT = 'Loads raw files from S3 into OLIST.RAW';
CREATE ROLE IF NOT EXISTS OLIST_TRANSFORMER COMMENT = 'dbt: reads RAW, builds STAGING/INTERMEDIATE/MARTS';
CREATE ROLE IF NOT EXISTS OLIST_REPORTER    COMMENT = 'Power BI: read-only on MARTS';
GRANT ROLE OLIST_LOADER, OLIST_TRANSFORMER, OLIST_REPORTER TO ROLE SYSADMIN;

-- ---------------------------------------------------------------------------
-- 3. Warehouses: X-Small, suspend after 60s idle, one per workload so cost
--    can be attributed (load vs transform vs BI)
-- ---------------------------------------------------------------------------
USE ROLE SYSADMIN;
CREATE WAREHOUSE IF NOT EXISTS OLIST_LOAD_WH
  WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE;
CREATE WAREHOUSE IF NOT EXISTS OLIST_TRANSFORM_WH
  WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE;
CREATE WAREHOUSE IF NOT EXISTS OLIST_BI_WH
  WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE;

USE ROLE ACCOUNTADMIN;
ALTER WAREHOUSE OLIST_LOAD_WH      SET RESOURCE_MONITOR = OLIST_MONTHLY_MONITOR;
ALTER WAREHOUSE OLIST_TRANSFORM_WH SET RESOURCE_MONITOR = OLIST_MONTHLY_MONITOR;
ALTER WAREHOUSE OLIST_BI_WH        SET RESOURCE_MONITOR = OLIST_MONTHLY_MONITOR;

-- ---------------------------------------------------------------------------
-- 4. Database and schemas
--    RAW    - landed files, untouched (owned by loader)
--    AUDIT  - load history and reconciliation results
--    STAGING / INTERMEDIATE / MARTS - built by dbt (owned by transformer)
-- ---------------------------------------------------------------------------
USE ROLE SYSADMIN;
CREATE DATABASE IF NOT EXISTS OLIST;
CREATE SCHEMA IF NOT EXISTS OLIST.RAW;
CREATE SCHEMA IF NOT EXISTS OLIST.AUDIT;
CREATE SCHEMA IF NOT EXISTS OLIST.STAGING;
CREATE SCHEMA IF NOT EXISTS OLIST.INTERMEDIATE;
CREATE SCHEMA IF NOT EXISTS OLIST.MARTS;

GRANT OWNERSHIP ON SCHEMA OLIST.RAW          TO ROLE OLIST_LOADER      COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA OLIST.AUDIT        TO ROLE OLIST_LOADER      COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA OLIST.STAGING      TO ROLE OLIST_TRANSFORMER COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA OLIST.INTERMEDIATE TO ROLE OLIST_TRANSFORMER COPY CURRENT GRANTS;
GRANT OWNERSHIP ON SCHEMA OLIST.MARTS        TO ROLE OLIST_TRANSFORMER COPY CURRENT GRANTS;

-- ---------------------------------------------------------------------------
-- 5. Grants
-- ---------------------------------------------------------------------------
GRANT USAGE ON DATABASE OLIST TO ROLE OLIST_LOADER;
GRANT USAGE ON DATABASE OLIST TO ROLE OLIST_TRANSFORMER;
GRANT USAGE ON DATABASE OLIST TO ROLE OLIST_REPORTER;

GRANT USAGE ON WAREHOUSE OLIST_LOAD_WH      TO ROLE OLIST_LOADER;
GRANT USAGE ON WAREHOUSE OLIST_TRANSFORM_WH TO ROLE OLIST_TRANSFORMER;
GRANT USAGE ON WAREHOUSE OLIST_BI_WH        TO ROLE OLIST_REPORTER;

-- transformer reads RAW + AUDIT (schemas owned by loader, so loader-owned
-- future tables need these future grants; ACCOUNTADMIN issues them)
USE ROLE ACCOUNTADMIN;
GRANT USAGE ON SCHEMA OLIST.RAW   TO ROLE OLIST_TRANSFORMER;
GRANT USAGE ON SCHEMA OLIST.AUDIT TO ROLE OLIST_TRANSFORMER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA OLIST.RAW   TO ROLE OLIST_TRANSFORMER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA OLIST.AUDIT TO ROLE OLIST_TRANSFORMER;

-- reporter reads only MARTS
GRANT USAGE ON SCHEMA OLIST.MARTS TO ROLE OLIST_REPORTER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA OLIST.MARTS TO ROLE OLIST_REPORTER;
GRANT SELECT ON FUTURE VIEWS  IN SCHEMA OLIST.MARTS TO ROLE OLIST_REPORTER;

-- ---------------------------------------------------------------------------
-- 6. Storage integration: Snowflake -> S3 via IAM role (no AWS keys stored)
-- ---------------------------------------------------------------------------
CREATE STORAGE INTEGRATION IF NOT EXISTS OLIST_S3_LAKE
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'S3'
  ENABLED = TRUE
  STORAGE_AWS_ROLE_ARN = '{{SNOWFLAKE_ROLE_ARN}}'
  STORAGE_ALLOWED_LOCATIONS = ('s3://{{LAKE_BUCKET}}/raw/');

GRANT USAGE ON INTEGRATION OLIST_S3_LAKE TO ROLE OLIST_LOADER;

-- ---------------------------------------------------------------------------
-- 7. Service users: key-pair auth only (TYPE = SERVICE has no password login)
-- ---------------------------------------------------------------------------
CREATE USER IF NOT EXISTS OLIST_LOADER_SVC
  TYPE = SERVICE
  DEFAULT_ROLE = OLIST_LOADER
  DEFAULT_WAREHOUSE = OLIST_LOAD_WH
  DEFAULT_NAMESPACE = OLIST.RAW
  COMMENT = 'Python loader / Airflow';
ALTER USER OLIST_LOADER_SVC SET RSA_PUBLIC_KEY = '{{LOADER_PUBLIC_KEY}}';
GRANT ROLE OLIST_LOADER TO USER OLIST_LOADER_SVC;

CREATE USER IF NOT EXISTS OLIST_DBT_SVC
  TYPE = SERVICE
  DEFAULT_ROLE = OLIST_TRANSFORMER
  DEFAULT_WAREHOUSE = OLIST_TRANSFORM_WH
  DEFAULT_NAMESPACE = OLIST.STAGING
  COMMENT = 'dbt';
ALTER USER OLIST_DBT_SVC SET RSA_PUBLIC_KEY = '{{DBT_PUBLIC_KEY}}';
GRANT ROLE OLIST_TRANSFORMER TO USER OLIST_DBT_SVC;
-- (your own login inherits all three roles through ACCOUNTADMIN -> SYSADMIN)

-- ---------------------------------------------------------------------------
-- 8. Hand these two values back for the AWS trust policy (Terraform)
--    property = STORAGE_AWS_IAM_USER_ARN and STORAGE_AWS_EXTERNAL_ID
-- ---------------------------------------------------------------------------
DESC INTEGRATION OLIST_S3_LAKE;
