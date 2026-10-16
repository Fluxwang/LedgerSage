"""把一次图运行包装成可恢复、可持久化的 SSE 事件序列。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any

from langgraph.types import Command

from beanbot.services.agent.graph import AgentGraph
from beanbot.storage.database import Database, now


class ChatService:
    def __init__(self, database: Database, graph: AgentGraph, model_name: str):
        self.database = database
        self.graph = graph
        self.model_name = model_name

    async def stream(
        self, user: dict, thread_id: str, message: str
    ) -> AsyncIterator[dict]:
        graph_input: Any
        session = self.database.session(user["id"], thread_id, message)
        active_run_id = session.get("active_run_id")
        pending_at = session.get("pending_at")
        resumed = False
        if active_run_id and pending_at:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(pending_at)
            if age <= timedelta(hours=24):
                runs = self.database.rows(
                    "SELECT * FROM runs WHERE id=? AND user_id=?",
                    (active_run_id, user["id"]),
                )
                if runs:
                    run = runs[0]
                    self.database.execute(
                        "UPDATE runs SET status='running',updated_at=? WHERE id=?",
                        (now(), run["id"]),
                    )
                    graph_input = Command(resume=message)
                    resumed = True
            else:
                self.database.finish_run(
                    active_run_id,
                    "failed",
                    0,
                )
                self.database.execute(
                    "UPDATE sessions SET active_run_id=NULL,pending_at=NULL,last_active_at=? WHERE id=?",
                    (now(), session["id"]),
                )
                yield {
                    "type": "message",
                    "content": "上一次追问已超过 24 小时，本条消息将作为新的运行处理。",
                }
        if not resumed:
            run = self.database.create_run(
                session, user["id"], self.model_name, message
            )
            graph_input = {
                "message": message,
                "history": [],
                "user": user,
                "run_id": run["id"],
                "bounce_count": 0,
            }
        started = perf_counter()
        graph_thread_id = f"{user['id']}:{run['id']}"
        try:
            async for event in self.graph.stream(graph_input, graph_thread_id):
                event["run_id"] = run["id"]
                event["model"] = self.model_name
                event["total_ms"] = int((perf_counter() - started) * 1000)
                event["total_tokens"] = run.get("total_tokens", 0)
                yield event
                if event["type"] == "ask":
                    self.database.execute(
                        "UPDATE sessions SET active_run_id=?,pending_at=?,last_active_at=? WHERE id=?",
                        (run["id"], now(), now(), session["id"]),
                    )
                    self.database.finish_run(
                        run["id"],
                        "clarification",
                        int((perf_counter() - started) * 1000),
                    )
                    return
            self.database.execute(
                "UPDATE sessions SET active_run_id=NULL,pending_at=NULL,last_active_at=? WHERE id=?",
                (now(), session["id"]),
            )
            current = self.database.rows(
                "SELECT intent FROM runs WHERE id=?", (run["id"],)
            )[0]
            self.database.finish_run(
                run["id"],
                "success",
                int((perf_counter() - started) * 1000),
                current.get("intent"),
            )
        except asyncio.CancelledError:
            self.database.finish_run(
                run["id"], "interrupted", int((perf_counter() - started) * 1000)
            )
        except Exception:
            self.database.finish_run(
                run["id"], "failed", int((perf_counter() - started) * 1000)
            )
            raise
