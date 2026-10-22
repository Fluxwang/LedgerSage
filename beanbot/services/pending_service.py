"""待确认写入：Agent 产出的 diff 在这里才真正落盘（ADR 0012）。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from pydantic import ValidationError

from beanbot.exceptions import LedgerWriteConflict, NotFound
from beanbot.gateways.ledger import LedgerFactory, TransactionInput
from beanbot.services.agent.accounts import FIELDS, normalize, preview_accounts
from beanbot.services.vector_index import VectorIndexManager
from beanbot.storage.database import Database

# 超过这个时间的预览不再放行：账本可能已经变了，照着旧预览落盘会写出与预览不符的东西。
PENDING_TTL = timedelta(hours=24)


class PendingWriteService:
    def __init__(
        self,
        database: Database,
        ledgers: LedgerFactory,
        vectors: VectorIndexManager | None = None,
    ):
        self.database = database
        self.ledgers = ledgers
        self.vectors = vectors
        self._confirming: set[str] = set()

    def _load(self, user: dict, pending_id: str) -> dict:
        if pending_id in self._confirming:
            raise LedgerWriteConflict("正在确认这条写入，请稍后重试")
        record = self.database.pending(pending_id, user["id"])
        if not record:
            raise NotFound("找不到这条待确认写入")
        if record["status"] != "pending":
            raise LedgerWriteConflict(
                f"这条写入已经{STATUS_LABELS[record['status']]}了"
            )
        age = datetime.now(timezone.utc) - datetime.fromisoformat(record["created_at"])
        if age > PENDING_TTL:
            self.database.resolve_pending(pending_id, "expired")
            raise LedgerWriteConflict("这条待确认写入已经超过 24 小时，请重新记一次")
        return record

    def edit(
        self, user: dict, pending_id: str, index: int, accounts: dict[str, str]
    ) -> dict:
        record = self._load(user, pending_id)
        if record["kind"] != "record":
            raise LedgerWriteConflict("只有交易的待确认写入可以修改账户")
        transactions = record["payload"]["transactions"]
        if (
            not 0 <= index < len(transactions)
            or not accounts
            or any(field not in FIELDS for field in accounts)
        ):
            raise LedgerWriteConflict("请选择有效交易和账户")
        changed = transactions[index] | accounts
        changed["autofilled"] = [
            field
            for field in transactions[index].get("autofilled", [])
            if field not in accounts
        ]
        changed = normalize(changed)
        transactions[index] = changed
        if any(
            (item.get(field) or "").startswith("Equity:")
            for item in transactions
            for field in FIELDS
        ):
            raise LedgerWriteConflict("对话记账不支持权益账户，请在账本里手写")
        ledger = self.ledgers.get(user)
        try:
            preview = ledger.preview(
                [TransactionInput.model_validate(item) for item in transactions]
            )
        except ValidationError as exc:
            raise LedgerWriteConflict("账户组合不能表示有效资金流向") from exc
        payload = record["payload"] | {"transactions": transactions}
        self.database.execute(
            "UPDATE pending_writes SET payload=? WHERE id=? AND user_id=? AND status=?",
            (
                json.dumps(payload, ensure_ascii=False),
                pending_id,
                user["id"],
                "pending",
            ),
        )
        return preview | {
            "pending_id": pending_id,
            "transactions": preview_accounts(
                ledger,
                transactions,
                self.ledgers.settings.clarification_candidate_limit,
            ),
        }

    async def confirm(self, user: dict, pending_id: str) -> dict:
        record = self._load(user, pending_id)
        self._confirming.add(pending_id)
        try:
            return await self._confirm(user, pending_id, record)
        finally:
            self._confirming.discard(pending_id)

    async def _confirm(self, user: dict, pending_id: str, record: dict) -> dict:
        ledger = self.ledgers.get(user)
        payload = record["payload"]
        # 落盘前重新校验一遍，而不是信任预览时的结论——两次之间账本可能被改过。
        if record["kind"] == "record":
            transactions = [
                TransactionInput.model_validate(item)
                for item in payload["transactions"]
            ]
            receipt = await ledger.insert(transactions)
            if self.vectors:
                self.vectors.add_in_background(user, receipt["entries"])
        else:
            receipt = await ledger.set_budget(
                payload["account"],
                Decimal(str(payload["amount"])),
                payload.get("period", "monthly"),
            ) | {"account": payload["account"]}
        self.database.resolve_pending(pending_id, "confirmed", receipt["commit"])
        return receipt | {"pending_id": pending_id, "status": "confirmed"}

    def reject(self, user: dict, pending_id: str) -> dict:
        self._load(user, pending_id)
        self.database.resolve_pending(pending_id, "rejected")
        return {"pending_id": pending_id, "status": "rejected"}


STATUS_LABELS = {"confirmed": "写入账本", "rejected": "丢弃", "expired": "过期"}
