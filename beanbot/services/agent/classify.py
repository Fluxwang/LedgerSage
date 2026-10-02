"""意图分类模型及低置信度路由。"""
from typing import Literal
from pydantic import BaseModel, Field
from beanbot.services.agent.few_shots import CLASSIFY_EXAMPLES


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