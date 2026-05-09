import logging

from beanbot.gateways.beancount_repo import BeancountRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

repo = BeancountRepository(filename="my_ledger.bean", currency="CNY", logger=logger)

print("=== 账户列表 ===")
for account in sorted(repo.accounts):
    print(f"{account}")

print("\n=== 账本选项 ===")
print(f"标题: {repo.options.get('title')}")
print(f"默认币种: {repo.options.get('operating_currency')}")

print("\n=== 条目数量 ===")
print(f"总条目数: {len(repo.entries)}")

print(f"mtimes 中的内容: {repo.mtimes}")

print(f"账户数量: {len(repo.accounts)}")
print(f"指令数量: {len(repo.entries)}")
print(f"默认货币: {repo.options['operating_currency']}")
