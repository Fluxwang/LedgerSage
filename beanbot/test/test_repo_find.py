import logging
from beanbot.gateways.beancount_repo import BeancountRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

repo = BeancountRepository(filename="my_ledger.bean", currency="CNY", logger=logger)

test_fragments = ["Checking", "Food", "Salary", "Bank", "Test"]
for fragment in test_fragments:
    result = repo.find_account(fragment, range_=[2, 3])
    print(f"片段 '{fragment} -> {result}'")

test_payees = ["超市", "公司", "不存在的商家", "KFC"]
for payee in test_payees:
    result = repo.find_account_by_payee(payee)
    print(f"收款方 '{payee}' -> {result}")
