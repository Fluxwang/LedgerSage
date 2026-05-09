from beanbot.settings import load_settings


settings = load_settings("config.yaml")
#
# print("=== 配置读取测试 ===")
# print(f"账本文件：{settings.beancount.filename}")
# print(f"默认币种：{settings.beancount.currency}")
# print(f"账户区分范围：{settings.beancount.account_distinguation_range}")
# print(f"日志级别：{settings.logging.level}")
#
# print("\n=== 测试不存在的配置 ===")
# print(f"不存在的配置：{settings.beancount.get('missing')}")
# print(f"不存在的配置（带默认值）：{settings.beancount.get('missing', 'default_value')}")
#
# print("\n=== 测试只读保护 ===")
# try:
#     settings.beancount.filename = "new_file.bean"
#     print("错误：配置应该是只读的！")
# except TypeError as e:
#     print(f"正确：配置被保护，无法修改 - {e}")

print(f"账本文件: {settings.beancount.filename}")
print(f"货币: {settings.beancount.currency}")
print(f"平台: {settings.bot.platform}")

# 测试不可变性
try:
    settings.beancount.filename = "new.bean"
except AttributeError as e:
    print(f"修改被阻止: {e}")

# 测试 get 方法
print(f"语言: {settings._config.get('language', 'en')}")
