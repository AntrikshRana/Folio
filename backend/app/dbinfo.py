"""Read-only facts about Folio's SQLite database for the stats page's Database tab.

Only structure, counts and timings leave this module: never the contents of any row.
"""
import os, sqlite3, time
from . import config, db, files

_SYNC = {0: "OFF", 1: "NORMAL", 2: "FULL", 3: "EXTRA"}

def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'          # table names come from sqlite_master, but quote them anyway

def _engine(c) -> dict:
    p = lambda name: c.execute(f"PRAGMA {name}").fetchone()[0]
    size, pages = p("page_size"), p("page_count")
    wal = config.DB_PATH + "-wal"
    return {"sqlite": sqlite3.sqlite_version, "journal_mode": p("journal_mode"), "foreign_keys": bool(p("foreign_keys")),
            "synchronous": _SYNC.get(p("synchronous"), "?"), "encoding": p("encoding"), "page_size": size, "pages": pages,
            "free_pages": p("freelist_count"), "bytes": size * pages, "wal_bytes": os.path.getsize(wal) if os.path.exists(wal) else 0}

def _tables(c) -> list[dict]:
    out = []
    for name in [r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]:
        cols = [{"name": r["name"], "type": r["type"], "pk": r["pk"], "notnull": bool(r["notnull"]), "default": r["dflt_value"]}
                for r in c.execute(f"PRAGMA table_info({_q(name)})")]
        groups: dict[int, dict] = {}                     # a composite foreign key spans several rows sharing one id
        for r in c.execute(f"PRAGMA foreign_key_list({_q(name)})"):
            g = groups.setdefault(r["id"], {"from": [], "to": [], "table": r["table"], "on_delete": r["on_delete"]})
            g["from"].append(r["from"]); g["to"].append(r["to"])
        idx = []
        for r in c.execute(f"PRAGMA index_list({_q(name)})"):
            idx.append({"name": r["name"], "unique": bool(r["unique"]), "origin": r["origin"],
                        "columns": [i["name"] for i in c.execute(f"PRAGMA index_info({_q(r['name'])})")]})
        out.append({"name": name, "rows": c.execute(f"SELECT COUNT(*) FROM {_q(name)}").fetchone()[0],
                    "columns": cols, "foreign_keys": list(groups.values()), "indexes": idx})
    return out

def _checks(c) -> list[dict]:
    n = lambda sql, *a: c.execute(sql, a).fetchone()[0]
    quick = [r[0] for r in c.execute("PRAGMA quick_check")]
    return [
        {"name": "Database file is structurally sound", "detail": "PRAGMA quick_check", "bad": 0 if quick == ["ok"] else len(quick)},
        {"name": "No broken foreign keys", "detail": "PRAGMA foreign_key_check", "bad": len(c.execute("PRAGMA foreign_key_check").fetchall())},
        {"name": "Every chunk has at least one stored copy", "detail": "chunks with no row in chunk_replicas", "bad": n(
            "SELECT COUNT(*) FROM chunks k WHERE NOT EXISTS (SELECT 1 FROM chunk_replicas r WHERE r.file_id=k.file_id AND r.idx=k.idx)")},
        {"name": f"Every chunk has {config.REPLICAS} copies", "detail": "can be lower if a node was down during the upload", "bad": n(
            "SELECT COUNT(*) FROM (SELECT 1 FROM chunk_replicas GROUP BY file_id, idx HAVING COUNT(*) < ?)", config.REPLICAS)},
        {"name": "Finished files: chunk bytes add up to the file size", "detail": "SUM(chunks.size) = files.size", "bad": n(
            "SELECT COUNT(*) FROM files f WHERE f.status='complete' AND f.size != (SELECT COALESCE(SUM(k.size),0) FROM chunks k WHERE k.file_id=f.id)")},
        {"name": "Finished files: chunk numbers have no gaps", "detail": "highest index + 1 = number of chunks", "bad": n(
            """SELECT COUNT(*) FROM files f WHERE f.status='complete' AND
               (SELECT COALESCE(MAX(idx)+1,0) FROM chunks k WHERE k.file_id=f.id) != (SELECT COUNT(*) FROM chunks k WHERE k.file_id=f.id)""")},
    ]

def _queries() -> list[tuple[str, str, str]]:
    r = int(config.REPLICAS)
    return [
        ("Chunks and bytes per storage node", "A join with GROUP BY: what the node cards on this page show.",
         "SELECT r.node_id, COUNT(*) AS copies, SUM(k.size) AS bytes\nFROM chunk_replicas r\nJOIN chunks k ON k.file_id = r.file_id AND k.idx = r.idx\nGROUP BY r.node_id"),
        ("Under-replicated chunks", "GROUP BY with HAVING: finds chunks that have fewer copies than intended.",
         f"SELECT file_id, idx, COUNT(*) AS copies\nFROM chunk_replicas\nGROUP BY file_id, idx\nHAVING COUNT(*) < {r}"),
        ("Room storage in use", "The aggregate behind the room-storage limit; the date filter ignores abandoned uploads.",
         f"SELECT session_id, COALESCE(SUM(size), 0) AS used\nFROM files\nWHERE {files.LIVE}\nGROUP BY session_id"),
        ("Finished files with their uploader", "A correlated subquery that looks up each uploader's name.",
         "SELECT f.id,\n  (SELECT m.name FROM session_members m\n   WHERE m.session_id = f.session_id AND m.member_id = f.member_id) AS uploader\nFROM files f\nWHERE f.status = 'complete'"),
        ("Copies on one node, using the index", "idx_replicas_node lets SQLite jump straight to the rows for one node.",
         "SELECT COUNT(*) FROM chunk_replicas WHERE node_id = 0"),
        ("The same query with indexes switched off", "NOT INDEXED forces a full table scan. Compare the plan with the query above.",
         "SELECT COUNT(*) FROM chunk_replicas NOT INDEXED WHERE node_id = 0"),
        ("Newest activity", "Walks the primary key backwards, so no sort is needed.",
         "SELECT id, kind FROM events ORDER BY id DESC LIMIT 40"),
    ]

