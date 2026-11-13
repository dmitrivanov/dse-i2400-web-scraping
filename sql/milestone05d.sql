-- Run once on an existing database after checking SHOW COLUMNS.
-- Nullable additions preserve every historical row and foreign key.
USE MY_CUSTOM_BOT;
ALTER TABLE search_runs ADD COLUMN provider VARCHAR(100) NULL;
ALTER TABLE search_results ADD COLUMN page_number INT NULL;
