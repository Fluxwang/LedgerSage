from __future__ import annotations

import json
from operator import itemgetter
from pathlib import Path
from typing import Any, List

import numpy as np
from numpy.linalg import norm

from beanbot.gateways.vector_store.base import calculate_score


class JsonVectorStore:
    def __init__(self, settings) -> None:
        self.settings = settings

    @property
    def db_path(self) -> Path:
        db_dir = self.settings.embedding.get("db_store_folder", ".")
        return Path(db_dir) / "tx_db.json"

    def build(self, transactions: List[dict]):
        with open(self.db_path, "w", encoding="utf-8") as file:
            # 直接将数据写入 db_store_folder/tx_db.json 文件之中
            json.dump(transactions, file)

    def query(
        self, embedding: List[float], sentence: str, candidate_amount: int
    ) -> list[dict]:
        try:
            with open(self.db_path, encoding="utf-8") as file:
                transactions = json.load(file)
        except FileNotFoundError:
            return []

        # 转化为numpy Array
        embed_query = np.array(embedding)
        for transaction in transactions:
            embed_tx = np.array(transaction["embedding"])
            # 计算出余弦值
            transaction["distance"] = np.dot(embed_tx, embed_query) / (
                norm(embed_tx) * norm(embed_query)
            )
            transaction["score"] = calculate_score(transaction, sentence)
        transactions.sort(key=itemgetter("distance"), reverse=True)
        # 只获取 candidates 个数据
        candidates = transactions[:candidate_amount]
        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates
        # return embed_query
