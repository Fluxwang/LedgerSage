from __future__ import annotations
import shlex

ARGS_ERROR = ValueError("Quote not closed")


def parse_args(line: str) -> list[str]:
    """将中文引号更改为英文的引号并按shell规则拆分为成列表"""
    line = line.replace("“", '"').replace("”", '"')
    try:
        # 引号外的空格作为分隔符切割，引号内的空格不切割(保留整体)
        return shlex.split(line)
    except ValueError as exc:
        raise ARGS_ERROR from exc
