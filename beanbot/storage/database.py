"""带版本迁移的 SQLite 存储，保存用户、运行轨迹与常用查询等非账务数据。"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from beanbot.exceptions import NotFound


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path, *, conversation_title_auto_length: int = 10):
        """
        schema_version 只有一列 version
        记录哪些迁移文件已经执行过，保证每个迁移只跑一次
        遍历 migrations/*.sql, 取出编号
        """
        self.path = path
        self.conversation_title_auto_length = conversation_title_auto_length
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
            db.execute(
                "UPDATE runs SET status='interrupted' WHERE status='running'"
            )  # 将异常退出留下的 running 记录改为 interrupted

    @contextmanager
    # with 要求后面的对象是上下文管理器, 所以要加上 contextmanager
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
        """
        读 rows
        返回 list[dict]，每一行转成一个字典
        """
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, params)]

    def execute(self, sql: str, params=()):
        with self.connect() as db:
            db.execute(sql, params)

    def invite(self, code: str):
        """
        将邀请码写入 invite_codes 之中
        没有传入信息也不会报错
        """
        self.execute(
            "INSERT OR IGNORE INTO invite_codes(code,created_at) VALUES(?,?)",
            (code, now()),
        )

    def add_step(
        self, run_id: str, kicker: str, title: str, payload: dict, duration_ms: int = 0
    ) -> dict:
        """为一次运行追加一条步骤记录, 序号在该运行内自动递增
        Args:
            run_id: 所属运行的id
            kicker: 步骤类别，取值为 CLASSIFY, PARSE, ASK, TOOL, REPLY 之一
            title: 步骤标题，展示在时间线上
                示例: "识别意图", "写入账本"
            payload: 该节点的输出，序列化为 JSON 后存储
            duration_ms: 节点耗时
        Returns:
            新建的步骤字典， 包含 id, seq, created_at 等字段
        """
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")  # 立即拿到数据库的写锁
            seq = db.execute(
                "SELECT COALESCE(MAX(seq),0)+1 FROM run_steps WHERE run_id=?",
                (run_id,),  # 查出这个 run 当前最大的序号再加 1,没有记录就从 1 开始
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
        """创建一条"待确认写入"记录
        Args:
            kind: record 表示记一笔交易, budget 表示设置预算
            payload: 要写入的内容, 比如交易列表，或预算的账户、金额、周期
            status: 新建时固定是 pending
            commit_sha / resolved_at: 新建时还没确认, 确认时才会填上
        """
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
        """按 id 取出当前用户的一条待确认写入。
        不按 status 过滤，'pending','confirmed','rejected','expired' 都会返回， 由调用方判断状态
        Args:
            pending_id: 待确认写入的id.
            user_id: 当前用户id， 用于保证只能读到自己的记录
        Returns:
            pending_writes 表中的一行，payloa 已从JSON字符串还原为字典, 找不到时返回 None
            示例：{"id": "abc123", "kind": "record", "status": "pending","payload": {"transactions": [...]}, ...}。
        """
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
        """把一条待确认写入标记为终态，并记下结案时间。只改 status / commit_sha / resolved_at，不动 payload
        Args:
            pending_id: 待确认写入的id.
            status: 终态，'confirmed' / 'rejected' / 'expired' 之一
            commit: 写入账本后的 git 提交 sha，只有 confirmed 时传入，其余为 None
        """
        self.execute(
            "UPDATE pending_writes SET status=?,commit_sha=?,resolved_at=? WHERE id=? AND status=?",
            (status, commit, now(), pending_id, "pending"),
        )

    def session(self, user_id: str, thread_id: str, message: str = "") -> dict:
        """按 thread_id 取出当前用户的对话框，没有就新建一个。
        Args:
            user_id: 当前用户id
            thread_id: 对话框id，由前端新建对话时生成
            message: 只在新建时用，取前 20 个字作为标题，为空时为"新对话"
        Returns:
            sessions 表中的一行，其中：
                active_run_id: 暂停中、等用户回答追问的 run；ChatService 收到 ask 时写入，run 结束后清空
                pending_at: 追问开始的时间，用来判断是否超过 24 小时
                last_active_at: 新建时为当前时间，之后每次 run 结束或暂停，由 ChatService 更新
            示例：{"id": "s1", "thread_id": "t1", "title": "午饭 38，微信", "active_run_id": None, ...}
        """
        rows = self.rows(
            "SELECT * FROM sessions WHERE user_id=? AND thread_id=?",
            (user_id, thread_id),
        )
        if rows:
            if rows[0]["deleted_at"] is not None:
                raise NotFound("对话不存在")
            return rows[0]
        session = {
            "id": uuid4().hex,
            "user_id": user_id,
            "thread_id": thread_id,
            "title": message[:self.conversation_title_auto_length] if message else "新对话",
            "created_at": now(),
            "last_active_at": now(),
            "active_run_id": None,
            "pending_at": None,
        }
        self.execute(
            "INSERT INTO sessions(id,user_id,thread_id,title,created_at,last_active_at,active_run_id,pending_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            tuple(session.values()),
        )
        return session

    def rename_session(self, user_id: str, thread_id: str, title: str) -> bool:
        """只改当前用户仍存在的对话标题，不改变活跃顺序。"""
        with self.connect() as db:
            return db.execute(
                "UPDATE sessions SET title=? WHERE user_id=? AND thread_id=? AND deleted_at IS NULL",
                (title, user_id, thread_id),
            ).rowcount == 1

    def delete_session(self, user_id: str, thread_id: str) -> bool:
        """软删除与丢弃待确认写入在同一事务中完成，保留其余审计数据。"""
        timestamp = now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE sessions SET deleted_at=? WHERE user_id=? AND thread_id=? AND deleted_at IS NULL",
                (timestamp, user_id, thread_id),
            ).rowcount
            if not changed:
                return False
            db.execute(
                "UPDATE pending_writes SET status='rejected',resolved_at=? "
                "WHERE user_id=? AND status='pending' AND run_id IN ("
                "SELECT r.id FROM runs r JOIN sessions s ON s.id=r.session_id "
                "WHERE s.user_id=? AND s.thread_id=?)",
                (timestamp, user_id, user_id, thread_id),
            )
            return True

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
            return (
                db.execute(
                    "DELETE FROM saved_queries WHERE id=? AND user_id=?",
                    (query_id, user_id),
                ).rowcount
                == 1
            )

    def finish_run(
        self, run_id: str, status: str, total_ms: int, intent: str | None = None
    ) -> None:
        self.execute(
            "UPDATE runs SET status=?,total_ms=?,intent=COALESCE(?,intent),updated_at=? WHERE id=?",
            (status, total_ms, intent, now(), run_id),
        )

    def run(self, run_id: str, user_id: str) -> dict | None:
        """按id取一条run"""
        rows = self.rows(
            "SELECT * FROM runs WHERE id=? AND user_id=?", (run_id, user_id)
        )
        return rows[0] if rows else None

    def count_runs(
        self, user_id: str, intent: str | None = None, asked: bool = False
    ) -> int:
        """统计满足筛选条件的 run 总数"""
        clauses, params = self._run_filters(user_id, intent, asked)
        return self.rows(
            f"SELECT COUNT(*) AS total FROM runs r WHERE {clauses}", params
        )[0]["total"]

    @staticmethod
    def _run_filters(
        user_id: str, intent: str | None, asked: bool
    ) -> tuple[str, list[object]]:
        """拼出筛选条件, 给上面两个共用"""
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
        """分页列出某用户的 run, 可以筛选"""
        clauses, params = self._run_filters(user_id, intent, asked)
        params.extend([size, (page - 1) * size])
        return self.rows(
            f"SELECT r.* FROM runs r WHERE {clauses} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        )
