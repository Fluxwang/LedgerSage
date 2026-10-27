from datetime import date
from decimal import Decimal

import pytest
from beancount.core.amount import Amount
from beancount.core.inventory import Inventory
from beancount.core.position import Position

from beanbot.services.agent.query import (
    DateRange,
    TransactionQuery,
    build_balance_bql,
    build_transaction_bql,
    scalar_amount,
)


def test_fixed_bql_escapes_parameters_and_has_time_bounds():
    query = TransactionQuery(
        start=date(2025, 12, 1),
        end=date(2025, 12, 31),
        account_prefix="Expenses:Food",
        payee='A "shop"',
        limit=26,
    )
    bql = build_transaction_bql(query)
    assert "date >= 2025-12-01" in bql and "date <= 2025-12-31" in bql
    assert '\\"shop\\"' in bql
    assert bql.endswith("LIMIT 26")
    assert build_balance_bql("Assets:Cash", date(2026, 1, 5)).startswith(
        "SELECT account, sum(position)"
    )


def test_inventory_conversion_preserves_multiple_currencies_and_empty_results():
    inventory = Inventory(
        [
            Position(Amount(Decimal("12"), "CNY"), None),
            Position(Amount(Decimal("3"), "USD"), None),
        ]
    )
    assert scalar_amount(inventory) == {"CNY": "12", "USD": "3"}
    assert scalar_amount(Inventory()) == {}


def test_query_range_rejects_future_and_more_than_five_years():
    with pytest.raises(ValueError, match="未来"):
        DateRange(start=date.today(), end=date(date.today().year + 1, 1, 1))
    with pytest.raises(ValueError, match="5 年"):
        DateRange(start=date(2010, 1, 1), end=date(2020, 1, 1))


def test_query_without_dates_defaults_to_this_month():
    today = date.today()
    query = TransactionQuery()
    assert (query.start, query.end) == (today.replace(day=1), today)


def test_query_with_only_end_starts_from_that_month():
    query = TransactionQuery(end=date(2026, 9, 15))
    assert (query.start, query.end) == (date(2026, 9, 1), date(2026, 9, 15))
