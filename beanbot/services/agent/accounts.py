"""追问和待确认写入共用的资金流向与候选选择。"""

from collections import Counter

from beanbot.gateways.ledger import Ledger
from beanbot.services.agent.confidence import account_confidence

FIELDS = ("from_account", "to_account")
FUNDS = ("Assets:", "Liabilities:")


def normalize(transaction: dict) -> dict:
    """统一资金流向, 如果Income: 账户被放到了 to_account 就把两边对调"""
    result = dict(transaction)
    if (result.get("to_account") or "").startswith("Income:"):
        result["from_account"], result["to_account"] = (
            result.get("to_account"),
            result.get("from_account"),
        )
        result["autofilled"] = [
            FIELDS[1 - FIELDS.index(field)] for field in result.get("autofilled", [])
        ]
    return result


def missing_fields(transactions: list[dict]) -> list[dict]:
    return [
        {"index": index, "field": field}
        for index, item in enumerate(transactions)
        for field in FIELDS
        if not item.get(field)
    ]


def allowed_accounts(
    ledger: Ledger, transaction: dict, field: str
) -> list[tuple[str, str | None]]:
    other = transaction.get(FIELDS[1 - FIELDS.index(field)]) or ""
    prefixes = (
        ("Assets:",)
        if other.startswith("Income:")
        else FUNDS
        if other.startswith("Expenses:")
        else (*FUNDS, "Expenses:", "Income:")
    )
    return [
        (account, name)
        for account, name in ledger.postable_accounts_with_names()
        if account != other and account.startswith(prefixes)
    ]


def role_history(ledger: Ledger, field: str) -> list[tuple[str, str]]:
    position = FIELDS.index(field) + 1
    return [(row[0], row[position]) for row in ledger.transaction_history()]


def candidates(ledger: Ledger, transaction: dict, field: str, limit: int) -> list[dict]:
    history = role_history(ledger, field)
    merchant = {
        item.account: item.count
        for item in account_confidence(transaction.get("payee", ""), history)
    }
    global_counts = Counter(account for _, account in history)
    accounts = allowed_accounts(ledger, transaction, field)
    accounts.sort(
        key=lambda item: (-merchant.get(item[0], 0), -global_counts[item[0]], item[0])
    )
    return [
        {"account": account, "display_name": name or account}
        for account, name in accounts[:limit]
    ]


def preview_accounts(
    ledger: Ledger, transactions: list[dict], limit: int
) -> list[dict]:
    names = dict(ledger.accounts_with_names())
    return [
        item
        | {
            "display_names": {
                field: names.get(item[field]) or item[field] for field in FIELDS
            },
            # 编辑器需要能选到账户树中的任意合法账户；追问仍使用 limit。
            "candidates": {
                field: candidates(
                    ledger, item, field, len(allowed_accounts(ledger, item, field))
                )
                for field in FIELDS
            },
        }
        for item in transactions
    ]

