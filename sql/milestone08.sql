-- Inspect SHOW COLUMNS first; run each missing addition once. No startup migration.
USE MY_CUSTOM_BOT;
ALTER TABLE search_runs ADD COLUMN search_type VARCHAR(10) NULL;
ALTER TABLE search_results ADD COLUMN displayed_link TEXT NULL;
ALTER TABLE ai_responses ADD COLUMN run_id BIGINT NULL,
    ADD INDEX idx_ai_responses_run_id (run_id),
    ADD CONSTRAINT fk_ai_responses_run_id FOREIGN KEY (run_id)
        REFERENCES search_runs(id) ON DELETE RESTRICT ON UPDATE RESTRICT;
ALTER TABLE ai_summaries ADD COLUMN run_id BIGINT NULL,
    ADD INDEX idx_ai_summaries_run_id (run_id),
    ADD CONSTRAINT fk_ai_summaries_run_id FOREIGN KEY (run_id)
        REFERENCES search_runs(id) ON DELETE RESTRICT ON UPDATE RESTRICT;
-- engine is direct historical evidence of a Web retrieval, including failed runs.
UPDATE search_runs SET search_type='web'
WHERE search_type IS NULL AND engine IN ('google','bing','duckduckgo');
-- Do not guess run links for historical AI rows from query_id alone.
