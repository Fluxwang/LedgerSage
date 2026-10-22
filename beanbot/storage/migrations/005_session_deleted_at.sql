-- 只隐藏对话，保留运行、待确认写入、常用查询和 checkpoint 的审计记录。
ALTER TABLE sessions ADD COLUMN deleted_at TEXT;
