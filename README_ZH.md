# BeanBot

**语言 / Language：** [English](README.md) | 中文

---

BeanBot 是一个通过 Telegram Bot 用自然语言记录 [Beancount](https://github.com/beancount/beancount) 账单的工具。你只需在 Telegram 中发送一段描述（如 `35 CMB KFC 午饭`），BeanBot 就会自动生成标准的复式记账条目，并等待你确认后写入账本。

> 本项目参考了 StdioA 的 [beancount-bot](https://github.com/StdioA/beancount-bot)。

## 功能特性

- **自然语言输入**：发送账单描述，自动解析为 Beancount 交易格式
- **交互式确认**：生成交易后通过内联按钮 Submit / Cancel 确认或取消
- **向量召回**：基于历史账单的 Embedding，对模糊输入进行账户补全
- **RAG 补全**：通过大模型对复杂输入进行智能补全
- **账单查询**：通过 `/expense` 和 `/bill` 指令查询当月支出和账单
- **克隆交易**：回复一条已记账的消息，使用 `/clone` 快速生成同款交易
- **热重载**：账本文件修改后自动重新加载，无需重启服务

## 项目架构

```
gateways → services → controller → bots
```

| 层级 | 模块 | 说明 |
|------|------|------|
| Gateway | `beancount_repo.py` | 读写 `.bean` 文件，封装 beancount 解析器 |
| Gateway | `embedding_client.py` | 调用兼容 OpenAI 的 Embedding API |
| Gateway | `vector_store/` | 向量数据库（SQLite 或 JSON fallback） |
| Service | `ledger_service.py` | 核心记账逻辑，协调 parser / vector / RAG |
| Service | `vector_service.py` | 向量库构建与账户召回 |
| Service | `query_service.py` | BQL 查询，生成支出报表 |
| Controller | `controller.py` | Bot 与 Service 之间的边界，统一错误处理 |
| Bot | `telegram_bot.py` | Telegram 消息处理与指令路由 |

## 快速开始

### 1. 环境要求

- Python 3.12+
- 一个 Beancount 账本文件（`.bean`）
- 一个 Telegram Bot Token（通过 [@BotFather](https://t.me/BotFather) 获取）

### 2. 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置文件

在项目根目录创建 `config.yaml`（该文件已被 `.gitignore` 忽略）：

```yaml
beancount:
  filename: /path/to/your/main.bean   # 主账本路径
  write_dir: /path/to/your/ledger/    # 新交易写入目录（当月文件）
  currency: CNY                        # 默认货币
  account_distinguation_range: 3       # 账户名模糊匹配前缀长度

bot:
  telegram:
    token: "YOUR_BOT_TOKEN"
    chat_id: 123456789                 # 你的 Telegram chat_id（仅允许该用户操作）

# 可选：启用 Embedding 向量召回
embedding:
  enable: false
  # url: http://localhost:11434/v1/embeddings
  # model: nomic-embed-text

# 可选：启用 RAG 大模型补全
rag:
  enable: false
  # url: http://localhost:11434/v1/chat/completions
  # model: qwen2.5
```

### 4. 启动

```bash
python -m beanbot telegram -c config.yaml
```

## Telegram 指令

| 指令 | 说明 |
|------|------|
| `/start` | 查看 Bot 运行状态和已运行时长 |
| `/expense` | 查询当月各分类支出 |
| `/bill` | 查询当月账单明细 |
| `/clone [金额]` | 回复一条交易消息，克隆并可选修改金额 |
| `/build` | 重新构建向量数据库（启用 Embedding 时使用） |
| 直接发送文字 | 解析为交易并展示预览，等待确认 |

## 自然语言格式

发送消息的基本格式：

```
<金额> <付款账户> <收款账户或商家名> [描述] [#标签]
```

示例：

```
35 CMB KFC 午饭 #food
120 CMB Expenses:Shopping:Clothing 买了件衬衫
```

- `CMB` 会模糊匹配到 `Assets:Bank:CMB`
- `KFC` 会根据历史账单推断对应的支出账户
- 启用向量召回后，即使账户名不完整也能智能补全

## 向量召回与 RAG（可选）

当直接解析失败时，BeanBot 按以下优先级尝试补全：

1. **向量召回**（`embedding.enable: true`）：将输入与历史交易做相似度匹配，推断可能的账户组合
2. **RAG 补全**（`rag.enable: true`）：将输入发送给本地大模型，由模型生成完整交易

两者均支持兼容 OpenAI 接口的本地模型（如 Ollama）。

## 开发与测试

测试脚本位于 `beanbot/test/`，以模块方式运行：

```bash
python -m beanbot.test.test_vector_service
python -m beanbot.test.test_sqlite_vector_store_build
```

## 待办 / Roadmap

- [x] Telegram Bot 自然语言记账
- [x] 基于 Embedding 的向量召回
- [x] 本地大模型 RAG 补全
- [ ] 添加 Flask RESTful API，解耦 Bot 与核心服务
- [ ] 基于 Flask 后端构建移动端 Web 界面，支持在手机浏览器中记账

## 依赖

核心依赖：`beancount`、`beanquery`、`python-telegram-bot`、`pyyaml`、`sqlite-vec`、`requests`

完整依赖见 [requirements.txt](requirements.txt)。

## License

[MIT](LICENSE)
