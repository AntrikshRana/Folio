"""SQLite metadata store. Plain SQL, so moving to PostgreSQL later is mostly a driver swap."""
import contextlib, os, sqlite3
from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS sessions (
    id         TEXT PRIMARY KEY,
    code       TEXT NOT NULL UNIQUE,                 -- shared with guests, e.g. K7Q2-9XMA
    host_token TEXT NOT NULL,                        -- secret kept by the host's browser
    title      TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS session_members (
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    role       TEXT NOT NULL CHECK (role IN ('host','guest')),
    joined_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (session_id, name)
);
CREATE TABLE IF NOT EXISTS files (
    id         TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    filename   TEXT NOT NULL,
    size       INTEGER NOT NULL CHECK (size >= 0),
    mode       TEXT NOT NULL DEFAULT 'auto',
    status     TEXT NOT NULL DEFAULT 'uploading' CHECK (status IN ('uploading','complete')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS chunks (
    file_id TEXT    NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    idx     INTEGER NOT NULL,
    size    INTEGER NOT NULL,
    PRIMARY KEY (file_id, idx)
);
CREATE TABLE IF NOT EXISTS chunk_replicas (          -- one row per stored copy of a chunk
    file_id TEXT    NOT NULL,
    idx     INTEGER NOT NULL,
    node_id INTEGER NOT NULL REFERENCES nodes(id),
    PRIMARY KEY (file_id, idx, node_id),
    FOREIGN KEY (file_id, idx) REFERENCES chunks(file_id, idx) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_replicas_node ON chunk_replicas(node_id);
CREATE INDEX IF NOT EXISTS idx_files_session ON files(session_id);
"""

@contextlib.contextmanager
def tx():
    c = sqlite3.connect(config.DB_PATH)
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

def _cols(c, table):
    return [r["name"] for r in c.execute(f"PRAGMA table_info({table})")]

def init():
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with tx() as c:
        c.execute("PRAGMA journal_mode=WAL")
        migrate_p1 = "node_id" in _cols(c, "chunks")           # Part-1 schema: chunks.node_id
        if migrate_p1:
            c.executescript("DROP INDEX IF EXISTS idx_chunks_node; ALTER TABLE chunks RENAME TO chunks_old;")
        if _cols(c, "files") and "session_id" not in _cols(c, "files"):   # older DB: link files to sessions
            c.execute("ALTER TABLE files ADD COLUMN session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE")
        c.executescript(SCHEMA)
        if migrate_p1:
            c.execute("INSERT INTO chunks(file_id,idx,size) SELECT file_id,idx,size FROM chunks_old")
            c.execute("INSERT INTO chunk_replicas(file_id,idx,node_id) SELECT file_id,idx,node_id FROM chunks_old")
            c.execute("DROP TABLE chunks_old")
