from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List


@dataclass
class Table:
    title: str
    headers: List[str]
    rows: list[list[Any]]