def _lab(c) -> list[dict]:
    out = []
    for title, why, sql in _queries():
        depth: dict[int, int] = {}
        plan = []
        for r in c.execute("EXPLAIN QUERY PLAN " + sql):
            depth[r["id"]] = d = depth.get(r["parent"], -1) + 1
            plan.append({"detail": r["detail"], "depth": d})
        best, rows = None, 0
        for _ in range(3):                                # best of three, so one slow run does not mislead
            t0 = time.perf_counter()
            rows = len(c.execute(sql).fetchall())
            dt = time.perf_counter() - t0
            best = dt if best is None else min(best, dt)
        out.append({"title": title, "why": why, "sql": sql, "plan": plan, "rows": rows, "ms": round(best * 1000, 3)})
    return out

def snapshot() -> dict:
    with db.tx() as c:
        return {"now": time.time(), "engine": _engine(c), "tables": _tables(c), "checks": _checks(c), "queries": _lab(c)}

def demo() -> dict:
    """Constraints, a rolled-back transaction and a cascade, on a throwaway in-memory copy of the real schema."""
    m = sqlite3.connect(":memory:", isolation_level=None)         # autocommit: the steps control their own transactions
    m.execute("PRAGMA foreign_keys=ON")
    m.executescript(db.SCHEMA)
    count = lambda: {t: m.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("files", "chunks", "chunk_replicas")}
    steps = []
    def add(title, why, sql, outcome, message):
        steps.append({"title": title, "why": why, "sql": sql, "outcome": outcome, "message": message, "counts": count()})
    seed = """INSERT INTO nodes(id,url) VALUES (0,'a'),(1,'b'),(2,'c');
INSERT INTO sessions(id,code,host_token,title,expires_at) VALUES ('s1','DEMO-0000','x','demo',datetime('now','+1 hour'));
INSERT INTO files(id,session_id,filename,size,status) VALUES ('f1','s1','demo.bin',3,'complete');
INSERT INTO chunks(file_id,idx,size) VALUES ('f1',0,1),('f1',1,1),('f1',2,1);
INSERT INTO chunk_replicas(file_id,idx,node_id) VALUES ('f1',0,0),('f1',0,1),('f1',1,1),('f1',1,2),('f1',2,2),('f1',2,0);"""
    m.executescript(seed)
    add("Start with one 3-chunk file", "Each chunk is stored on two of three nodes, as Folio does.", seed.split("\n", 1)[1], "ok", "1 file, 3 chunks and 6 copies stored.")

    sql = "INSERT INTO chunk_replicas(file_id, idx, node_id) VALUES ('f1', 9, 0);"
    try:
        m.execute(sql); add("Foreign key: a copy of a chunk that does not exist", "", sql, "ok", "Accepted (unexpected).")
    except sqlite3.IntegrityError as e:
        add("Foreign key: a copy of a chunk that does not exist", "The database refuses rows that point at nothing.", sql, "error", str(e))

    sql = "UPDATE files SET status = 'bogus' WHERE id = 'f1';"
    try:
        m.execute(sql); add("CHECK constraint: an invalid status", "", sql, "ok", "Accepted (unexpected).")
    except sqlite3.IntegrityError as e:
        add("CHECK constraint: an invalid status", "Only 'uploading' and 'complete' are allowed.", sql, "error", str(e))

    sql = ("BEGIN;\nINSERT INTO chunks(file_id, idx, size) VALUES ('f1', 3, 1);\n"
           "INSERT INTO chunk_replicas(file_id, idx, node_id) VALUES ('f1', 3, 99);   -- node 99 does not exist\nROLLBACK;")
    m.execute("BEGIN")
    m.execute("INSERT INTO chunks(file_id, idx, size) VALUES ('f1', 3, 1)")
    inside = count()["chunks"]
    try:
        m.execute("INSERT INTO chunk_replicas(file_id, idx, node_id) VALUES ('f1', 3, 99)")
        err = "accepted (unexpected)"
    except sqlite3.IntegrityError as e:
        err = str(e)
    m.execute("ROLLBACK")
    add("Atomic transaction: all or nothing", "Half-finished work vanishes when any step fails.", sql, "error",
        f"The second insert failed ({err}). Inside the transaction there were {inside} chunks; after ROLLBACK there are {count()['chunks']}.")

    sql = "DELETE FROM files WHERE id = 'f1';"
    m.execute(sql)
    add("Cascade: one DELETE cleans up everything below it", "ON DELETE CASCADE is how cancelling an upload removes its chunks and copies.", sql, "ok",
        "1 file row deleted; its chunks and copies went with it.")
    m.close()
    return {"note": "Runs in a throwaway in-memory database that uses Folio's real schema. Your data is not touched.", "steps": steps}
