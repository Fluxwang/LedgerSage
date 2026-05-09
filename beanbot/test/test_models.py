from beanbot.models import BaseMessage, ErrorMessage
from beanbot.models import Table

msg = BaseMessage(content="Hello, BeanBot!")
# print(msg)
# print(msg.content)

try:
    1 / 0
except Exception as e:
    err = ErrorMessage(content="计算错误", exception=e)
    print(err.content)
    print(err.exception)


table = Table(
    title="费用统计",
    headers=["账户", "金额"],
    rows=[["Expenses:Food", "500 CNY"], ["Expenses:Transport", "200 CNY"]],
)
print(table.title)  # 费用统计
print(table.headers)  # ['账户', '金额']
print(table.rows[0])  # ['Expenses:Food', '500 CNY']
