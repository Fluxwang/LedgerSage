"""账户置信度的可复现频次计算。"""
from collections import Counter
from decimal import Decimal
from pydantic import BaseModel


class AccountEvidence(BaseModel):
    account: str
    count: int
    total: int
    ratio: Decimal

    @property
    def label(self) -> str:
        return f'{self.account} {self.count}/{self.total}'


def account_confidence(term: str, history: list[tuple[str, str]]) -> list[AccountEvidence]:
    matches = [account for merchant, account in history if term.casefold() in merchant.casefold()]
    if not matches:
        return []
    counts = Counter(matches)
    total = len(matches)
    return [
        AccountEvidence(account=account, count=count, total=total, ratio=Decimal(count) / Decimal(total))
        for account, count in counts.most_common()
    ]