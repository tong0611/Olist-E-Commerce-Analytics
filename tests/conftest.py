"""Shared fixture: an in-memory SQLite copy of the source schema (no Docker needed)."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine

DAY = date(2017, 11, 24)

SOURCE = """
CREATE TABLE orders (order_id TEXT, customer_id TEXT, order_status TEXT, order_purchase_timestamp TIMESTAMP);
CREATE TABLE order_items (order_id TEXT, order_item_id INT, product_id TEXT, seller_id TEXT, price REAL);
CREATE TABLE order_payments (order_id TEXT, payment_sequential INT, payment_type TEXT, payment_value REAL);
CREATE TABLE customers (customer_id TEXT, customer_unique_id TEXT, customer_state TEXT);
CREATE TABLE order_reviews (review_id TEXT, order_id TEXT, review_score INT, review_creation_date TIMESTAMP);
CREATE TABLE products (product_id TEXT, product_category_name TEXT);
CREATE TABLE sellers (seller_id TEXT, seller_state TEXT);
CREATE TABLE product_category_translation (product_category_name TEXT, product_category_name_english TEXT);
CREATE TABLE geolocation (geolocation_zip_code_prefix TEXT, geolocation_lat REAL);

INSERT INTO orders VALUES
    ('o1', 'c1', 'delivered', '2017-11-23 23:59:59'),  -- day before
    ('o2', 'c2', 'delivered', '2017-11-24 00:00:00'),  -- window start (included)
    ('o3', 'c3', 'shipped',   '2017-11-24 18:30:00'),
    ('o4', 'c4', 'delivered', '2017-11-25 00:00:00');  -- window end (excluded)
INSERT INTO order_items VALUES
    ('o1', 1, 'p1', 's1', 10.0), ('o2', 1, 'p1', 's1', 20.0), ('o2', 2, 'p2', 's1', 5.0), ('o3', 1, 'p2', 's1', 7.5);
INSERT INTO order_payments VALUES ('o2', 1, 'credit_card', 25.0), ('o3', 1, 'boleto', 7.5), ('o4', 1, 'voucher', 1.0);
INSERT INTO customers VALUES ('c1', 'u1', 'SP'), ('c2', 'u2', 'RJ'), ('c3', 'u1', 'SP'), ('c4', 'u3', 'MG');
INSERT INTO order_reviews VALUES ('r1', 'o1', 5, '2017-11-24 00:00:00'), ('r2', 'o0', 3, '2017-11-20 00:00:00');
INSERT INTO products VALUES ('p1', 'beleza_saude'), ('p2', 'esporte_lazer');
INSERT INTO sellers VALUES ('s1', 'SP');
INSERT INTO product_category_translation VALUES ('beleza_saude', 'health_beauty');
INSERT INTO geolocation VALUES ('01037', -23.5);
"""


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    with eng.begin() as conn:
        conn.connection.driver_connection.executescript(SOURCE)
    return eng
