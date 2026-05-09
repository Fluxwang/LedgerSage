from types import SimpleNamespace
from beanbot.services.query_service import QueryService

query_service = QueryService(repository=None)  # translate_rows 不用 repository

# 模拟 result_types：每列只需要有 .name 属性
result_types = [
    SimpleNamespace(name="account"),
    SimpleNamespace(name="sum(position)"),
]

# 模拟 result_rows：包含空值的情况
result_rows = [
    ["Expenses:Food", "250.00 CNY"],
    ["Expenses:Transport", ""],  # 空值，预期被过滤
    ["Expenses:Coffee", "32.00 CNY"],
]

table = query_service.translate_rows("Expenses", result_types, result_rows)
print(table)
