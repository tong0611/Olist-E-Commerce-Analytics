-- Source OLTP database for the Olist e-commerce pipeline.
-- This Postgres database plays the role of the "production" store database
-- that the ingestion layer extracts from.
--
-- Foreign keys are intentionally NOT enforced: the raw Kaggle data has a few
-- orphan/duplicate rows, and catching those is the job of the data quality
-- layer (dbt tests), not the source loader.

CREATE SCHEMA IF NOT EXISTS olist;

CREATE TABLE IF NOT EXISTS olist.customers (
    customer_id              TEXT PRIMARY KEY,   -- one per ORDER (not per person!)
    customer_unique_id       TEXT NOT NULL,      -- the real person identifier
    customer_zip_code_prefix TEXT,
    customer_city            TEXT,
    customer_state           TEXT
);

CREATE TABLE IF NOT EXISTS olist.orders (
    order_id                      TEXT PRIMARY KEY,
    customer_id                   TEXT NOT NULL,
    order_status                  TEXT,
    order_purchase_timestamp      TIMESTAMP NOT NULL,
    order_approved_at             TIMESTAMP,
    order_delivered_carrier_date  TIMESTAMP,
    order_delivered_customer_date TIMESTAMP,
    order_estimated_delivery_date TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_orders_purchase_ts ON olist.orders (order_purchase_timestamp);

CREATE TABLE IF NOT EXISTS olist.order_items (
    order_id            TEXT NOT NULL,
    order_item_id       INTEGER NOT NULL,
    product_id          TEXT NOT NULL,
    seller_id           TEXT NOT NULL,
    shipping_limit_date TIMESTAMP,
    price               NUMERIC(12, 2),
    freight_value       NUMERIC(12, 2),
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE IF NOT EXISTS olist.order_payments (
    order_id             TEXT NOT NULL,
    payment_sequential   INTEGER NOT NULL,
    payment_type         TEXT,
    payment_installments INTEGER,
    payment_value        NUMERIC(12, 2),
    PRIMARY KEY (order_id, payment_sequential)
);

-- review_id is NOT unique in the source data, so no primary key here.
CREATE TABLE IF NOT EXISTS olist.order_reviews (
    review_id               TEXT NOT NULL,
    order_id                TEXT NOT NULL,
    review_score            INTEGER,
    review_comment_title    TEXT,
    review_comment_message  TEXT,
    review_creation_date    TIMESTAMP,
    review_answer_timestamp TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_reviews_creation ON olist.order_reviews (review_creation_date);

CREATE TABLE IF NOT EXISTS olist.products (
    product_id                 TEXT PRIMARY KEY,
    product_category_name      TEXT,
    product_name_lenght        NUMERIC,  -- (sic) misspelled in the source data
    product_description_lenght NUMERIC,  -- (sic)
    product_photos_qty         NUMERIC,
    product_weight_g           NUMERIC,
    product_length_cm          NUMERIC,
    product_height_cm          NUMERIC,
    product_width_cm           NUMERIC
);

CREATE TABLE IF NOT EXISTS olist.sellers (
    seller_id              TEXT PRIMARY KEY,
    seller_zip_code_prefix TEXT,
    seller_city            TEXT,
    seller_state           TEXT
);

CREATE TABLE IF NOT EXISTS olist.product_category_translation (
    product_category_name         TEXT PRIMARY KEY,
    product_category_name_english TEXT
);

CREATE TABLE IF NOT EXISTS olist.geolocation (
    geolocation_zip_code_prefix TEXT,
    geolocation_lat             DOUBLE PRECISION,
    geolocation_lng             DOUBLE PRECISION,
    geolocation_city            TEXT,
    geolocation_state           TEXT
);
