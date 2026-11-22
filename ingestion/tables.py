"""What to extract from the source database, and how.

incremental  rows for the business date being processed (half-open window [start, end))
snapshot     small dimensions, re-extracted in full
static       reference data, extracted only with --include-static

Queries use a `{schema}` placeholder and `:start` / `:end` bind parameters,
so the same SQL runs on Postgres and on SQLite in the unit tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Mode(StrEnum):
    INCREMENTAL = "incremental"
    SNAPSHOT = "snapshot"
    STATIC = "static"


@dataclass(frozen=True)
class TableSpec:
    name: str
    mode: Mode
    query: str


_ORDER_WINDOW = "o.order_purchase_timestamp >= :start AND o.order_purchase_timestamp < :end"


def _joined_to_orders(table: str, key: str) -> str:
    return (
        f"SELECT t.* FROM {{schema}}.{table} t "
        f"JOIN {{schema}}.orders o ON o.{key} = t.{key} WHERE {_ORDER_WINDOW}"
    )


def _full(table: str) -> str:
    return f"SELECT * FROM {{schema}}.{table}"


TABLES: list[TableSpec] = [
    TableSpec("orders", Mode.INCREMENTAL, f"SELECT o.* FROM {{schema}}.orders o WHERE {_ORDER_WINDOW}"),
    TableSpec("order_items", Mode.INCREMENTAL, _joined_to_orders("order_items", "order_id")),
    TableSpec("order_payments", Mode.INCREMENTAL, _joined_to_orders("order_payments", "order_id")),
    # customer_id is new on every order, so "customers who ordered today" is incremental
    TableSpec("customers", Mode.INCREMENTAL, _joined_to_orders("customers", "customer_id")),
    # reviews arrive days after the order: real late-arriving data
    TableSpec(
        "order_reviews",
        Mode.INCREMENTAL,
        "SELECT * FROM {schema}.order_reviews WHERE review_creation_date >= :start AND review_creation_date < :end",
    ),
    TableSpec("products", Mode.SNAPSHOT, _full("products")),
    TableSpec("sellers", Mode.SNAPSHOT, _full("sellers")),
    TableSpec("product_category_translation", Mode.SNAPSHOT, _full("product_category_translation")),
    TableSpec("geolocation", Mode.STATIC, _full("geolocation")),
]
