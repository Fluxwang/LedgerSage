"""把 open 指令的中文注释和人工确认的名称迁移到 name meta。"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from beancount import loader
from beancount.core import data


def migrate_account_names(root: Path, names: dict[str, str] | None = None, *,
                          dry_run: bool = False, commit: bool = False) -> list[str]:
    root = root.resolve()
    names = names or {}
    status = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain'], text=True)
    if status and not dry_run:
        raise RuntimeError('工作区不干净，请先处理现有改动')
    entries, errors, _ = loader.load_file(str(root / 'main.bean'))
    if errors:
        raise RuntimeError(f'迁移前账本无法加载：{errors[0]}')
    opened = [entry for entry in entries if isinstance(entry, data.Open)]
    unknown = set(names) - {entry.account for entry in opened}
    if unknown:
        raise ValueError(f'账户不存在：{sorted(unknown)}')
    originals: dict[Path, bytes] = {}
    replacements: dict[Path, dict[int, str]] = {}
    changed: list[str] = []
    for entry in opened:
        if entry.meta.get('name'):
            continue
        path = Path(entry.meta['filename']).resolve()
        if not path.is_relative_to(root):
            raise RuntimeError('账户文件必须在账本仓库内')
        original = originals.setdefault(path, path.read_bytes())
        line_number = entry.meta['lineno'] - 1
        line = original.decode('utf-8').splitlines(keepends=True)[line_number]
        directive, _, comment = line.rstrip('\r\n').partition(';')
        name = names.get(entry.account) or (comment.strip() if re.search(r'[\u4e00-\u9fff]', comment) else '')
        if not name:
            continue
        if '\n' in name or '\r' in name:
            raise ValueError('显示名不能换行')
        newline = '\r\n' if line.endswith('\r\n') else '\n'
        replacements.setdefault(path, {})[line_number] = (
            directive.rstrip() + newline + '  name: ' + json.dumps(name, ensure_ascii=False) + newline
        )
        changed.append(f'{path.relative_to(root)}: {entry.account} → {name}')
    if dry_run or not changed:
        return changed
    try:
        for path, edits in replacements.items():
            lines = originals[path].decode('utf-8').splitlines(keepends=True)
            path.write_bytes(''.join(edits.get(index, line) for index, line in enumerate(lines)).encode('utf-8'))
        migrated, errors, _ = loader.load_file(str(root / 'main.bean'))
        if errors or sum(isinstance(entry, data.Open) for entry in migrated) != len(opened):
            raise RuntimeError(f'迁移后账本校验失败：{errors[:1]}')
        if commit:
            subprocess.run(['git', '-C', str(root), 'commit', '--only', '-m',
                            'BeanChat: migrate account display names', '--',
                            *(str(path.relative_to(root)) for path in replacements)], check=True, capture_output=True)
    except Exception:
        for path in replacements:
            path.write_bytes(originals[path])
        raise
    return changed
