-- Apply once if SHOW COLUMNS confirms this nullable column is missing.
USE MY_CUSTOM_BOT;
ALTER TABLE search_runs ADD COLUMN collection_metadata JSON NULL;
