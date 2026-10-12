import asyncio
import subprocess

import pytest
from pydantic import SecretStr
from datetime import date
from decimal import Decimal
from uuid import uuid4

from beanbot.gateways.ledger import LedgerFactory, TransactionInput, scaffold_ledger
from beanbot.services.vector_index import VectorIndexManager
from tests.test_api import settings


class FixtureEmbedder:
    async def embed(self, texts):
        return [[float("火锅" in text), float("咖啡" in text), 1.0] for text in texts]


class SlowEmbedder(FixtureEmbedder):
    async def embed(self, texts):
        await asyncio.sleep(0.05)
        return await super().embed(texts)


class FailingEmbedder:
    async def embed(self, texts):
        raise RuntimeError("embedding 服务不可用")


def user(**overrides) -> dict:
    return {"id": uuid4().hex, "ledger_path": None} | overrides


async def transactions(ledger, count: int) -> None:
    await ledger.insert(
        [
            TransactionInput(
                amount=Decimal(index + 1),
                date=date(2026, 9, 9),
                payee=f"商户{index}",
                from_account="Assets:Cash",
                to_account="Expenses:Other",
            )
            for index in range(count)
        ],
        today=date(2026, 9, 9),
    )


async def test_vector_indexes_are_isolated_and_incremental(tmp_path):
    config = settings(tmp_path).model_copy(update={"embedding_enabled": True})
    manager = VectorIndexManager(config, LedgerFactory(config), FixtureEmbedder())
    one, two = user(), user()
    manager.add_in_background(one, ["火锅 微信"])
    manager.add_in_background(two, ["咖啡 现金"])
    assert await manager.search(one, "火锅") == ["火锅 微信"]
    assert await manager.search(two, "火锅") == ["咖啡 现金"]
    assert manager.path(one) != manager.path(two)


async def test_index_follows_a_taken_over_ledger(tmp_path):
    config = settings(tmp_path).model_copy(update={"embedding_enabled": True})
    elsewhere = tmp_path / "somewhere-else"
    scaffold_ledger(elsewhere)
    taken_over = user(ledger_path=str(elsewhere))
    manager = VectorIndexManager(config, LedgerFactory(config), FixtureEmbedder())

    manager.add_in_background(taken_over, ["火锅 微信"])
    await asyncio.gather(*manager._pending[taken_over["id"]])

    assert manager.path(taken_over) == elsewhere.resolve() / "vector.sqlite"
    assert not (config.ledger_root / taken_over["id"]).exists()
    # 索引是派生数据，落在账本目录里但不能弄脏用户账本的 git 工作区。
    dirty = subprocess.check_output(
        ["git", "-C", str(elsewhere), "status", "--short"], text=True
    )
    assert dirty == ""


async def test_full_rebuild_covers_every_transaction_and_is_repeatable(tmp_path):
    config = settings(tmp_path).model_copy(
        update={"embedding_enabled": True, "embedding_batch_size": 32}
    )
    ledgers = LedgerFactory(config)
    owner = user()
    await transactions(ledgers.get(owner), 205)
    manager = VectorIndexManager(config, ledgers, FixtureEmbedder())

    first = manager.rebuild_in_background(owner)
    await manager._rebuilds[owner["id"]]["task"]
    assert first == {"status": "running", "completed": 0, "total": 0}
    assert manager.status(owner["id"]) == {
        "status": "complete",
        "completed": 205,
        "total": 205,
    }
    assert not manager.is_empty(owner)

    manager.rebuild_in_background(owner)
    await manager._rebuilds[owner["id"]]["task"]
    with manager._connect(owner) as db:
        assert db.execute("SELECT COUNT(*) FROM vectors").fetchone()[0] == 205


