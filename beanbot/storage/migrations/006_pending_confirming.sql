-- confirming：确认请求已占住这条写入、正在落盘，删除对话和丢弃都不能再改它。
-- SQLite 不能修改 CHECK 约束，只能重建表。
CREATE TABLE pending_writes_new(
 id TEXT PRIMARY KEY,
 user_id TEXT NOT NULL REFERENCES users(id),
 run_id TEXT REFERENCES runs(id),
 kind TEXT NOT NULL CHECK(kind IN ('record','budget')),
 payload TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','confirming','confirmed','rejected','expired')),
 commit_sha TEXT,
 created_at TEXT NOT NULL,
 resolved_at TEXT);
INSERT INTO pending_writes_new SELECT * FROM pending_writes;
DROP TABLE pending_writes;
ALTER TABLE pending_writes_new RENAME TO pending_writes;
CREATE INDEX pending_writes_user_status ON pending_writes(user_id,status,created_at);
