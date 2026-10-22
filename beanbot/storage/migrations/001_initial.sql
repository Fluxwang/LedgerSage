CREATE TABLE users(id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
 password_hash TEXT NOT NULL, ledger_path TEXT, created_at TEXT NOT NULL);
CREATE TABLE user_settings(user_id TEXT PRIMARY KEY REFERENCES users(id),
 account_distinguation_range TEXT NOT NULL DEFAULT '[2,4]', currency TEXT NOT NULL DEFAULT 'CNY',
 confidence_threshold REAL NOT NULL DEFAULT 0.7);
CREATE TABLE invite_codes(code TEXT PRIMARY KEY, used_by TEXT REFERENCES users(id),
 used_at TEXT, created_at TEXT NOT NULL);
CREATE TABLE sessions(id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 thread_id TEXT NOT NULL, title TEXT NOT NULL, created_at TEXT NOT NULL, last_active_at TEXT NOT NULL,
 active_run_id TEXT, pending_at TEXT, UNIQUE(user_id,thread_id));
CREATE TABLE runs(id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
 user_id TEXT NOT NULL REFERENCES users(id), intent TEXT, status TEXT NOT NULL, model TEXT NOT NULL,
 total_ms INTEGER NOT NULL DEFAULT 0, total_tokens INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL, title TEXT NOT NULL);
CREATE TABLE run_steps(id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
 seq INTEGER NOT NULL, kicker TEXT NOT NULL CHECK(kicker IN ('PARSE','CLASSIFY','TOOL','ASK','REPLY')),
-- 步骤类别
--   CLASSIFY 识别意图（记账 / 查询 / 预算……）
--   PARSE    从自然语言中抽取交易字段
--   ASK      信息不足，向用户追问
--   TOOL     操作账本（写入 / 查询 / 设置预算）
--   REPLY    生成最终回复

 title TEXT NOT NULL, duration_ms INTEGER NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(run_id,seq));
CREATE INDEX runs_user_created ON runs(user_id,created_at);
