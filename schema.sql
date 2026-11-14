-- Tables for the core cited Q&A (docs/architecture.md). Needs MariaDB 11.7 or later
-- (VECTOR); loading history with real timestamps needs 10.11+ (system_versioning_insert_history).
-- Runtime-agnostic: runs the same on Docker, a portable install or a cloud MariaDB.
--   mariadb -u <user> -p <database> < schema.sql

-- Every saved version of every article, from dataset M. MariaDB keeps earlier versions as
-- history rows; the loader writes them with Wikipedia's real edit times, so
-- FOR SYSTEM_TIME AS OF '2015-06-01' means "what Wikipedia showed on 1 June 2015".
-- Based on mariadb-system-versioning-wikipedia/schema.sql, plus parent_id and anonymous.
CREATE TABLE IF NOT EXISTS article (
  page_id     INT UNSIGNED NOT NULL,          -- Wikipedia's own id
  title       VARCHAR(255) NOT NULL,          -- can change over time: pages get renamed
  rev_id      INT UNSIGNED NOT NULL,          -- Wikipedia's id of this version
  parent_id   INT UNSIGNED,                   -- the version this one was edited from
  user        VARCHAR(255),                   -- user name, IP address or temporary account
  anonymous   BOOL NOT NULL DEFAULT 0,        -- saved without an account
  comment     TEXT,                           -- the edit summary
  minor       BOOL NOT NULL DEFAULT 0,
  sha1        VARCHAR(40),                    -- same hash = same text: how reverts are found
  len         INT UNSIGNED,                   -- size of the text in bytes (dataset column: bytes)
  text        MEDIUMTEXT COMPRESSED NOT NULL, -- raw wikitext
  row_start   TIMESTAMP(6) GENERATED ALWAYS AS ROW START INVISIBLE,
  row_end     TIMESTAMP(6) GENERATED ALWAYS AS ROW END INVISIBLE,
  PERIOD FOR SYSTEM_TIME (row_start, row_end),
  PRIMARY KEY (page_id),
  KEY (sha1),
  -- MariaDB's own history index is ordered by row_end, so "as of 2005" would walk every later
  -- version. This one lets it start from the versions that began before the date.
  KEY start_key (page_id, row_start)
) CHARACTER SET utf8mb4
  WITH SYSTEM VERSIONING
  PARTITION BY SYSTEM_TIME INTERVAL 1 YEAR STARTS '2002-01-01 00:00:00' AUTO PARTITIONS 26;

-- The current passages of each Finnish article, cut from its newest version: one per section
-- (the lead included), long sections split at paragraphs to ~300 words. A plain table, rebuilt
-- by build_passages.py. Paragraph history is a later feature with its own table.
CREATE TABLE IF NOT EXISTS passage (
  passage_id  INT UNSIGNED NOT NULL AUTO_INCREMENT,
  page_id     INT UNSIGNED NOT NULL,
  rev_id      INT UNSIGNED NOT NULL,          -- the revision the text came from: citations link here
  title       VARCHAR(255) NOT NULL,          -- article title
  position    SMALLINT UNSIGNED NOT NULL,     -- order within the article, from 0
  heading     VARCHAR(255),                   -- the section heading (NULL for the lead)
  text        TEXT NOT NULL,                  -- plain text, as shown to readers
  text_hash   BINARY(32) NOT NULL,            -- SHA-256 of the embedding input
                                              -- (title \n heading \n text): joins to passage_vector
  PRIMARY KEY (passage_id),
  UNIQUE KEY (page_id, position),
  KEY (text_hash),
  -- Keyword half of hybrid search. Queried in boolean mode with prefix terms (Kekko*), because
  -- FULLTEXT has no Finnish stemming.
  FULLTEXT (title, heading, text)
) CHARACTER SET utf8mb4;

-- One vector per distinct paragraph text, not per position: the same text is embedded once,
-- and older paragraph versions can be added later without changing this table.
-- A VECTOR INDEX column must be NOT NULL, so "has a row" = "is embedded".
CREATE TABLE IF NOT EXISTS passage_vector (
  text_hash   BINARY(32) NOT NULL,
  model       VARCHAR(50) NOT NULL,           -- which model made it; all rows must match
  embedding   VECTOR(1024) NOT NULL,
  PRIMARY KEY (text_hash),
  -- M=16: with 1024 dimensions the default M=6 found only 79% of the true top 10 in the starter.
  VECTOR INDEX (embedding) M=16 DISTANCE=cosine
);

-- The shipped whole-article vectors from dataset S (fi, sv, en), for topic search and the
-- Swedish and English articles. Same shape as mariadb-vector-wikipedia-rag.
CREATE TABLE IF NOT EXISTS article_vector (
  lang        CHAR(2) NOT NULL,
  page_id     INT UNSIGNED NOT NULL,
  model       VARCHAR(50) NOT NULL,
  truncated   BOOL NOT NULL,                  -- article was longer than the model reads
  embedding   VECTOR(1024) NOT NULL,
  PRIMARY KEY (lang, page_id),
  VECTOR INDEX (embedding) M=16 DISTANCE=cosine
);

-- One row per revert: a version whose text (same sha1) already existed earlier in the article,
-- with other versions in between. Filled once after loading by scripts/build_reverts.py.
-- Survival time of the undone text = reverted_at - undone_since.
CREATE TABLE IF NOT EXISTS revert_event (
  page_id          INT UNSIGNED NOT NULL,
  rev_id           INT UNSIGNED NOT NULL,     -- the reverting version
  reverted_at      DATETIME(6) NOT NULL,      -- UTC
  user             VARCHAR(255),              -- who reverted
  anonymous        BOOL NOT NULL DEFAULT 0,
  restored_rev_id  INT UNSIGNED NOT NULL,     -- the earlier version whose text came back
  undone_since     DATETIME(6) NOT NULL,      -- when the first undone edit was saved
  undone_edits     INT UNSIGNED NOT NULL,     -- how many versions were undone
  undone_user      VARCHAR(255),              -- author of the first undone edit
  undone_anonymous BOOL NOT NULL DEFAULT 0,   -- undoing anonymous edits is mostly cleanup
  PRIMARY KEY (page_id, rev_id),
  KEY (reverted_at),
  KEY (user), KEY (undone_user)
) CHARACTER SET utf8mb4;
