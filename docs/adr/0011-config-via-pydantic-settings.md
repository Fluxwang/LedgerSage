# 配置改用 pydantic-settings 与环境变量，弃用 config.yaml

原 `settings.py` 的 `__getattr__` 在 key 不存在时返回一个空的 `Settings`（假值但不是 `None`），因此漏写配置不会报错、只会静默降级——线上的真实例证：`config.yaml` 从未定义 `db_store_folder`，向量库便悄悄落到进程工作目录。改用 `pydantic-settings`：配置来自环境变量与 `.env`，缺必填项在**启动时**失败。

## Consequences

- 密钥（LLM api_key、JWT secret、邀请码）走环境变量，符合容器部署惯例，也终结了「明文密钥躺在被 gitignore 的 `config.yaml` 里」这一状态——那个文件一旦误提交即全部泄露。
- `settings.py` 整体重写，所有 `settings.x.y` 调用点跟着改；`ImmutableDict` 的点号访问写法放弃。README 中关于 `config.yaml` 的说明需同步更新。
- 账户区分层级（`account_distinguation_range`）这类 **per-user 偏好**不属于环境变量，拆到 SQLite 的 `user_settings`。
