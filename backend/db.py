"""SQLite metadata store. Plain SQL, so moving to PostgreSQL later is mostly a driver swap."""
import contextlib, os, sqlite3

DB_PATH = os.getenv("FOLIO_DB", "folio.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id   INTEGER PRIMARY KEY,
    url  TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS files (
    id         TEXT PRIMARY KEY,
    filename   TEXT NOT NULL,
    size       INTEGER NOT NULL CHECK (size >= 0),
    mode       TEXT NOT NULL DEFAULT 'auto',
    status     TEXT NOT NULL DEFAULT 'uploading' CHECK (status IN ('uploading','complete')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS chunks (
    file_id TEXT    NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    idx     INTEGER NOT NULL,
    node_id INTEGER NOT NULL REFERENCES nodes(id),
    size    INTEGER NOT NULL,
    PRIMARY KEY (file_id, idx)
);
CREATE INDEX IF NOT EXISTS idx_chunks_node ON chunks(node_id);
"""

@contextlib.contextmanager
def tx():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()

def init():
    with tx() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
