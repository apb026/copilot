"""
db.py
Single SQLite file as the entire data layer, with sqlite-vec for
semantic retrieval over resume bullets, projects, and past writing.

Why one file: this is a single-user system. A full Postgres server
is overkill for one person's resume history, and SQLite gives us
zero infra to manage. The tradeoff (no concurrent multi-user writes,
ephemeral disk on Streamlit Cloud) is handled by backup.py.
"""

import sqlite3
import sqlite_vec
import json
import os
from datetime import datetime

DB_PATH = os.environ.get("CAREER_DB_PATH", "data/career.db")
EMBED_DIM = 384  # all-MiniLM-L6-v2 output size


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


SCHEMA = """
-- Raw source material: every distinct piece of career truth.
-- This is the single source of truth the truth-checker validates against.
CREATE TABLE IF NOT EXISTS source_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type TEXT NOT NULL,        -- 'bullet', 'project', 'skill', 'cert', 'summary'
    content TEXT NOT NULL,
    source_label TEXT,              -- e.g. "TCS - System Engineer" for traceability
    tags TEXT,                      -- JSON list, e.g. ["java","backend"]
    created_at TEXT NOT NULL,
    active INTEGER DEFAULT 1        -- soft delete, never hard-delete career history
);

-- Vector index over source_items.content, kept in sync manually on insert.
CREATE VIRTUAL TABLE IF NOT EXISTS source_items_vec USING vec0(
    embedding FLOAT[384]
);
-- maps vec rowid -> source_items.id (sqlite-vec rowids are separate from our PK)
CREATE TABLE IF NOT EXISTS vec_link (
    vec_rowid INTEGER PRIMARY KEY,
    source_item_id INTEGER NOT NULL REFERENCES source_items(id)
);

-- Every JD you've ever pasted/extracted, kept even if you don't apply.
CREATE TABLE IF NOT EXISTS job_descriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT,
    title TEXT,
    raw_text TEXT NOT NULL,
    url TEXT,
    source_platform TEXT,           -- linkedin, indeed, greenhouse, etc.
    parsed_requirements TEXT,       -- JSON
    parsed_responsibilities TEXT,   -- JSON
    parsed_preferred_skills TEXT,   -- JSON
    created_at TEXT NOT NULL
);

-- One row per generated resume version, tied to a JD.
CREATE TABLE IF NOT EXISTS resume_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_description_id INTEGER REFERENCES job_descriptions(id),
    content_markdown TEXT NOT NULL,
    ats_score REAL,
    truth_check_passed INTEGER,     -- 0/1
    truth_check_notes TEXT,         -- JSON list of flagged claims
    skill_gap_notes TEXT,           -- JSON
    user_edited_final TEXT,         -- what you actually sent, after your edits
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cover_letters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_description_id INTEGER REFERENCES job_descriptions(id),
    resume_version_id INTEGER REFERENCES resume_versions(id),
    content TEXT NOT NULL,
    user_edited_final TEXT,
    created_at TEXT NOT NULL
);

-- Lightweight application tracker (manually updated for now).
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_description_id INTEGER REFERENCES job_descriptions(id),
    resume_version_id INTEGER REFERENCES resume_versions(id),
    status TEXT DEFAULT 'drafted',  -- drafted, applied, referred, interview, rejected, ghosted, offer
    applied_at TEXT,
    notes TEXT,
    updated_at TEXT NOT NULL
);

-- Free-text user preferences/edits the system should remember,
-- e.g. "always say STEM OPT, never say visa sponsorship needed"
CREATE TABLE IF NOT EXISTS writing_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    preference_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    active INTEGER DEFAULT 1
);
"""


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def now():
    return datetime.utcnow().isoformat()


if __name__ == "__main__":
    init_db()
    print(f"Initialized DB at {DB_PATH}")
