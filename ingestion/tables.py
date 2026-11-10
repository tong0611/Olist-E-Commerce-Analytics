"""What to extract from the source database, and how.

Load modes
----------
incremental : only rows belonging to the business date being processed
              (driven by the order purchase timestamp / review creation date)
snapshot    : small dimension tables, fully re-extracted every day
static      : reference data that basically never changes; only extracted
              when explicitly requested (--include-static)

Queries use `{schema}` as a placeholder and `:start` / `:end` bind params
(half-open window [start, end)), which keeps them portable across Postgres
and SQLite (used in the unit tests).
"""
from __future__ import annotations

from dataclasses import dataclass

INCREMENTAL = "incremental"
SNAPSHOT = "snapshot"
STATIC = "static"


@dataclass(frozen=True)
class TableSpec:
    name: str
    mode: str
    query: str


_ORDER_WINDOW = "o.order_purchase_timestamp >= :start AND o.order_purchase_timestamp < :end"

TABLES: list[TableSpec] = [
    TableSpec("orders", INCREMENTAL, f"SELECT o.* FROM {{schema}}.orders o WHERE {_ORDER_WINDOW}"),
    TableSpec(
        "order_items",
        INCREMENTAL,
        f"SELECT oi.* FROM {{schema}}.order_items oi "
        f"JOIN {{schema}}.orders o ON o.order_id = oi.order_id WHERE {_ORDER_WINDOW}",
    ),
    TableSpec(
        "order_payments",
        INCREMENTAL,
        f"SELECT p.* FROM {{schema}}.order_payments p "
        f"JOIN {{schema}}.orders o ON o.order_id = p.order_id WHERE {_ORDER_WINDOW}",
    ),
    # customer_id is unique per order, so "customers who ordered today" is incremental
    TableSpec(
        "customers",
        INCREMENTAL,
        f"SELECT c.* FROM {{schema}}.customers c "
        f"JOIN {{schema}}.orders o ON o.customer_id = c.customer_id WHERE {_ORDER_WINDOW}",
    ),
    # Reviews arrive days after the order -> a natural late-arriving data source
    TableSpec(
        "order_reviews",
        INCREMENTAL,
        "SELECT r.* FROM {schema}.order_reviews r "
        "WHERE r.review_creation_date >= :start AND r.review_creation_date < :end",
    ),
    TableSpec("products", SNAPSHOT, "SELECT * FROM {schema}.products"),
    TableSpec("sellers", SNAPSHOT, "SELECT * FROM {schema}.sellers"),
    TableSpec("product_category_translation", SNAPSHOT, "SELECT * FROM {schema}.product_category_translation"),
    TableSpec("geolocation", STATIC, "SELECT * FROM {schema}.geolocation"),
]
