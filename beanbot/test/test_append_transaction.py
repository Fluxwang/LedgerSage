from beanbot.gateways.beancount_repo import BeancountRepository
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
repo = BeancountRepository(filename="my_ledger.bean", currency="CNY", logger=logger)
transaction_text = """
2024-01-15 * "KFC" "午餐"
  Assets:Bank:CMB  -100 CNY
  Expenses:Food
"""
repo.append_transaction(transaction_text)
print("交易已追加到文件")
