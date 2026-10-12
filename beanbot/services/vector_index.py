"""每用户向量索引，支持增量写入和可重跑的全量构建。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import sqlite3
from pathlib import Path
from typing import Any, Protocol

import httpx

from beanbot.config import Settings
from beanbot.gateways.ledger import LedgerFactory


class EmbeddingError(RuntimeError):
    pass


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class HttpEmbedder:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """按 EMBEDDING_BATCH_SIZE 切批发送：服务商普遍对单次条数有上限。"""
        size = self.settings.embedding_batch_size
        vectors: list[list[float]] = []
        url = self.settings.embedding_base_url.rstrip("/") + "/embeddings"
        headers = {
            "Authorization": f"Bearer {self.settings.embedding_api_key.get_secret_value()}"
        }
        async with httpx.AsyncClient(timeout=120) as client:
            for offset in range(0, len(texts), size):
                payload = {
                    "model": self.settings.embedding_model,
                    "input": texts[offset : offset + size],
                    "encoding_format": "float",
                }
                response = await client.post(url, headers=headers, json=payload)
                if response.is_error:
                    # 服务商把「哪个参数不对」写在响应体里，raise_for_status 会丢掉它。
                    raise EmbeddingError(
                        f"embedding 请求失败：HTTP {response.status_code} {url}\n{response.text[:500]}"
                    )
                rows = sorted(response.json()["data"], key=lambda item: item["index"])
                vectors.extend(row["embedding"] for row in rows)
        return vectors


class VectorIndexManager:
    def __init__(
        self,
        settings: Settings,
        ledgers: LedgerFactory,
        embedder: Embedder | None = None,
    ):
        self.settings = settings
        self.ledgers = ledgers
        self.embedder = embedder or HttpEmbedder(settings)
        self.log = logging.getLogger(__name__)
        self._pending: dict[str, set[asyncio.Task]] = {}
        self._rebuilds: dict[str, dict] = {}

    def path(self, user: dict) -> Path:
        """索引跟着账本走：接管的账本也把 vector.sqlite 放在自己的目录里（票 21）。"""
        return self.ledgers.get(user).root / "vector.sqlite"

    def _connect(self, user: dict):
        db = sqlite3.connect(self.path(user))
        db.execute(
            "CREATE TABLE IF NOT EXISTS vectors(id TEXT PRIMARY KEY, content TEXT NOT NULL, embedding TEXT NOT NULL)"
        )
        return db

    async def _add(self, user: dict, contents: list[str]) -> None:
        try:
            vectors = await self.embedder.embed(contents)
            with self._connect(user) as db:
                for content, vector in zip(contents, vectors):
                    identifier = hashlib.sha256(content.encode()).hexdigest()
                    db.execute(
                        "INSERT OR REPLACE INTO vectors VALUES(?,?,?)",
                        (identifier, content, json.dumps(vector)),
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            self.log.exception("增量向量写入失败，账本写入不受影响")

    def add_in_background(self, user: dict, contents: list[str]) -> None:
        if not self.settings.embedding_enabled or not contents:
            return
        task = asyncio.create_task(self._add(user, contents))
        tasks = self._pending.setdefault(str(user["id"]), set())
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    async def search(self, user: dict, text: str, limit: int = 5) -> list[str]:
        if not self.settings.embedding_enabled:
            return []
        pending = tuple(self._pending.get(str(user["id"]), ()))
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        try:
            query = (await self.embedder.embed([text]))[0]
            with self._connect(user) as db:
                rows = db.execute("SELECT content,embedding FROM vectors").fetchall()
        except asyncio.CancelledError:
            raise
        except Exception:
            # 相似历史只是抽取时的参考。召回挂了就少给几个例子，不能让人记不了账。
            self.log.exception("向量召回失败，本次抽取不带相似历史")
            return []

        def similarity(raw: str) -> float:
            vector = json.loads(raw)
            denominator = math.sqrt(sum(x * x for x in query)) * math.sqrt(
                sum(x * x for x in vector)
            )
            return (
                sum(x * y for x, y in zip(query, vector)) / denominator
                if denominator
                else 0
            )

        return [
            content
            for content, _ in sorted(
                rows, key=lambda row: similarity(row[1]), reverse=True
            )[:limit]
        ]

    def rebuild_in_background(self, user: dict) -> dict:
        current = self._rebuilds.get(user["id"])
        if current and current["status"] == "running":
            return self._public(current)
        status: dict[str, Any] = {"status": "running", "completed": 0, "total": 0}
        self._rebuilds[user["id"]] = status

        async def rebuild():
            try:
                ledger = self.ledgers.get(user)
                contents = [
                    ledger.render_entry(transaction)
                    for transaction in ledger.transactions
                ]
                status["total"] = len(contents)
                with self._connect(user) as db:
                    db.execute("DELETE FROM vectors")
                for offset in range(
                    0, len(contents), self.settings.embedding_batch_size
                ):
                    batch = contents[
                        offset : offset + self.settings.embedding_batch_size
                    ]
                    await self._add(user, batch)
                    status["completed"] = int(status["completed"]) + len(batch)
                status["status"] = "complete"
            except asyncio.CancelledError:
                # 中断留下的是已写入的一部分；重跑会先清空再写，所以幂等。
                status["status"] = "cancelled"
                raise
            except Exception as exc:
                status.update(status="failed", error=str(exc))

        status["task"] = asyncio.create_task(rebuild())
        return self._public(status)

    def cancel_rebuild(self, user_id: str) -> dict:
        current = self._rebuilds.get(user_id)
        if current and current.get("task") and not current["task"].done():
            current["task"].cancel()
        return self.status(user_id)

    def status(self, user_id: str) -> dict:
        return self._public(
            self._rebuilds.get(user_id, {"status": "idle", "completed": 0, "total": 0})
        )

    @staticmethod
    def _public(status: dict) -> dict:
        return {key: value for key, value in status.items() if key != "task"}

    def is_empty(self, user: dict) -> bool:
        with self._connect(user) as db:
            return db.execute("SELECT COUNT(*) FROM vectors").fetchone()[0] == 0
