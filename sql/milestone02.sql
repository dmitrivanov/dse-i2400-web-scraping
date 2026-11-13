
-- Retains every existing row and flag; NULL means classification unknown.
USE MY_CUSTOM_BOT;
ALTER TABLE search_results MODIFY COLUMN is_ad BOOLEAN NULL DEFAULT NULL;
