from decimal import Decimal
from beanbot.gateways.beancount_repo import BeancountRepository
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
repo = BeancountRepository(filename="my_ledger.bean", currency="CNY", logger=logger)


original = """
2024-01-10 * "KFC" "午餐"
  Assets:Bank:CMB  -100 CNY
  Expenses:Food
"""

cloned = repo.clone_transaction(original, Decimal("50"))
print(cloned)
