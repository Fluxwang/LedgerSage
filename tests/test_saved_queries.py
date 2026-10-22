"""常用查询通过真实对话生成，HTTP 边界校验意图、去重和用户隔离。"""

from fastapi.testclient import TestClient

from beanbot.api.app import create_app
from beanbot.services.agent.classify import Classification
from tests.test_api import settings
from tests.test_dashboard import register
from tests.test_runs import RoutingFixtureModel, converse


class SavedQueryModel(RoutingFixtureModel):
    async def classify(self, message, history):
        if "预算" in message:
            return Classification(intent="budget", confidence=0.95)
        return await super().classify(message, history)


def test_save_deduplicate_order_delete_and_persist(tmp_path):
    config = settings(tmp_path)
    app = create_app(config, agent_model=SavedQueryModel())
    with TestClient(app) as client:
        headers = register(client)
        assert client.get("/saved-queries", headers=headers).json() == []
        questions = ["这个月餐饮花了多少", "今年花了多少"]
        saved = []
        for index, question in enumerate(questions):
            events = converse(client, headers, f"query-{index}", question)
            response = client.post("/saved-queries", headers=headers, json={"run_id": events[-1]["run_id"]})
            assert response.status_code == 200
            record = response.json()
            assert set(record) == {"id", "question", "created_at"}
            assert record["question"] == question
            saved.append(record)

        # 不同运行的同一句话也只能产生一条收藏。
        events = converse(client, headers, "same-question", questions[0])
        duplicate = client.post("/saved-queries", headers=headers, json={"run_id": events[-1]["run_id"]})
        assert duplicate.json() == saved[0]
        assert client.get("/saved-queries", headers=headers).json() == saved[::-1]

    with TestClient(create_app(config, agent_model=SavedQueryModel())) as client:
        assert client.get("/saved-queries", headers=headers).json() == saved[::-1]
        assert client.delete(f"/saved-queries/{saved[0]['id']}", headers=headers).status_code == 200
        assert client.get("/saved-queries", headers=headers).json() == [saved[1]]
        assert client.delete(f"/saved-queries/{saved[0]['id']}", headers=headers).status_code == 404


def test_reject_unsafe_legacy_foreign_and_invalid_requests(tmp_path):
    app = create_app(settings(tmp_path), agent_model=SavedQueryModel())
    with TestClient(app) as client:
        headers = register(client)
        for index, message in enumerate(["火锅128", "设置餐饮预算2000"]):
            events = converse(client, headers, f"unsafe-{index}", message)
            response = client.post("/saved-queries", headers=headers, json={"run_id": events[-1]["run_id"]})
            assert response.status_code == 400

        events = converse(client, headers, "query", "这个月花了多少")
        run_id = events[-1]["run_id"]
        saved = client.post("/saved-queries", headers=headers, json={"run_id": run_id}).json()
        app.state.db.invite("second")
        registered = client.post("/auth/register", json={"username": "other", "password": "correct-horse", "invite_code": "second"})
        other = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        assert client.get("/saved-queries", headers=other).json() == []
        assert client.post("/saved-queries", headers=other, json={"run_id": run_id}).status_code == 404
        assert client.delete(f"/saved-queries/{saved['id']}", headers=other).status_code == 404
        assert client.get("/saved-queries", headers=headers).json() == [saved]
        assert client.post("/saved-queries", headers=headers, json={"run_id": "missing"}).status_code == 404
        assert client.delete("/saved-queries/missing", headers=headers).status_code == 404
        for message in [None, ""]:
            app.state.db.execute("UPDATE runs SET message=? WHERE id=?", (message, run_id))
            assert client.post("/saved-queries", headers=headers, json={"run_id": run_id}).status_code == 400
        assert client.post("/saved-queries", headers=headers, json={"question": "伪造查询"}).status_code == 422
        assert client.get("/saved-queries").status_code == 401
        assert client.post("/saved-queries", json={"run_id": run_id}).status_code == 401
        assert client.delete(f"/saved-queries/{saved['id']}").status_code == 401
