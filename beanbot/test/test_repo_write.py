import logging
from datetime import datetime
from decimal import Decimal

from beanbot.gateways.beancount_repo import BeancountRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

repo = BeancountRepository(filename="my_ledger.bean", currency="CNY", logger=logger)

print("=== 生成交易测试 ===")
entry = repo.build_transaction_entry(
    date=datetime(2024, 2, 1),
    payee="测试商家",
    narration="测试交易",
    account="Expenses:Food",
    amount=Decimal("100.00"),
    tags={"test"},
)
print("生成的交易: ")
print(repo.render_entry(entry))


append_Entry = repo.build_transaction_entry(
    date=datetime(2024, 2, 1),
    payee="测试新增商家",
    narration="测试新增交易",
    account="Expenses:Food",
    amount=Decimal("150.00"),
    tags={"test"},
)
repo.append_transaction(append_Entry)

print(append_Entry)
