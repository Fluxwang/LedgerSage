from beanbot.services.parser import parse_args

# 测试 1：无引号
result = parse_args("100 CMB KFC 午餐")
assert result == ["100", "CMB", "KFC", "午餐"]

# 测试 2：双引号
result = parse_args('100 CMB KFC "午餐 with friends"')
assert result == ["100", "CMB", "KFC", "午餐 with friends"]

# 测试 3：单引号
result = parse_args("100 CMB KFC '午餐 with friends'")
assert result == ["100", "CMB", "KFC", "午餐 with friends"]

# 测试 4：中文引号
result = parse_args("100 CMB KFC “午餐 with friends”")
assert result == ["100", "CMB", "KFC", "午餐 with friends"]

# 测试 5：引号内只有一个词
result = parse_args('100 CMB KFC "午餐"')
assert result == ["100", "CMB", "KFC", "午餐"]

# 测试 6：引号没闭合（应该抛出错误）
try:
    parse_args('100 CMB KFC "午餐')
    assert False, "应该抛出错误"
except ValueError as e:
    assert str(e) == "Quote not closed"

print("所有测试通过！")
