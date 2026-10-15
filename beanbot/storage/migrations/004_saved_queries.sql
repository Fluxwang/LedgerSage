CREATE TABLE saved_queries(
 id TEXT PRIMARY KEY,
 user_id TEXT NOT NULL REFERENCES users(id),
 question TEXT NOT NULL,
 run_id TEXT NOT NULL REFERENCES runs(id),
 created_at TEXT NOT NULL,
 UNIQUE(user_id, question));
CREATE INDEX saved_queries_user_created ON saved_queries(user_id, created_at);
