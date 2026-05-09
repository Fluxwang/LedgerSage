from beancount import loader

filename = "my_ledger.bean"
entries, errors, options = loader.load_file("my_ledger.bean")
# printer = EntryPrinter()
# for entry in entries:
#     print(type(entry).__name__)
#     print(printer(entry))

print(entries)

# if errors:
#     print("解析错误")
#     for error in errors:
#         print(f"{error}")
#     print()
#
# print("=== 账户列表 ===")
# accounts = set()
# for entry in entries:
#     if isinstance(entry, data.Open):
#         accounts.add(entry.account)
#         print(f"账户: {entry.account}")
#         print(f"开户日期: {entry.date}")
#         print(f"币种: {entry.currencies}")
#         print()
#
#
# print("\n=== 交易列表 ===")
# for entry in entries:
#     if isinstance(entry, data.Transaction):
#         print(f"日期：{entry.date}")
#         print(f"收款方：{entry.payee or '(无)'}")
#         print(f"描述：{entry.narration}")
#         print("  明细：")
#         for posting in entry.postings:
#             amount = posting.units
#             assert amount is not None
#             print(f"    {posting.account:40s} {amount.number:>10} {amount.currency}")
#         print()
