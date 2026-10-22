"""LLM 边界：只接受结构化输出，便于测试时替换固定响应。"""

from __future__ import annotations

from datetime import date
from typing import Protocol
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

from beanbot.config import Settings
from beanbot.services.agent.classify import Classification, classify_prompt
from beanbot.services.agent.extract import ExtractedTransaction, Money
from beanbot.services.agent.query import TransactionQuery


class ExtractBatch(BaseModel):
    transactions: list[ExtractedTransaction]


class BudgetPlan(BaseModel):
    account: str | None = None
    amount: Money | None = Field(default=None, gt=0)
    period: str = "monthly"


class QueryPlan(BaseModel):
    tool: str = "query_transactions"
    arguments: TransactionQuery | None = None
    account_prefix: str | None = None
    as_of: date | None = None


class AgentModel(Protocol):
    async def classify(self, message: str, history: list[str]) -> Classification: ...
    async def extract(
        self,
        message: str,
        accounts: list[tuple[str, str | None]],
        examples: list[str],
        today: date,
    ) -> ExtractBatch: ...
    async def query(self, message: str, accounts: list[tuple[str, str | None]], today: date) -> QueryPlan: ...
    async def budget(
        self, message: str, accounts: list[tuple[str, str | None]]
    ) -> BudgetPlan: ...


class OpenAIAgentModel:
    def __init__(self, settings: Settings):
        self.chat = ChatOpenAI(
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            temperature=0,
        )

    async def classify(self, message: str, history: list[str]) -> Classification:
        runnable = self.chat.with_structured_output(Classification)
        return Classification.model_validate(
            await runnable.ainvoke(classify_prompt(message, history))
        )

    async def extract(
        self,
        message: str,
        accounts: list[tuple[str, str | None]],
        examples: list[str],
        today: date,
    ) -> ExtractBatch:
        runnable = self.chat.with_structured_output(ExtractBatch)
        prompt = (
            "抽取一笔或多笔新交易。日期必须是绝对 ISO 日期。金额为正数。"
            "from_account 是资金流出方（负数），to_account 是资金流入方。"
            "支出：Assets/Liabilities → Expenses；收入：Income → Assets；"
            "转账及还信用卡：Assets/Liabilities → Assets/Liabilities。"
            "照相似历史的金额符号填写，未提及的账户填 null，不猜资金账户。\n"
            f"今天是 {today.isoformat()}。相对日期必须以今天为基准换算。\n"
            f"账户（账户名，显示名）：{accounts}\n相似历史：{examples}\n消息：{message}"
        )
        return ExtractBatch.model_validate(await runnable.ainvoke(prompt))

    async def query(self, message: str, accounts: list[tuple[str, str | None]], today: date) -> QueryPlan:
        runnable = self.chat.with_structured_output(QueryPlan)
        return QueryPlan.model_validate(
            await runnable.ainvoke(
                "选择固定工具 query_transactions/get_balance/list_accounts/budget_status 并填写参数。"
                "问预算还剩多少、超没超时用 budget_status。"
                "account_prefix 必须是账户表里的真实账户，或其按冒号分段的前缀，不得编造账户。"
                f"账户（账户名，显示名）：{accounts}。"
                f"今天是 {today.isoformat()}。不得生成 BQL。问题：{message}"
            )
        )

    async def budget(
        self, message: str, accounts: list[tuple[str, str | None]]
    ) -> BudgetPlan:
        runnable = self.chat.with_structured_output(BudgetPlan)
        return BudgetPlan.model_validate(
            await runnable.ainvoke(
                f"抽取追加式预算设置。账户：{accounts}\n消息：{message}"
            )
        )
