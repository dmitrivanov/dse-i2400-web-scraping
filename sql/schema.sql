-- Run manually in MySQL Workbench. Existing objects and records are preserved.
CREATE DATABASE IF NOT EXISTS MY_CUSTOM_BOT
    CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE MY_CUSTOM_BOT;

CREATE TABLE IF NOT EXISTS search_queries (
    id BIGINT NOT NULL AUTO_INCREMENT,
    query_text VARCHAR(1000) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS search_runs (
    id BIGINT NOT NULL AUTO_INCREMENT,
    query_id BIGINT NOT NULL,
    engine VARCHAR(50) NOT NULL,
    search_type VARCHAR(10) NULL,
    provider VARCHAR(100) NULL,
    collection_metadata JSON NULL,
    status VARCHAR(30) NOT NULL,
    raw_count INT NOT NULL DEFAULT 0,
    ad_count INT NOT NULL DEFAULT 0,
    duplicate_count INT NOT NULL DEFAULT 0,
    final_count INT NOT NULL DEFAULT 0,
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at DATETIME NULL,
    error_message TEXT NULL,
    PRIMARY KEY (id),
    INDEX idx_search_runs_query_id (query_id),
    CONSTRAINT fk_search_runs_query_id FOREIGN KEY (query_id)
        REFERENCES search_queries(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT chk_search_runs_counts CHECK (raw_count >= 0 AND ad_count >= 0 AND duplicate_count >= 0 AND final_count >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS search_results (
    id BIGINT NOT NULL AUTO_INCREMENT,
    run_id BIGINT NOT NULL,
    title TEXT NULL,
    original_url TEXT NOT NULL,
    normalized_url TEXT NULL,
    snippet TEXT NULL,
    displayed_link TEXT NULL,
    result_rank INT NULL,
    page_number INT NULL,
    is_ad BOOLEAN NULL DEFAULT NULL,
    is_duplicate BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_search_results_run_id (run_id),
    CONSTRAINT fk_search_results_run_id FOREIGN KEY (run_id)
        REFERENCES search_runs(id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS capture_artifacts (
    id BIGINT NOT NULL AUTO_INCREMENT,
    run_id BIGINT NOT NULL,
    screenshot_path VARCHAR(1000) NULL,
    ocr_text_path VARCHAR(1000) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_capture_artifacts_run_id (run_id),
    CONSTRAINT fk_capture_artifacts_run_id FOREIGN KEY (run_id)
        REFERENCES search_runs(id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS ai_responses (
    id BIGINT NOT NULL AUTO_INCREMENT,
    query_id BIGINT NOT NULL,
    run_id BIGINT NULL,
    provider VARCHAR(50) NOT NULL,
    model_name VARCHAR(100) NULL,
    response_text LONGTEXT NOT NULL,
    requested_model VARCHAR(100) NULL,
    prompt_text TEXT NULL,
    prompt_version VARCHAR(50) NULL,
    grounding_metadata JSON NULL,
    usage_metadata JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    INDEX idx_ai_responses_run_id (run_id),
    CONSTRAINT fk_ai_responses_run_id FOREIGN KEY (run_id)
        REFERENCES search_runs(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    INDEX idx_ai_responses_query_id (query_id),
    CONSTRAINT fk_ai_responses_query_id FOREIGN KEY (query_id)
        REFERENCES search_queries(id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS ai_summaries (
    id BIGINT NOT NULL AUTO_INCREMENT,
    query_id BIGINT NOT NULL,
    run_id BIGINT NULL,
    summary_text LONGTEXT NOT NULL,
    source_response_id BIGINT NULL,
    prompt_text LONGTEXT NULL,
    prompt_version VARCHAR(50) NULL,
    usage_metadata JSON NULL,
    summarizer VARCHAR(100) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_ai_summary_response (source_response_id),
    CONSTRAINT fk_ai_summary_response FOREIGN KEY (source_response_id)
        REFERENCES ai_responses(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    INDEX idx_ai_summaries_run_id (run_id),
    CONSTRAINT fk_ai_summaries_run_id FOREIGN KEY (run_id)
        REFERENCES search_runs(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    INDEX idx_ai_summaries_query_id (query_id),
    CONSTRAINT fk_ai_summaries_query_id FOREIGN KEY (query_id)
        REFERENCES search_queries(id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


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
