"""写账输入模型与资金流向推导（ADR 0014）。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Direction = Literal["支出", "收入", "转账"]


def flow_direction(
    from_account: str | None, to_account: str | None
) -> Direction | None:
    """由两条分录行的账户前缀推导方向；两侧都定不下来时返回 None（ADR 0014）。"""
    if (to_account or "").startswith("Expenses:"):
        return "支出"
    if (from_account or "").startswith("Income:"):
        return "收入"
    return "转账" if from_account and to_account else None


class TransactionInput(BaseModel):
    amount: Decimal = Field(gt=0)
    date: date
    payee: str = Field(min_length=1)
    narration: str = ""
    from_account: str = Field(min_length=1)
    to_account: str = Field(min_length=1)
    tags: set[str] = Field(default_factory=set)

    @model_validator(mode="after")  # 表示在所有字段都解析、校验完之后再运行
    def normalize_flow(self):
        if self.to_account.startswith("Income:"):
            self.from_account, self.to_account = self.to_account, self.from_account
        if self.from_account == self.to_account or self.to_account.startswith(
            "Income:"
        ):
            raise ValueError("两条分录行不能表示这笔资金流向")
        return self

    @property
    def direction(self) -> Direction:
        return flow_direction(self.from_account, self.to_account) or "转账"
