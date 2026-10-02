"""Extract 输出模型与确定性打回规则。"""
from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Annotated
from pydantic import BaseModel, Field, WithJsonSchema, field_validator


# Pydantic 给 Decimal 自动生成的 schema 带一条含 lookaround 的正则，结构化输出的
# schema 校验器普遍不支持，会直接 400。这里显式声明成字符串：既绕开那条正则，
# 也让金额不经过 float，避免精度损失。
Money = Annotated[Decimal, WithJsonSchema({
    'type': 'string',
    'description': '金额，正数，十进制字符串，如 "128.50"',
})]


QUESTION_WORDS = ('吗', '呢', '为什么', '多少', '几', '是不是')
RANGE_DATES = ('上个月', '这个月', '本月', '上周', '这周', '今年', '去年', '最近')
CATEGORY_PAYEES = {'餐饮', '交通', '购物', '订阅', '早餐', '午餐', '晚餐', '咖啡'}
MULTI_POSTING_ISSUE = '这笔需要多条分录行，当前只支持两条分录行，请在账本里手写'


class ExtractedTransaction(BaseModel):
    amount: Money = Field(gt=0)
    date: date
    payee: str
    narration: str = ''
    from_account: str | None = None
    to_account: str | None = None
    # Structured Outputs 不支持 set 生成的 `uniqueItems: true`，因此在 LLM
    # 边界使用数组，并在解析后确定性去重。
    tags: list[str] = Field(default_factory=list)

    @field_validator('tags')
    @classmethod
    def deduplicate_tags(cls, tags: list[str]) -> list[str]:
        return list(dict.fromkeys(tags))


def extraction_issues(message: str, transactions: Sequence[ExtractedTransaction | dict]) -> list[str]:
    issues: list[str] = []
    # 只在同一组拆分金额中识别；多笔独立消费不会因金额多就被拒绝。
    amounts_message = re.sub(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}|(?:\d{4}年)?\d{1,2}月\d{1,2}[日号]', '', message)
    for segment in re.split(r'[。；;\n]|另外|然后|还买|又买', amounts_message):
        if len(re.findall(r'\d+(?:\.\d+)?', segment)) > 1 and any(word in segment for word in ('扣', '其中', '到手', '实发')):
            issues.append(MULTI_POSTING_ISSUE)
            break
    if any(word in message for word in QUESTION_WORDS):
        issues.append('含疑问词')
    if any(word in message for word in RANGE_DATES):
        issues.append('日期是范围')
    if not re.search(r'(?<!\d)\d+(?:\.\d{1,2})?(?!\d)', message):
        issues.append('缺明确金额主体')
    for raw in transactions:
        transaction = raw if isinstance(raw, ExtractedTransaction) else ExtractedTransaction.model_validate(raw)
        if transaction.payee.strip() in CATEGORY_PAYEES:
            issues.append('商户字段是品类词')
            break
    return issues


def route_after_extract(issues: list[str], bounce_count: int, missing: list[dict] | None = None) -> str:
    if missing and not issues:
        return 'ask'
    if not issues:
        return 'tools'
    return 'classify' if bounce_count < 1 else 'ask'