async def test_rebuild_can_be_cancelled_and_rerun(tmp_path):
    config = settings(tmp_path).model_copy(
        update={"embedding_enabled": True, "embedding_batch_size": 1}
    )
    ledgers = LedgerFactory(config)
    owner = user()
    await transactions(ledgers.get(owner), 8)
    manager = VectorIndexManager(config, ledgers, SlowEmbedder())

    manager.rebuild_in_background(owner)
    await asyncio.sleep(0.06)
    assert manager.cancel_rebuild(owner["id"])["status"] in ("running", "cancelled")
    task = manager._rebuilds[owner["id"]]["task"]
    await asyncio.gather(task, return_exceptions=True)
    assert manager.status(owner["id"])["status"] == "cancelled"

    manager.rebuild_in_background(owner)
    await manager._rebuilds[owner["id"]]["task"]
    assert manager.status(owner["id"]) == {
        "status": "complete",
        "completed": 8,
        "total": 8,
    }
    with manager._connect(owner) as db:
        assert db.execute("SELECT COUNT(*) FROM vectors").fetchone()[0] == 8


async def test_failed_embedding_is_logged_without_breaking_the_write(tmp_path, caplog):
    config = settings(tmp_path).model_copy(update={"embedding_enabled": True})
    manager = VectorIndexManager(config, LedgerFactory(config), FailingEmbedder())
    owner = user()
    manager.add_in_background(owner, ["火锅 微信"])
    await asyncio.gather(*manager._pending[owner["id"]])
    assert manager.is_empty(owner)
    assert "增量向量写入失败" in caplog.text


class RecordingEmbedder:
    """记下每次请求的条数，用来验证切批。"""

    def __init__(self):
        self.batches: list[int] = []

    async def embed(self, texts):
        self.batches.append(len(texts))
        return [[1.0, 0.0, 0.0] for _ in texts]


async def test_search_degrades_when_the_embedding_provider_is_down(tmp_path):
    """召回是抽取的参考项，服务商挂了只能少给例子，不能让记账失败。"""
    config = settings(tmp_path).model_copy(update={"embedding_enabled": True})
    manager = VectorIndexManager(config, LedgerFactory(config), FailingEmbedder())
    assert await manager.search(user(), "火锅") == []


async def test_http_embedder_splits_requests_by_batch_size(tmp_path, monkeypatch):
    """服务商对单次条数有上限，切批要在 embedder 里做，增量路径也得受保护。"""
    from beanbot.services import vector_index

    config = settings(tmp_path).model_copy(
        update={
            "embedding_enabled": True,
            "embedding_batch_size": 20,
            "embedding_base_url": "https://example.invalid/v1",
            "embedding_api_key": SecretStr("k"),
        }
    )
    sent: list[int] = []

    class Response:
        is_error = False

        @staticmethod
        def json():
            return {"data": [{"index": i, "embedding": [1.0]} for i in range(sent[-1])]}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers, json):
            sent.append(len(json["input"]))
            return Response()

    monkeypatch.setattr(vector_index.httpx, "AsyncClient", lambda **kw: Client())
    vectors = await vector_index.HttpEmbedder(config).embed(
        [f"第{i}笔" for i in range(45)]
    )

    assert sent == [20, 20, 5]
    assert len(vectors) == 45


async def test_http_embedder_reports_the_provider_error_body(tmp_path, monkeypatch):
    """raise_for_status 只给 URL 和状态码，真正的原因在响应体里。"""
    from beanbot.services import vector_index

    config = settings(tmp_path).model_copy(
        update={
            "embedding_base_url": "https://example.invalid/v1",
            "embedding_api_key": SecretStr("k"),
        }
    )

    class Response:
        is_error = True
        status_code = 400
        text = '{"code":"InvalidParameter","message":"batch size 32 exceeds limit 20"}'

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers, json):
            return Response()

    monkeypatch.setattr(vector_index.httpx, "AsyncClient", lambda **kw: Client())
    with pytest.raises(vector_index.EmbeddingError, match="exceeds limit 20"):
        await vector_index.HttpEmbedder(config).embed(["火锅"])
