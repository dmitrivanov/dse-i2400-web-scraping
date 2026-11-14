-- Additive source identity migration. Inspect columns before applying ALTER once.
USE MY_CUSTOM_BOT;
CREATE TABLE IF NOT EXISTS source_catalog (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 url_hash BINARY(32) NOT NULL,
 url TEXT NOT NULL,
 UNIQUE KEY uq_source_url_hash (url_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
ALTER TABLE search_results ADD COLUMN source_id BIGINT NULL,
 ADD INDEX idx_search_results_source_id (source_id),
 ADD CONSTRAINT fk_search_results_source_id FOREIGN KEY (source_id)
 REFERENCES source_catalog(id) ON DELETE RESTRICT ON UPDATE RESTRICT;
-- Backfill existing valid normalized URLs with source_identity.source_id in Python;
-- retain every original observation, rank, snippet and URL.
