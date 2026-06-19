# BeanBot

**Language:** English | [中文](README_ZH.md)

---

BeanBot is a Telegram bot that lets you record [Beancount](https://github.com/beancount/beancount) transactions using natural language. Just send a message like `35 CMB KFC lunch` and BeanBot will generate a properly formatted double-entry accounting entry, waiting for your confirmation before writing it to the ledger.

> Inspired by [beancount-bot](https://github.com/StdioA/beancount-bot) by StdioA.

## Features

- **Natural language input**: Send a description, get a Beancount transaction
- **Interactive confirmation**: Inline Submit / Cancel buttons before writing
- **Vector recall**: Embedding-based account completion from transaction history
- **RAG completion**: LLM-powered completion for complex or ambiguous input
- **Query commands**: `/expense` and `/bill` to view monthly spending summaries
- **Clone transactions**: Reply to an existing transaction with `/clone` to duplicate it
- **Hot reload**: Automatically reloads the ledger file when it changes on disk

## Architecture

```
gateways → services → controller → bots
```

| Layer | Module | Description |
|-------|--------|-------------|
| Gateway | `beancount_repo.py` | Read/write `.bean` files, wraps beancount parser |
| Gateway | `embedding_client.py` | OpenAI-compatible Embedding API client |
| Gateway | `vector_store/` | Vector database (SQLite or JSON fallback) |
| Service | `ledger_service.py` | Core accounting logic, coordinates parser / vector / RAG |
| Service | `vector_service.py` | Vector DB build and account recall |
| Service | `query_service.py` | BQL queries for expense reports |
| Controller | `controller.py` | Boundary between bot and services, unified error handling |
| Bot | `telegram_bot.py` | Telegram message handling and command routing |

## Getting Started

### 1. Requirements

- Python 3.12+
- A Beancount ledger file (`.bean`)
- A Telegram Bot Token (get one from [@BotFather](https://t.me/BotFather))

### 2. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configuration

Create `config.yaml` in the project root (it is gitignored):

```yaml
beancount:
  filename: /path/to/your/main.bean   # Main ledger file
  write_dir: /path/to/your/ledger/    # Directory for new transactions (current month file)
  currency: CNY                        # Default currency
  account_distinguation_range: 3       # Prefix length for fuzzy account matching

bot:
  telegram:
    token: "YOUR_BOT_TOKEN"
    chat_id: 123456789                 # Your Telegram chat_id (only this user can operate)

# Optional: enable Embedding-based vector recall
embedding:
  enable: false
  # url: http://localhost:11434/v1/embeddings
  # model: nomic-embed-text

# Optional: enable RAG completion via LLM
rag:
  enable: false
  # url: http://localhost:11434/v1/chat/completions
  # model: qwen2.5
```

### 4. Run

```bash
python -m beanbot telegram -c config.yaml
```

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Show bot status and uptime |
| `/expense` | Query current month's expenses by category |
| `/bill` | Query current month's bill details |
| `/clone [amount]` | Reply to a transaction message to clone it, optionally with a new amount |
| `/build` | Rebuild the vector database (when embedding is enabled) |
| Plain text | Parsed as a transaction and shown as a preview awaiting confirmation |

## Natural Language Format

Basic message format:

```
<amount> <from-account> <to-account-or-payee> [description] [#tag]
```

Examples:

```
35 CMB KFC lunch #food
120 CMB Expenses:Shopping:Clothing bought a shirt
```

- `CMB` fuzzy-matches to `Assets:Bank:CMB`
- `KFC` is inferred from transaction history to its expense account
- With vector recall enabled, partial or misspelled account names are completed automatically

## Vector Recall & RAG (Optional)

When direct parsing fails, BeanBot falls back in this order:

1. **Vector recall** (`embedding.enable: true`): Finds similar historical transactions and infers likely account combinations
2. **RAG completion** (`rag.enable: true`): Sends the input to a local LLM to generate a complete transaction

Both support local models via any OpenAI-compatible API (e.g. Ollama).

## Development & Testing

Test scripts are in `beanbot/test/` and must be run as modules from the repo root:

```bash
python -m beanbot.test.test_vector_service
python -m beanbot.test.test_sqlite_vector_store_build
```

## Roadmap

- [x] Telegram Bot with natural language transaction input
- [x] Vector recall via Embedding
- [x] RAG completion via local LLM
- [ ] Flask RESTful API to decouple the bot from core services
- [ ] Mobile-friendly Web App based on the Flask backend, for recording transactions in the browser

## Dependencies

Core: `beancount`, `beanquery`, `python-telegram-bot`, `pyyaml`, `sqlite-vec`, `requests`

Full list: [requirements.txt](requirements.txt)

## License

[MIT](LICENSE)
