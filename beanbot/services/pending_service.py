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

    def _load(self, user: dict, pending_id: str) -> dict:
        """取出当前用户一条仍可操作的待确认写入，edit / confirm / reject 都先经过这里。
        超过 PENDING_TTL 的记录会顺手标记为 'expired' 写回库里，之后再访问就按终态拒绝
        Args:
            user: 当前用户，用 user["id"] 保证只能操作自己的记录
            pending_id: 待确认写入的id.
        Returns:
            database.pending 返回的一行，status 一定是 'pending' 且未过期
            示例：{"id": "abc123", "kind": "record", "status": "pending", "payload": {"transactions": [...]}, ...}。
        Raises:
            LedgerWriteConflict: 正在 confirm 中（防止连点重复写入）、已是终态（confirmed / rejected / expired），或刚刚过期
            NotFound: 找不到，或不属于当前用户
        """
        record = self.database.pending(pending_id, user["id"])
        if not record:
            raise NotFound("找不到这条待确认写入")
        if record["status"] == "confirming":
            raise LedgerWriteConflict("正在确认这条写入，请稍后重试")
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
        """修改一条待确认交易里某笔交易的账户，重新预览后把新 payload 存回库里。
        用户手动指定的字段会从 autofilled 里去掉；改完后经 normalize 处理，to_account 是 Income: 时会和 from_account 互换
        Args:
            user: 当前用户，用 user["id"] 保证只能操作自己的记录
            pending_id: 待确认写入的id.
            index: 要修改的交易在 payload["transactions"] 里的下标
            accounts: 要改的账户，key 只能是 from_account / to_account
                示例：{"from_account": "Assets:Bank:CMB"}
        Returns:
            ledger.preview 的结果，再合并上 pending_id 和带 display_names / candidates 的 transactions，供前端刷新 diff 卡
            示例：{"kind": "record", "text": "...", "validations": [...], "pending_id": "abc123", "transactions": [...], ...}。
        Raises:
            LedgerWriteConflict: 同 _load；不是交易类写入（如预算）；index 越界、accounts 为空或含非法字段；
                用到了 Equity: 账户；账户组合不能构成有效资金流向
            NotFound: 同 _load
            AccountNotFound: 账户没有在账本的 open 指令中声明
        """
        record = self._load(user, pending_id)
        if record["kind"] != "record":
            raise LedgerWriteConflict("只有交易的待确认写入可以修改账户")
        transactions = record["payload"]["transactions"]
        if (
            not 0 <= index < len(transactions)  # 下标不在合法范围内
            or not accounts
            or any(field not in FIELDS for field in accounts)
        ):
            raise LedgerWriteConflict("请选择有效交易和账户")
        changed = transactions[index] | accounts  # | 为字典合并运算符
        changed["autofilled"] = [
            # 创建一个新列表
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
        """确认一条待确认写入：落盘到账本并提交 git，成功后标记为 'confirmed'。
        落盘前先在库里把状态抢成 'confirming'：连点和删除对话都改不动它，失败时退回 'pending'
        Args:
            user: 当前用户
            pending_id: 待确认写入的id.
        Returns:
            账本写入回执，合并上 pending_id 和 status
            示例：{"file": "2026/10-expenses.bean", "commit": "a1b2c3d", "pending_id": "abc123", "status": "confirmed", ...}
        Raises:
            LedgerWriteConflict: 同 _load，或账本写入失败
            NotFound: 同 _load
        """
        record = self._load(user, pending_id)
        if not self.database.claim_pending(pending_id, user["id"]):
            raise LedgerWriteConflict("这条写入的状态刚刚变了，请刷新后重试")
        try:
            return await self._confirm(user, pending_id, record)
        except BaseException:
            self.database.release_pending(pending_id)
            raise

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
        self.database.resolve_pending(
            pending_id, "confirmed", receipt["commit"], from_status="confirming"
        )
        return receipt | {"pending_id": pending_id, "status": "confirmed"}

    def reject(self, user: dict, pending_id: str) -> dict:
        self._load(user, pending_id)
        self.database.resolve_pending(pending_id, "rejected")
        return {"pending_id": pending_id, "status": "rejected"}


STATUS_LABELS = {"confirmed": "写入账本", "rejected": "丢弃", "expired": "过期"}
