-- 待确认写入：Agent 只产出 diff，落盘由用户点确认（ADR 0012）。
-- 非账务数据，确认后这条记录作为审计痕迹留着，commit_sha 指回账本里的真身。
CREATE TABLE pending_writes(
 id TEXT PRIMARY KEY,
 user_id TEXT NOT NULL REFERENCES users(id),
 run_id TEXT REFERENCES runs(id),
 kind TEXT NOT NULL CHECK(kind IN ('record','budget')),
 payload TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','confirmed','rejected','expired')),
 commit_sha TEXT,
 created_at TEXT NOT NULL,
 resolved_at TEXT);
CREATE INDEX pending_writes_user_status ON pending_writes(user_id,status,created_at);
