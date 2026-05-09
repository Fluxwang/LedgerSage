from beanbot.services.query_service import QueryService
from beanbot.gateways.beancount_repo import BeancountRepository
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
repo = BeancountRepository(filename="my_ledger.bean", currency="CNY", logger=logger)

query_service = QueryService(repo)


def print_expected(title, headers, rows_description):
    print("希望的输出:")
    print(f"标题: {title}")
    print(f"列名: {headers}")
    print(f"行数据: {rows_description}")


def print_actual(table):
    print("程序的输出:")
    print(f"标题: {table.title}")
    print(f"列名: {table.headers}")
    print("行数据:")
    if table.rows:
        for row in table.rows:
            print(row)
    else:
        print([])


def check_table(table, expected_title, expected_headers):
    assert table.title == expected_title
    assert table.headers == expected_headers
    assert isinstance(table.rows, list)
    for row in table.rows:
        assert isinstance(row, list)
        assert len(row) == len(expected_headers)
        for value in row:
            assert isinstance(value, str)


# 查询费用
print("\n测试: 查询费用")
expense_table = query_service.fetch_expense()
print_expected(
    title="Expenses",
    headers=["account", "sum(position)"],
    rows_description="每一行应该是 [费用账户, 金额汇总]，例如 ['Expenses:Food', '(250.00 CNY)']",
)
print_actual(expense_table)
check_table(
    table=expense_table,
    expected_title="Expenses",
    expected_headers=["account", "sum(position)"],
)

# 查询账单
print("\n测试: 查询账单")
bill_table = query_service.fetch_bill()
print_expected(
    title="Bills",
    headers=["account", "sum(position)"],
    rows_description="每一行应该是 [负债账户, 金额汇总]，例如 ['Liabilities:CreditCard', '(-100.00 CNY)']；如果账本里没有负债记录，可以是 []",
)
print_actual(bill_table)
check_table(
    table=bill_table,
    expected_title="Bills",
    expected_headers=["account", "sum(position)"],
)

print("\n全部 QueryService 测试通过")

