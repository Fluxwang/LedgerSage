from __future__ import annotations

import math
from typing import Protocol


class VectorStore(Protocol):
    def build(self, transactions: list[dict]): ...

    def query(
        self, embedding: list[float], sentence: str, candidate_amount: int
    ) -> list[dict]: ...


def calculate_score(transaction: dict, sentence: str) -> float:
    del sentence
    # occurance: 该交易在历史中出现的次数，使用对数函数进行计算 底数为50
    # 出现的次数越多, 对数值越大，可以进行压缩差异，让频繁交易有优势但不会完全压倒相似度
    occurrence_score = math.log(transaction["occurance"] + 1, 50)
    return transaction["distance"] + occurrence_score
