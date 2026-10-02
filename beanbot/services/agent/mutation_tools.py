"""写账工具只接收强类型参数，分录文本由代码生成。"""
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from beanbot.gateways.ledger import Ledger, TransactionInput


class TransactionBatch(BaseModel):
    transactions: list[TransactionInput] = Field(min_length=1)


def insert_transaction_tool(ledger: Ledger) -> StructuredTool:
    async def insert_transaction(transactions: list[TransactionInput]):
        """把一条用户消息中的全部交易原子写入账本。"""
        return await ledger.insert(transactions)

    return StructuredTool.from_function(
        coroutine=insert_transaction,
        name='insert_transaction',
        description='验证并原子追加一批 Beancount 交易，返回文件、行号、提交和实际分录文本',
        args_schema=TransactionBatch,
    )