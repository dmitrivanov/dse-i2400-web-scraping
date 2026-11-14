-- Inspect columns first; additive migration, apply missing statements once.
USE MY_CUSTOM_BOT;
ALTER TABLE ai_responses
 ADD COLUMN requested_model VARCHAR(100) NULL,
 ADD COLUMN prompt_text TEXT NULL,
 ADD COLUMN prompt_version VARCHAR(50) NULL,
 ADD COLUMN grounding_metadata JSON NULL,
 ADD COLUMN usage_metadata JSON NULL;
ALTER TABLE ai_summaries
 ADD COLUMN source_response_id BIGINT NULL,
 ADD COLUMN prompt_text LONGTEXT NULL,
 ADD COLUMN prompt_version VARCHAR(50) NULL,
 ADD COLUMN usage_metadata JSON NULL,
 ADD UNIQUE INDEX uq_ai_summary_response (source_response_id),
 ADD CONSTRAINT fk_ai_summary_response FOREIGN KEY (source_response_id)
 REFERENCES ai_responses(id) ON DELETE RESTRICT ON UPDATE RESTRICT;
CREATE TABLE IF NOT EXISTS ai_sources (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 response_id BIGINT NOT NULL,
 chunk_index INT NOT NULL,
 title TEXT NULL,
 url TEXT NOT NULL,
 UNIQUE KEY uq_ai_source_chunk (response_id, chunk_index),
 CONSTRAINT fk_ai_sources_response FOREIGN KEY (response_id)
 REFERENCES ai_responses(id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
