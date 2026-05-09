from beanbot.gateways.beancount_repo import BeancountRepository
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
repo = BeancountRepository(filename="my_ledger.bean", currency="CNY", logger=logger)
text = """
2024-01-15 * "KFC" "午餐"
  Assets:Bank:CMB  -100 CNY
  Expenses:Food
"""
entries, errors, options = repo.parse_transactions(text)
print(f"解析出 {len(entries)} 条指令")
print(f"发现 {len(errors)} 个错误")
print(entries)
