from __future__ import annotations

import argparse

from beanbot.bootstrap import bootstrap_app


def main():
    parser = argparse.ArgumentParser(description="BenaBot - Beancount Telegram Bot")
    parser.add_argument(
        "platform", choices=["telegram", "mattermost"], help="Choice the Bot platform"
    )
    parser.add_argument("-c", "--config", required=True, help="Config File path")
    args = parser.parse_args()

    context = bootstrap_app(args.config)

    if args.platform == "telegram":
        print("telegram")
        from beanbot.bots.telegram_bot import run_bot

        run_bot(context.settings, context.logger)
