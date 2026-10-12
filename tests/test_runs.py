"""决策历史：运行标题自动生成，过滤器与详情返回真实轨迹。"""

import json

from fastapi.testclient import TestClient

from beanbot.api.app import create_app
from beanbot.services.agent.classify import Classification
from tests.test_api import settings
from tests.test_dashboard import register
from tests.test_graph import FixtureModel


class RoutingFixtureModel(FixtureModel):
    async def classify(self, message, history):
        if "多少" in message:
            return Classification(intent="query", confidence=0.95)
        return Classification(intent="record", confidence=0.95)


def converse(client, headers, thread: str, message: str) -> list[dict]:
    response = client.post(
        "/chat/stream", headers=headers, json={"message": message, "thread_id": thread}
    )
    assert response.status_code == 200
    return [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]


def test_run_titles_filters_and_detail(tmp_path):
    app = create_app(settings(tmp_path), agent_model=RoutingFixtureModel())
    with TestClient(app) as client:
        headers = register(client)
        asked = converse(client, headers, "thread-record", "火锅128")
        assert asked[-1]["type"] == "ask"
        converse(client, headers, "thread-record", "微信")
        converse(client, headers, "thread-query", "这个月餐饮花了多少")

        every = client.get("/runs", headers=headers).json()
        with_ask = client.get("/runs?asked=true", headers=headers).json()
        queries = client.get("/runs?intent=query", headers=headers).json()
        page_two = client.get("/runs?size=1&page=2", headers=headers).json()
        detail = client.get(
            f"/runs/{with_ask['rows'][0]['id']}", headers=headers
        ).json()
        missing = client.get("/runs/does-not-exist", headers=headers)

    assert [run["title"] for run in every["rows"]] == [
        "查询账本",
        "记录火锅店支出（含追问）",
    ]
    assert every["total"] == 2
    assert [run["id"] for run in with_ask["rows"]] == [every["rows"][1]["id"]]
    assert with_ask["total"] == 1
    assert [run["title"] for run in queries["rows"]] == ["查询账本"]
    assert [run["title"] for run in page_two["rows"]] == ["记录火锅店支出（含追问）"]
    assert [step["kicker"] for step in detail["steps"]].count("ASK") == 1
    assert all(step["run_id"] == detail["id"] for step in detail["steps"])
    assert missing.status_code == 404


def test_runs_are_scoped_to_the_owner(tmp_path):
    app = create_app(settings(tmp_path), agent_model=RoutingFixtureModel())
    with TestClient(app) as client:
        headers = register(client)
        converse(client, headers, "thread-query", "这个月餐饮花了多少")
        app.state.db.execute(
            "INSERT INTO invite_codes(code,created_at) VALUES(?,?)",
            ("second", "2026-01-01"),
        )
        other = client.post(
            "/auth/register",
            json={
                "username": "other",
                "password": "correct-horse",
                "invite_code": "second",
            },
        ).json()["access_token"]

        mine = client.get("/runs", headers=headers).json()
        theirs = client.get(
            "/runs", headers={"Authorization": f"Bearer {other}"}
        ).json()
        cross = client.get(
            f"/runs/{mine['rows'][0]['id']}",
            headers={"Authorization": f"Bearer {other}"},
        )

    assert mine["total"] == 1 and theirs["rows"] == [] and theirs["total"] == 0
    assert cross.status_code == 404
