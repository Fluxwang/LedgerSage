"""带版本迁移的 SQLite 存储，保存用户、运行轨迹与常用查询等非账务数据。"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(
            parents=True, exist_ok=True
        )  # parents 相当于 mkdir -p, exist_ok 文件已经存在也不报错
        with self.connect() as db:
            # 将 SQLite 切换为 WAL 模式，让读和写可以同时进行
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY)"
            )
            applied = {
                row[0] for row in db.execute("SELECT version FROM schema_version")
            }
            migration_dir = Path(__file__).with_name("migrations")
            for migration in sorted(migration_dir.glob("*.sql")):
                version = int(migration.stem.split("_", 1)[0])
                if version not in applied:
                    db.executescript(migration.read_text(encoding="utf-8"))
                    db.execute("INSERT INTO schema_version VALUES(?)", (version,))
            db.execute("UPDATE runs SET status='interrupted' WHERE status='running'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def rows(self, sql: str, params=()) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, params)]

    def execute(self, sql: str, params=()):
        with self.connect() as db:
            db.execute(sql, params)

    def invite(self, code: str):
        self.execute(
            "INSERT OR IGNORE INTO invite_codes(code,created_at) VALUES(?,?)",
            (code, now()),
        )

    def add_step(
        self, run_id: str, kicker: str, title: str, payload: dict, duration_ms: int = 0
    ) -> dict:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            seq = db.execute(
                "SELECT COALESCE(MAX(seq),0)+1 FROM run_steps WHERE run_id=?", (run_id,)
            ).fetchone()[0]
            step = dict(
                id=uuid4().hex,
                run_id=run_id,
                seq=seq,
                kicker=kicker,
                title=title,
                duration_ms=duration_ms,
                payload=payload,
                created_at=now(),
            )
            db.execute(
                "INSERT INTO run_steps VALUES(?,?,?,?,?,?,?,?)",
                (
                    step["id"],
                    run_id,
                    seq,
                    kicker,
                    title,
                    duration_ms,
                    json.dumps(payload, ensure_ascii=False, default=str),
                    step["created_at"],
                ),
            )
            return step

    def steps(self, run_id: str) -> list[dict]:
        rows = self.rows(
            "SELECT * FROM run_steps WHERE run_id=? ORDER BY seq", (run_id,)
        )
        for row in rows:
            row["payload"] = json.loads(row["payload"])
        return rows

    def create_pending(
        self,
        user_id: str,
        run_id: str | None,
        kind: str,
        payload: dict,
        pending_id: str | None = None,
    ) -> dict:
        record = {
            "id": pending_id or uuid4().hex,
            "user_id": user_id,
            "run_id": run_id,
            "kind": kind,
            "payload": payload,
            "status": "pending",
            "commit_sha": None,
            "created_at": now(),
            "resolved_at": None,
        }
        self.execute(
            "INSERT INTO pending_writes VALUES(?,?,?,?,?,?,?,?,?)",
            (
                record["id"],
                user_id,
                run_id,
                kind,
                json.dumps(payload, ensure_ascii=False, default=str),
                "pending",
                None,
                record["created_at"],
                None,
            ),
        )
        return record

    def pending(self, pending_id: str, user_id: str) -> dict | None:
        rows = self.rows(
            "SELECT * FROM pending_writes WHERE id=? AND user_id=?",
            (pending_id, user_id),
        )
        if not rows:
            return None
        rows[0]["payload"] = json.loads(rows[0]["payload"])
        return rows[0]

    def resolve_pending(
        self, pending_id: str, status: str, commit: str | None = None
    ) -> None:
        self.execute(
            "UPDATE pending_writes SET status=?,commit_sha=?,resolved_at=? WHERE id=? AND status=?",
            (status, commit, now(), pending_id, "pending"),
        )

    def session(self, user_id: str, thread_id: str) -> dict:
        rows = self.rows(
            "SELECT * FROM sessions WHERE user_id=? AND thread_id=?",
            (user_id, thread_id),
        )
        if rows:
            return rows[0]
        session = {
            "id": uuid4().hex,
            "user_id": user_id,
            "thread_id": thread_id,
            "title": "新对话",
            "created_at": now(),
            "last_active_at": now(),
            "active_run_id": None,
            "pending_at": None,
        }
        self.execute(
            "INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?)",
            tuple(session.values()),
        )
        return session

    def create_run(self, session: dict, user_id: str, model: str, message: str) -> dict:
        timestamp = now()
        run = {
            "id": uuid4().hex,
            "session_id": session["id"],
            "user_id": user_id,
            "intent": None,
            "status": "running",
            "model": model,
            "total_ms": 0,
            "total_tokens": 0,
            "created_at": timestamp,
            "updated_at": timestamp,
            "title": message[:60],
            "message": message,
        }
        self.execute(
            "INSERT INTO runs(id,session_id,user_id,intent,status,model,total_ms,total_tokens,created_at,updated_at,title,message) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            tuple(run.values()),
        )
        return run

    def saved_queries(self, user_id: str) -> list[dict]:
        return self.rows(
            "SELECT id,question,created_at FROM saved_queries WHERE user_id=? "
            "ORDER BY created_at DESC,id DESC",
            (user_id,),
        )

    def save_query(self, user_id: str, run: dict) -> dict:
        with self.connect() as db:
            # 唯一约束和同一事务让并发收藏也返回同一条记录。
            db.execute(
                "INSERT INTO saved_queries(id,user_id,question,run_id,created_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(user_id,question) DO NOTHING",
                (uuid4().hex, user_id, run["message"], run["id"], now()),
            )
            return dict(
                db.execute(
                    "SELECT id,question,created_at FROM saved_queries WHERE user_id=? AND question=?",
                    (user_id, run["message"]),
                ).fetchone()
            )

    def delete_saved_query(self, query_id: str, user_id: str) -> bool:
        with self.connect() as db:
            return db.execute(
                "DELETE FROM saved_queries WHERE id=? AND user_id=?", (query_id, user_id)
            ).rowcount == 1

    def finish_run(
        self, run_id: str, status: str, total_ms: int, intent: str | None = None
    ) -> None:
        self.execute(
            "UPDATE runs SET status=?,total_ms=?,intent=COALESCE(?,intent),updated_at=? WHERE id=?",
            (status, total_ms, intent, now(), run_id),
        )

    def run(self, run_id: str, user_id: str) -> dict | None:
        rows = self.rows(
            "SELECT * FROM runs WHERE id=? AND user_id=?", (run_id, user_id)
        )
        return rows[0] if rows else None

    def count_runs(
        self, user_id: str, intent: str | None = None, asked: bool = False
    ) -> int:
        clauses, params = self._run_filters(user_id, intent, asked)
        return self.rows(
            f"SELECT COUNT(*) AS total FROM runs r WHERE {clauses}", params
        )[0]["total"]

    @staticmethod
    def _run_filters(
        user_id: str, intent: str | None, asked: bool
    ) -> tuple[str, list[object]]:
        clauses = ["r.user_id=?"]
        params: list[object] = [user_id]
        if intent:
            clauses.append("r.intent=?")
            params.append(intent)
        if asked:
            clauses.append(
                "EXISTS(SELECT 1 FROM run_steps s WHERE s.run_id=r.id AND s.kicker='ASK')"
            )
        return " AND ".join(clauses), params

    def runs(
        self,
        user_id: str,
        page: int = 1,
        size: int = 20,
        intent: str | None = None,
        asked: bool = False,
    ) -> list[dict]:
        clauses, params = self._run_filters(user_id, intent, asked)
        params.extend([size, (page - 1) * size])
        return self.rows(
            f"SELECT r.* FROM runs r WHERE {clauses} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        )
