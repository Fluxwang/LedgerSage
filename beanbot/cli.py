from __future__ import annotations

import argparse
import json
import secrets
import subprocess
from pathlib import Path

from beanbot.config import Settings
from beanbot.migrate_account_names import migrate_account_names
from beanbot.storage.database import Database


def main():
    parser = argparse.ArgumentParser(description="LedgerSage 对话式记账服务")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser(name="serve", help="启动 Web 服务")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", default=8000, type=int)
    invite = commands.add_parser(name="invite", help="生成邀请码")
    invite.add_argument("--count", type=int, default=1)
    migrate = commands.add_parser(
        name="migrate-account-names",
        aliases=["migrate_account_names"],
        help="迁移账户显示名",
    )
    migrate.add_argument("ledger", type=Path)
    migrate.add_argument("--names", type=Path, help="已确认的账户显示名 JSON")
    migrate.add_argument(
        "--apply", action="store_true", help="执行迁移并单独提交；默认只预览"
    )

    # bean-format 不再是运行时依赖，只作为可选的人工维护命令保留（ADR-0002）。
    format_command = commands.add_parser(
        "format", help="人工对账本文件跑一次 bean-format"
    )
    format_command.add_argument("ledger", type=Path, help="账本目录或单个 .bean 文件")
    args, extras = parser.parse_known_args()
    if extras:
        parser.error(f"无法识别的参数：{' '.join(extras)}")
    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "beanbot.api.app:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            workers=1,
        )
    elif args.command == "invite":
        settings = Settings()  # type: ignore[call-arg]
        database = Database(settings.database_path)
        for _ in range(args.count):
            code = secrets.token_urlsafe(18)
            database.invite(code)
            print(code)
    elif args.command in ("migrate-account-names", "migrate_account_names"):
        names = json.loads(args.names.read_text()) if args.names else None
        for item in migrate_account_names(
            args.ledger, names, dry_run=not args.apply, commit=args.apply
        ):
            print(item)
    elif args.command == "format":
        target: Path = args.ledger
        files = sorted(target.rglob("*.bean")) if target.is_dir() else [target]
        if not files:
            parser.error(f"{target} 下没有 .bean 文件")
        for path in files:
            subprocess.run(["bean-format", "-o", str(path), str(path)], check=True)
            print(path)
