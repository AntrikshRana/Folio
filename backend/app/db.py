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
    expires_at TEXT NOT NULL,
    upload_policy       TEXT    NOT NULL DEFAULT 'approval',   -- 'open': guests upload unless blocked; 'approval': only approved guests
    max_file_mb         INTEGER NOT NULL DEFAULT 50,           -- per file, for guests (the host is exempt)
    max_files_per_guest INTEGER NOT NULL DEFAULT 5,
    room_quota_mb       INTEGER NOT NULL DEFAULT 1024          -- all files in the room together
);
CREATE TABLE IF NOT EXISTS session_members (
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    role       TEXT NOT NULL CHECK (role IN ('host','guest')),
    joined_at  TEXT NOT NULL DEFAULT (datetime('now')),
    member_id  TEXT,                                 -- public handle (safe to show, used by the host to point at someone)
    token_hash TEXT,                                 -- sha256 of the member's secret token; the token itself is never stored
    can_upload INTEGER,                              -- NULL: follow the room policy; 1: host allowed them; 0: host blocked them
    PRIMARY KEY (session_id, name)
);
CREATE TABLE IF NOT EXISTS files (
    id         TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    filename   TEXT NOT NULL,
    size       INTEGER NOT NULL CHECK (size >= 0),
    mode       TEXT NOT NULL DEFAULT 'auto',
    status     TEXT NOT NULL DEFAULT 'uploading' CHECK (status IN ('uploading','complete')),
    member_id  TEXT,                                 -- who uploaded it (session_members.member_id)
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
CREATE TABLE IF NOT EXISTS events (                  -- activity log behind the live stats page (trimmed in stats.py)
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      REAL NOT NULL,
    kind    TEXT NOT NULL,
    file_id TEXT,                                    -- no FK: events outlive cancelled files
    idx     INTEGER,
    nodes   TEXT,
    size    INTEGER,
    detail  TEXT
);
CREATE TABLE IF NOT EXISTS stat_counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS texts (                   -- text snippets people share in a room
    id         TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    member_id  TEXT,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_texts_session ON texts(session_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_members_token ON session_members(token_hash);
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
        for table, col, ddl in (("sessions", "upload_policy", "TEXT NOT NULL DEFAULT 'approval'"),
                                ("sessions", "max_file_mb", "INTEGER NOT NULL DEFAULT 50"),
                                ("sessions", "max_files_per_guest", "INTEGER NOT NULL DEFAULT 5"),
                                ("sessions", "room_quota_mb", "INTEGER NOT NULL DEFAULT 1024"),
                                ("session_members", "member_id", "TEXT"), ("session_members", "token_hash", "TEXT"),
                                ("session_members", "can_upload", "INTEGER"), ("files", "member_id", "TEXT")):
            cols = _cols(c, table)
            if cols and col not in cols:                                  # database made by an older version
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
                if col == "upload_policy" and "guests_can_upload" in cols:  # Stage 2 had a single on/off switch: keep its meaning
                    c.execute("UPDATE sessions SET upload_policy='open' WHERE guests_can_upload=1")
        c.executescript(SCHEMA)
        c.execute("UPDATE session_members SET member_id = lower(hex(randomblob(4))) WHERE member_id IS NULL")
        if migrate_p1:
            c.execute("INSERT INTO chunks(file_id,idx,size) SELECT file_id,idx,size FROM chunks_old")
            c.execute("INSERT INTO chunk_replicas(file_id,idx,node_id) SELECT file_id,idx,node_id FROM chunks_old")
            c.execute("DROP TABLE chunks_old")
