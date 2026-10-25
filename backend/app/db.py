"""SQLite connection handling and schema.

A new connection is opened per request (and per background job) — SQLite
connections must not be shared across threads. Foreign keys cascade, so
deleting a meeting removes all of its derived rows in one transaction.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    title             TEXT NOT NULL,
    source_filename   TEXT,
    source            TEXT NOT NULL DEFAULT 'upload',   -- upload | ami | sample
    transcript        TEXT NOT NULL,
    reference_summary TEXT,
    status            TEXT NOT NULL DEFAULT 'pending',  -- pending | running | done | failed
    error             TEXT,
    word_count        INTEGER,
    sentence_count    INTEGER,
    speaker_count     INTEGER,
    options_json      TEXT,
    stage             TEXT,                             -- current analysis step
    notes_json        TEXT,                             -- warnings/fallbacks from the last run
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    analyzed_at       TEXT
);

CREATE TABLE IF NOT EXISTS summaries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id  INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    method      TEXT NOT NULL,            -- tfidf | distilbart
    status      TEXT NOT NULL,            -- ok | fallback | skipped
    text        TEXT,
    note        TEXT,
    model_name  TEXT,
    rouge1      REAL,
    rouge2      REAL,
    rougeL      REAL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (meeting_id, method)
);

CREATE TABLE IF NOT EXISTS sentences (
    meeting_id  INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    idx         INTEGER NOT NULL,
    speaker     TEXT,
    text        TEXT NOT NULL,
    embedding   BLOB,                     -- float32 vector, NULL if no embedder
    PRIMARY KEY (meeting_id, idx)
);

CREATE TABLE IF NOT EXISTS entities (
    meeting_id  INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    text        TEXT NOT NULL,
    label       TEXT NOT NULL,
    count       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS keywords (
    meeting_id  INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    rank        INTEGER NOT NULL,
    keyword     TEXT NOT NULL,
    score       REAL NOT NULL,
    method      TEXT NOT NULL             -- keybert | tfidf_fallback
);

CREATE TABLE IF NOT EXISTS extractions (
    meeting_id      INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,        -- action | decision | risk | question | deadline
    text            TEXT NOT NULL,
    owner           TEXT,
    deadline        TEXT,
    speaker         TEXT,
    sentence_index  INTEGER
);

CREATE INDEX IF NOT EXISTS ix_sentences_meeting   ON sentences(meeting_id);
CREATE INDEX IF NOT EXISTS ix_entities_meeting    ON entities(meeting_id);
CREATE INDEX IF NOT EXISTS ix_keywords_meeting    ON keywords(meeting_id);
CREATE INDEX IF NOT EXISTS ix_extractions_meeting ON extractions(meeting_id);
"""


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        # A job that was running when the server stopped will never finish.
        conn.execute(
            "UPDATE meetings SET status='failed', error='Analysis was interrupted "
            "(server stopped). Run it again.' WHERE status IN ('pending','running')"
        )
        conn.commit()
    finally:
        conn.close()


@contextmanager
def transaction(db_path: str):
    """Open a connection, commit on success, roll back on error."""
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
