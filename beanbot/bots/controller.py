from __future__ import annotations

from decimal import Decimal

from beanbot.models import BaseMessage, ErrorMessage

_controller = None


def get_controller():
    if _controller is None:
        raise RuntimeError("Controller not init_locale")
    return _controller


def configure(controller):
    global _controller
    _controller = controller


# 函数级包装函数
def build_db():
    return get_controller().build_db()


class BotController:
    def __init__(
        self, settings, repository, ledger_service, query_service, vector_service
    ):
        self.settings = settings
        self.repository = repository
        self.ledger_service = ledger_service
        self.query_service = query_service
        self.vector_service = vector_service

    def render_txs(self, line: str):
        """根据用户输入文本生成 Beancount 交易。

        Args:
            line: 用户输入的原始文本，会由 ledger_service
                调用 parse_args() 解析引号和参数。

        Returns:
            list[str]: 生成成功时返回格式化后的交易文本列表。
            ErrorMessage: 生成失败时返回错误消息，并保留原始异常。
        """
        try:
            transactions = self.ledger_service.generate_transactions(line)
            return transactions
        except Exception as e:
            return ErrorMessage(content=str(e), exception=e)

    def submit_transaction(self, data: str):
        """提交一条已生成的 Beancount 交易到账本文件。

        Args:
            data: 已格式化的 Beancount 交易文本，通常来自
                render_txs() 生成的结果。

        Returns:
            BaseMessage: 写入成功时返回普通消息。
            ErrorMessage: 写入失败时返回错误消息，并保留原始异常。
        """
        try:
            self.ledger_service.commit_transaction(data)
            return BaseMessage(content="Transaction committed")
        except Exception as exc:
            return ErrorMessage(content=str(exc), exception=exc)

    def clone_txs(self, text: str, amount: str | None = None):
        """克隆一条已有交易，可选覆盖金额。
        Args:
            text: 用于匹配历史交易的文本(如收款方或描述)

            amount: 可选的新金额字符串，传入后会替换原始交易
                中的金额；为None 时保持原金额不变。

        Returns:
            list[str]: 克隆成功时返回格式化后的交易文本列表
            ErrorMessage: 克隆失败时返回错误消息，并保留原始异常。

        """
        try:
            amount_decimal = Decimal(amount) if amount else None
            cloned = self.ledger_service.clone_transaction_with_error(
                text, amount_decimal
            )
            return [cloned]
        except Exception as e:
            return ErrorMessage(content=str(e), exception=e)

    def fetch_bill(self):
        """查询账单的汇总消息。

        Returns:
            Table: 查询成功时返回账单表格数据。
            ErrorMessage: 查询失败时返回错误消息，并保留原始异常。
        """
        try:
            return self.query_service.fetch_bill()
        except Exception as e:
            return ErrorMessage(content=str(e), exception=e)

    def fetch_expense(self):
        """查询Expenses账户的汇总信息
        ReturnsL
            Table: 查询成功时返回支出表格数据。
            ErrorMessage: 查询失败时返回错误消息，并保留原始异常
        """
        try:
            return self.query_service.fetch_expense()
        except Exception as e:
            return ErrorMessage(content=str(e), exception=e)

    def build_db(self):
        """构建向量数据库"""
        try:
            if not self.settings.embedding.get("enable", False):
                return BaseMessage(content="embedding not enabled")
            tokens = self.vector_service.build_transaction_db(self.repository.entries)
            # return BaseMessage(content=("Token usage: {tokens}").format(tokens=tokens))
            return BaseMessage(content=f"Token usage: {tokens}")
        except Exception as e:
            return ErrorMessage(content=str(e), exception=e)
