-- 原话独立于运行摘要保存；旧运行保持 NULL。
ALTER TABLE runs ADD COLUMN message TEXT;
