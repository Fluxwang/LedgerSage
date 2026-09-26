# 预算写成追加式的 `custom "budget"` 指令

预算数据和交易一样以账本文件为唯一真源，不进数据库。Beancount 没有原生的预算指令，我们采用 fava-envelope 的既有约定，写在独立的 `budgets.bean` 里：

```beancount
2026-08-01 custom "budget" Expenses:Food:Dining "monthly" 2000.00 CNY
```

## Consequences

- `custom` 是 Beancount 官方的扩展点，loader 遇到不认识的 custom 原样保留、不报错，代码遍历 `entries` 取 `data.Custom` 即可读出。选用 `"budget"` 这个既有约定键，将来接 fava 的预算视图有路可走。
- **调整预算是追加一条新指令，不是改写旧行**，生效值取日期最新的那条——与 ADR-0002 的纯追加原则保持一致，同时天然保留预算的变更历史。代价是文件会随时间变长。
- 预算单独成文件：交易文件是纯追加的流水，预算是会被反复覆盖的配置，两种写入语义不混在一个文件里。
