def main():
    headers = ["account", "sum_position"]
    rows = [
        ["Expenses:Food", "380.50 CNY"],
        ["Expenses:Transport", "120.00 CNY"],
        ["Expenses:Shopping", "650.00 CNY"],
        ["Expenses:Entertainment", "200.00 CNY"],
    ]
    print(render_tg_table(headers, rows))


def render_tg_table(headers, rows):
    # 将 Table 数据渲染成等宽文本，自动对齐列宽
    margin = 2
    # map(function, iterables)
    max_widths = list(map(len, headers))
    for row in rows:
        # enumerate() 会在遍历元素的同时，自动加上索引
        # 计算出每列的最大宽度
        for index, cell in enumerate(row):
            max_widths[index] = max(len(str(cell)), max_widths[index])

    table = []
    raw_row = []
    for index, header in enumerate(headers):
        # 核心就是将当前header补全到该列最长的内容一样宽，再额外加margin
        raw_row.append(f"{header}{' ' * (max_widths[index] - len(header) + margin)}")
    table.append(raw_row)
    # 添加max_widths的和为长度的 - 再加上 margin * 列数 -1 的 -
    table.append("-" * (sum(max_widths) + margin * (len(max_widths) - 1)))

    for row in rows:
        raw_row = []
        for index, cell in enumerate(row):
            raw_row.append(
                f"{cell}{' ' * (max_widths[index] - len(str(cell)) + margin)} "
            )
        table.append(raw_row)

    # return "\n".join("".join(row) for row in table)
    result = ""
    for row in table:
        line = "".join(row)
        result += line + "\n"
    return result


if __name__ == "__main__":
    main()
