from uuid import uuid4

from langgraph.types import Command

from beanbot.services.chat_service import ChatService
from beanbot.storage.database import Database, now
from tests.test_api import settings


class ClarificationGraph:
    """只模拟图的公开事件协议；数据库与 ChatService 均使用真实实现。"""

    async def stream(self, input_state, graph_thread_id):
        if isinstance(input_state, Command):
            yield {"type": "receipt", "pending_id": "pending-1", "entries": ["preview"]}
            yield {"type": "done"}
            return
        yield {
            "type": "ask",
            "question": "请选择付款账户",
            "candidates": ["Assets:DebitCard:CN:PINGAN-6479"],
        }


async def test_numbered_account_answer_resumes_the_pending_run(tmp_path):
    config = settings(tmp_path)
    database = Database(config.database_path)
    user = {"id": uuid4().hex, "username": "mark", "ledger_path": None}
    database.execute(
        "INSERT INTO users VALUES(?,?,?,?,?)",
        (user["id"], user["username"], "unused", None, now()),
    )
    service = ChatService(database, ClarificationGraph(), "fixture")

    first = [event async for event in service.stream(user, "thread-1", "潮汕砂锅菜 11 元")]
    run_id = first[-1]["run_id"]
    second = [
        event
        async for event in service.stream(
            user, "thread-1", "Assets:DebitCard:CN:PINGAN-6479"
        )
    ]

    assert [event["type"] for event in second] == ["receipt", "done"]
    assert {event["run_id"] for event in second} == {run_id}