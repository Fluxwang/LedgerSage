"""从磁盘读取账本健康度；绕过工厂缓存，不创建账本，也不拿写锁。"""

import os
import re
import subprocess
from pathlib import Path

from beancount import loader
from beancount.core import data

from beanbot.gateways.ledger.inputs import flow_direction
from beanbot.gateways.ledger.repo import git


def error_message(root: Path, error) -> str:
    """错误位置和描述中的路径均转成相对于账本根目录的路径。"""
    def relative(filename: str) -> str:
        try:
            return Path(os.path.relpath(filename, root)).as_posix()
        except ValueError:
            # Windows 跨盘符路径没有相对形式，只展示文件名。
            return Path(filename).name

    source = error.source or {}
    filename = source.get("filename", str(root / "main.bean"))
    location = relative(filename) if Path(filename).is_absolute() else filename
    message = str(error.message)
    # 先替换根目录，保留带空格或中文的账本内路径。
    for prefix in (str(root) + os.sep, root.as_posix() + "/"):
        message = message.replace(prefix, "")
    message = re.sub(
        r"([\"'])((?:[A-Za-z]:[\\/]|/).*?)\1",
        lambda match: match[1] + relative(match[2]) + match[1],
        message,
    )
    # include 或插件错误还可能引用账本目录以外的绝对路径。
    message = re.sub(
        r"(?<![\w./\\])(?:[A-Za-z]:[\\/]|/)[^\s\"'<>]+",
        lambda match: relative(match.group()),
        message,
    )
    return f"{location}:{source.get('lineno', 0)} {message}"


def ledger_status(root: Path) -> dict:
    root = root.resolve()
    # load_file 会读写 pickle 缓存；使用锁定版本的无缓存入口，
    # 确保新增 include 匹配文件也立即生效，且体检本身不落盘。
    entries, errors, _ = loader._uncached_load_file(
        str(root / "main.bean"), None, None, None
    )
    message = error_message(root, errors[0]) if errors else "bean-check 通过"
    missing = sum(
        1
        for entry in entries
        if isinstance(entry, data.Transaction)
        and not entry.payee
        and any(
            posting.units is not None
            and posting.units.number is not None
            and posting.units.number > 0
            and flow_direction(None, posting.account) == "支出"
            for posting in entry.postings
        )
    )
    # 禁用 status 的可选索引刷新，体检不修改 git 工作区。
    try:
        tracked = git(
            root, "--no-optional-locks", "status", "--porcelain", "--untracked-files=no"
        )
        untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z")
        clean = not tracked and not any(
            name.endswith(".bean") for name in untracked.split("\0")
        )
        working_text = "工作区干净" if clean else "工作区有未提交的改动"
    except subprocess.CalledProcessError:
        clean = False
        working_text = "账本尚未建立 git 版本管理"
    try:
        last_commit_at = git(root, "show", "-s", "--format=%cI", "HEAD")
    except subprocess.CalledProcessError:
        last_commit_at = None
    return {
        "bean_check": {"ok": not errors, "error_count": len(errors), "message": message},
        "git": {"clean": clean, "last_commit_at": last_commit_at},
        "health": [
            {"key": "bean_check", "level": "warn" if errors else "ok", "text": message},
            {"key": "working_tree", "level": "ok" if clean else "warn", "text": working_text},
            {
                "key": "missing_payee",
                "level": "warn" if missing else "ok",
                "text": f"{missing} 笔支出缺收款方" if missing else "支出均已填写收款方",
            },
        ],
    }
