"""意图分类模型及低置信度路由。"""
from typing import Literal
from pydantic import BaseModel, Field


# 静态分类示例；不得注入用户或账本数据。
CLASSIFY_EXAMPLES = (
    ('我上个月为什么订阅花了150元', 'query'),
    ('上次那顿火锅是不是花了128', 'query'),
    ('这个月餐饮超过500了吗', 'query'),
    ('打车32', 'record'),
    ('星巴克38 微信', 'record'),
    ('早饭12，对了这个月餐饮多少钱', 'other'),
    ('给餐饮设个每月2000的预算', 'budget'),
)

Intent = Literal['record', 'query', 'budget', 'other']


class Classification(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0, le=1)


def classify_prompt(message: str, history: list[str]) -> str:
    examples = '\n'.join(f'{text} => {intent}' for text, intent in CLASSIFY_EXAMPLES)
    conversation = '\n'.join(history[-6:])
    return f'将消息分类为 record/query/budget/other。\n{examples}\n对话：{conversation}\n消息：{message}'


def route_classification(result: Classification, threshold: float = 0.6) -> str:
    return 'ask' if result.confidence < threshold or result.intent == 'other' else result.intent