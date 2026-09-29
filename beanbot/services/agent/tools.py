"""绑定某一本账本的固定 LangChain 工具集。"""

from datetime import date
from decimal import Decimal
from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from beanbot.gateways.ledger import Ledger
from beanbot.services.agent.query import TransactionQuery


class BalanceInput(BaseModel):
    account_prefix: str
    as_of: date


class AccountListInput(BaseModel):
    prefix: str = ""


def query_tools(ledger: Ledger) -> list[StructuredTool]:
    def query_transactions(**values):
        query = TransactionQuery.model_validate(values)
        return ledger.query_transactions(
            query.start,
            query.end,
            query.account_prefix,
            query.payee,
            query.limit,
            Decimal(str(query.min_amount)) if query.min_amount is not None else None,
            Decimal(str(query.max_amount)) if query.max_amount is not None else None,
            query.group_by,
        )

    def get_balance(account_prefix: str, as_of: date):
        return ledger.balances(account_prefix, as_of)

    def list_accounts(prefix: str = ""):
        return [
            {"account": account, "display_name": display_name}
            for account, display_name in ledger.accounts_with_names()
            if account.startswith(prefix)
        ]

    return [
        StructuredTool.from_function(
            query_transactions,
            name="query_transactions",
            description="按固定参数查询交易",
            args_schema=TransactionQuery,
        ),
        StructuredTool.from_function(
            get_balance,
            name="get_balance",
            description="查询指定日期的账户余额",
            args_schema=BalanceInput,
        ),
        StructuredTool.from_function(
            list_accounts,
            name="list_accounts",
            description="列出账户及其显示名",
            args_schema=AccountListInput,
        ),
    ]
