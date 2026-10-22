"""从账本 Git 提交生成只读写入历史，忽略手工提交和撤销本身。"""
from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING

from beanbot.gateways.ledger.repo import git

if TYPE_CHECKING:
    from beanbot.gateways.ledger.ledger import Ledger

ACTION = re.compile(r'^(?:LedgerSage|BeanChat): (record|set budget|delete)(?:\s|$)')
UNDO = re.compile(r'^(?:LedgerSage|BeanChat): undo ([0-9a-f]{12,40})$')
HEADER = re.compile(r'^\d{4}-\d{2}-\d{2}\s+(?:[*!A-Z]|txn)\s+')
QUOTED = r'"(?:[^"\\]|\\.)*"'


def _transaction_summary(lines: list[str], multiple: bool) -> str:
    heads = [i for i, line in enumerate(lines) if HEADER.match(line)]
    if not heads:
        return '交易写入'
    first = heads[0]
    header = lines[first]
    text = '/'.join(filter(None, (ast.literal_eval(s) for s in re.findall(QUOTED, header))))
    block = lines[first + 1:heads[1] if len(heads) > 1 else len(lines)]
    amount = next((m.group(1).replace('-', '−') for line in block
                   if (m := re.match(r'^\s+[A-Z][\w:-]+\s+(-?[\d.]+)\s+\w+', line))), '')
    summary = ' '.join(part for part in (header[5:10], text, amount) if part)
    return summary + (f' 等 {len(heads)} 笔' if multiple and len(heads) > 1 else '')


def write_history(ledger: Ledger, limit: int) -> list[dict]:
    # 新提交先出现；同秒内的提交仍保持 Git 的拓扑顺序。
    log = git(ledger.root, 'log', '--topo-order', '--format=%H%x00%cI%x00%s')
    commits = [line.split('\0', 2) for line in log.splitlines()]
    undone: dict[str, str] = {}
    for _, timestamp, subject in commits:
        if match := UNDO.fullmatch(subject):
            undone.setdefault(match.group(1), timestamp)
    ledger.reload()
    names = dict(ledger.accounts_with_names())
    rows: list[dict] = []
    for sha, timestamp, subject in commits:
        action = ACTION.match(subject)
        if not action:
            continue
        kind = {'record': 'record', 'set budget': 'budget', 'delete': 'delete'}[action.group(1)]
        files = git(ledger.root, '-c', 'core.quotepath=false', 'diff-tree', '--no-commit-id',
                    '--name-only', '-r', sha).splitlines()
        changed: list[str] = []
        target = ''
        sign = '-' if kind == 'delete' else '+'
        for filename in files:
            if not filename.endswith('.bean'):
                continue
            diff = git(ledger.root, 'show', '--format=', '--unified=0', '--no-color',
                       '--no-ext-diff', '--no-renames', sha, '--', filename)
            lines = [line[1:] for line in diff.splitlines()
                     if line.startswith(sign) and not line.startswith(sign * 3)]
            if lines and not target:
                target = filename
            changed.extend(lines)
        if kind == 'budget':
            budget = next((m for line in changed if (m := re.match(
                rf'^\d{{4}}-\d{{2}}-\d{{2}} custom "budget" ({QUOTED}|[A-Z][\w:-]+) ({QUOTED}) ([\d.]+) (\w+)', line))), None)
            if budget:
                account = ast.literal_eval(budget.group(1)) if budget.group(1).startswith('"') else budget.group(1)
                summary = f'{names.get(account) or account} 预算 → {budget.group(3)} {budget.group(4)}'
            else:
                summary = '设置预算'
        else:
            summary = _transaction_summary(changed, kind == 'record')
        rows.append({
            'commit': sha, 'kind': kind, 'summary': summary, 'file': target,
            'committed_at': timestamp,
            'undone_at': next((at for prefix, at in undone.items() if sha.startswith(prefix)), None),
        })
        if len(rows) >= limit:
            break
    return rows
