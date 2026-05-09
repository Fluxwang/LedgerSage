from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List


# 等价于
# class BaseMessage:
#     def __init__(self, content: str):
#         self.content = content
@dataclass
class BaseMessage:
    content: str


@dataclass
class ErrorMessage:
    content: str
    exception: Exception


@dataclass
class Table:
    title: str
    headers: List[str]
    rows: list[list[Any]]
