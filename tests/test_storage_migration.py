"""已有运行数据库升级后仍可读取，新增迁移可重复启动。"""

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from beanbot.api.app import create_app
from beanbot.storage.database import Database
from tests.test_api import settings
from tests.test_dashboard import register
from tests.test_runs import RoutingFixtureModel, converse


def test_upgrade_preserves_old_runs_and_adds_saved_queries(tmp_path):
    config = settings(tmp_path)
    config.database_path.parent.mkdir(parents=True, exist_ok=True)
    migrations = Path("beanbot/storage/migrations")
    with sqlite3.connect(config.database_path) as db:
        db.execute("CREATE TABLE schema_version(version INTEGER PRIMARY KEY)")
        for migration in sorted(migrations.glob("00[12]_*.sql")):
            db.executescript(migration.read_text(encoding="utf-8"))
            db.execute("INSERT INTO schema_version VALUES(?)", (int(migration.stem[:3]),))
        db.execute("INSERT INTO users VALUES('legacy','legacy','unused',NULL,'2026-01-01')")
        db.execute("INSERT INTO sessions VALUES('session','legacy','thread','旧对话','2026-01-01','2026-01-01',NULL,NULL)")
        db.execute("INSERT INTO runs VALUES('old-run','session','legacy','query','success','fixture',0,0,'2026-01-01','2026-01-01','查询账本')")

    database = Database(config.database_path)
    old = database.run("old-run", "legacy")
    assert old["message"] is None and old["title"] == "查询账本"
    app = create_app(config, agent_model=RoutingFixtureModel())
    with TestClient(app) as client:
        headers = register(client)
        user_id = client.get("/auth/me", headers=headers).json()["id"]
        app.state.db.execute("UPDATE runs SET user_id=? WHERE id='old-run'", (user_id,))
        assert client.get("/runs/old-run", headers=headers).json()["message"] is None
        assert client.post("/saved-queries", headers=headers, json={"run_id": "old-run"}).status_code == 400
        events = converse(client, headers, "new", "这个月花了多少")
        response = client.post("/saved-queries", headers=headers, json={"run_id": events[-1]["run_id"]})
        assert response.status_code == 200
    reopened = Database(config.database_path)
    assert reopened.run("old-run", user_id)["message"] is None
    assert len(reopened.rows("SELECT * FROM saved_queries")) == 1
