from __future__ import annotations

import time
from datetime import datetime, timedelta

import telegram
from telegram import Message, Update

from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from beanbot.bootstrap import get_context
from beanbot.bots import controller

# from beanbot.i18n import gettext as _
from beanbot.models import ErrorMessage

# 获取系统时间
_start_time = time.monotonic()


def owner_required(func):
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_chat is None:
            return
        chat_id = update.effective_chat.id
        owner_id = get_context().settings.bot.telegram.chat_id
        if chat_id != owner_id:
            return
        await func(update, context)

    return wrapped


async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    uptime = timedelta(seconds=time.monotonic() - _start_time)
    if update.message is None:
        return
    await update.message.reply_text(text=f"Now: {now}\n uptime: {uptime}")


def render_tg_table(headers, rows):
    # 将 Table 数据渲染成等宽文本，自动对齐列宽
    margin = 2
    # map(function, iterables)
    max_widths = list(map(len, headers))
    for row in rows:
        # enumerate() 会在遍历元素的同时，自动加上索引
        # 计算出每列的最大宽度
        for index, cell in enumerate(row):
            # 查找出max_widths[index] 的 最大值，找出最宽的字符串
            max_widths[index] = max(len(str(cell)), max_widths[index])

    table = []
    raw_row = []
    for index, header in enumerate(headers):
        # 核心就是将当前header补全到该列最长的内容一样宽，再额外加margin
        raw_row.append(f"{header}{' ' * (max_widths[index] - len(header) + margin)}")
    table.append(raw_row)
    # 添加max_widths的和为长度的 - 再加上 margin * 列数 -1 的 -
    table.append("-" * (sum(max_widths) + margin * (len(max_widths) - 1)))

    for row in rows:
        raw_row = []
        for index, cell in enumerate(row):
            raw_row.append(
                f"{cell}{' ' * (max_widths[index] - len(str(cell)) + margin)} "
            )
        table.append(raw_row)

    # return "\n".join("".join(row) for row in table)
    result = ""
    for row in table:
        line = "".join(row)
        result += line + "\n"
    return result


def escape_md2(text):
    # 转义 MarkdownV2 中的特殊字符
    return text.replace("-", "\\-").replace("*", "\\*")


@owner_required
async def bill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = controller.get_controller().fetch_bill()
    if update.message is None:
        return
    if isinstance(result, ErrorMessage):
        await update.message.reply_text(text=result.content)
        return
    text = f"```\n{render_tg_table(result.headers, result.rows)}```"
    await update.message.reply_text(text=text, parse_mode="MarkdownV2")


@owner_required
async def expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = controller.get_controller().fetch_expense()
    if update.message is None:
        return
    if isinstance(result, ErrorMessage):
        await update.message.reply_text(text=result.content)
        return
    text = f"```\n{render_tg_table(result.headers, result.rows)}```"
    await update.message.reply_text(text=text, parse_mode="MarkdownV2")


@owner_required
async def render(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    line = update.message.text
    result = controller.get_controller().render_txs(line)
    if isinstance(result, ErrorMessage):
        await update.message.reply_text(text=result.content)
        return
    for index, transaction in enumerate(result):
        keyboard = [
            [
                telegram.InlineKeyboardButton(
                    "Submit", callback_data=f"submit:{index}"
                ),
                telegram.InlineKeyboardButton("Cancel", callback_data="cancel"),
            ]
        ]
        reply_markup = telegram.InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            text=f"```beancount\n{escape_md2(transaction)}\n```",
            parse_mode="MarkdownV2",
            reply_markup=reply_markup,
            reply_to_message_id=update.message.message_id,
        )


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None:
        return
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text(text="Cancelled")
        return

    if query.data is None:
        return

    if query.data.startswith("submit:"):
        if not isinstance(query.message, Message) or query.message.text is None:
            return
        transaction = query.message.text_markdown_v2.split("```beancount\n")[1].split(
            "```"
        )[0]
        transaction = transaction.replace("\\-", "-").replace("\\*", "*")
        result = controller.get_controller().submit_transaction(transaction)
        if isinstance(result, ErrorMessage):
            await query.edit_message_text(text=result.content)
        else:
            await query.edit_message_text(
                text=f"```beancount\n{escape_md2(transaction)}\n```✅Transaction committed",
                parse_mode="MarkdownV2",
            )


@owner_required
async def clone_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None:
        return
    args = context.args
    amount = args[0] if args else None

    reply_to = update.message.reply_to_message
    if not reply_to:
        await update.message.reply_text(text="Please reply to a transaction message")
        return

    # reply_to.text 返回的是渲染后的纯文本
    text = reply_to.text_markdown_v2
    if "```beancount" not in text:
        # await update.message.reply_text(text="Not a transaction message")
        await update.message.reply_text(text)

        return
    transaction = text.split("```beancount\n")[1].split("```")[0]
    result = controller.get_controller().clone_txs(transaction, amount)
    if isinstance(result, ErrorMessage):
        await update.message.reply_text(text=result.content)
        return

    for index, cloned in enumerate(result):
        keyboard = [
            [
                telegram.InlineKeyboardButton(
                    "Submit", callback_data=f"submit:{index}"
                ),
                telegram.InlineKeyboardButton("Cancel", callback_data="cancel"),
            ]
        ]
        reply_markup = telegram.InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            text=f"```beancount\n{escape_md2(cloned)}\n```",
            parse_mode="MarkdownV2",
            reply_markup=reply_markup,
        )


async def build(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = controller.build_db()
    if update.message is None:
        return
    await update.message.reply_text(text=msg.content)


def run_bot(settings, logger):
    app = ApplicationBuilder().token(settings.bot.telegram.token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bill", bill))
    app.add_handler(CommandHandler("expense", expense))
    # app.add_handler(CommandHandler("render", render))
    app.add_handler(CommandHandler("clone", clone_transaction))
    app.add_handler(CommandHandler("build", build))
    # filters.TEXT: 匹配所有包含文字内容的消息, filters.COMMAND: 匹配以 / 开头的指令消息 ~为取反的意思
    # ~filters.COMMAND 就是不是指令的消息
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, render))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    logger.info("Starting telegram Bot")
    app.run_polling()
