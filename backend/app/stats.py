"""Activity log + counters behind the live stats page.

record() never raises: a stats problem must not break an upload or a download.
Call it AFTER your own db.tx() block has closed (SQLite allows one writer at a time).
"""
import logging, math, time
from . import config, db, pool

log = logging.getLogger("folio.stats")
KEEP_EVENTS = 5000          # older events are trimmed; totals live in stat_counters, so they are not lost
MAX_CELLS = 120             # a file with more chunks than this is shown in buckets
_COUNTER = {"upload_started": "uploads_started", "upload_completed": "uploads_completed",
            "upload_cancelled": "uploads_cancelled", "chunk_stored": "chunks_stored",
            "download_started": "downloads", "chunk_served": "chunks_served", "failover": "failovers"}
_n = 0

def label(i: int) -> str:
    return f"Node {chr(65 + i)}" if i < 26 else f"Node {i + 1}"

def _bump(c, name, by=1):
    c.execute("INSERT INTO stat_counters(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=value+excluded.value", (name, by))

def record(kind, file_id=None, idx=None, nodes=None, size=None, detail=None):
    global _n
    try:
        with db.tx() as c:
            c.execute("INSERT INTO events(ts,kind,file_id,idx,nodes,size,detail) VALUES(?,?,?,?,?,?,?)",
                      (time.time(), kind, file_id, idx, ",".join(map(str, nodes)) if nodes else None, size, detail))
            if kind in _COUNTER:
                _bump(c, _COUNTER[kind])
            if kind == "chunk_stored" and size:
                _bump(c, "bytes_stored", size)
            _n += 1
            if _n % 200 == 0:
                c.execute("DELETE FROM events WHERE id <= (SELECT MAX(id) FROM events) - ?", (KEEP_EVENTS,))
    except Exception:
        log.warning("could not record %s event", kind, exc_info=True)

def _cells(plan):
    step = max(1, math.ceil(len(plan) / MAX_CELLS))
    out = []
    for i in range(0, len(plan), step):
        g = plan[i:i + step]
        out.append({"from": i, "chunks": len(g), "nodes": sorted(set().union(*g)), "copies": min(len(x) for x in g)})
    return out

def snapshot() -> dict:
    """Everything the stats page shows, in one read. Names of files and people are never included."""
    now = time.time()
    with db.tx() as c:
        per = {r["node_id"]: (r["n"], r["b"]) for r in c.execute(
            """SELECT r.node_id, COUNT(*) AS n, COALESCE(SUM(k.size),0) AS b FROM chunk_replicas r
               JOIN chunks k ON k.file_id = r.file_id AND k.idx = r.idx GROUP BY r.node_id""")}
        nodes = [{"id": i, "label": label(i), "online": bool(pool.up[u]),
                  "chunks": per.get(i, (0, 0))[0], "bytes": per.get(i, (0, 0))[1]} for i, u in enumerate(config.NODES)]
        counters = {r["name"]: r["value"] for r in c.execute("SELECT name, value FROM stat_counters")}
        n_files, bytes_files = c.execute("SELECT COUNT(*), COALESCE(SUM(size),0) FROM files WHERE status='complete'").fetchone()
        uploads = [{"id": r["id"][:4], "size": r["size"], "chunks": r["chunks"], "received": r["got"]} for r in c.execute(
            """SELECT f.id, f.size, COUNT(k.idx) AS chunks, COALESCE(SUM(k.size),0) AS got FROM files f
               LEFT JOIN chunks k ON k.file_id = f.id
               WHERE f.status='uploading' AND f.created_at > datetime('now','-1 hour')
               GROUP BY f.id ORDER BY f.created_at DESC, f.rowid DESC LIMIT 10""")]
        recent = c.execute("SELECT id, size, status FROM files ORDER BY created_at DESC, rowid DESC LIMIT 6").fetchall()
        plans = {}
        if recent:
            ids = [r["id"] for r in recent]
            for r in c.execute(f"""SELECT k.file_id, GROUP_CONCAT(r.node_id) AS nodes FROM chunks k
                JOIN chunk_replicas r ON r.file_id = k.file_id AND r.idx = k.idx
                WHERE k.file_id IN ({",".join("?" * len(ids))}) GROUP BY k.file_id, k.idx ORDER BY k.file_id, k.idx""", ids):
                plans.setdefault(r["file_id"], []).append(sorted(int(x) for x in r["nodes"].split(",")))
        files = [{"id": r["id"][:4], "size": r["size"], "status": r["status"], "chunks": len(plans.get(r["id"], [])),
                  "cells": _cells(plans[r["id"]]) if r["id"] in plans else []} for r in recent]
        events = [{"id": r["id"], "ts": r["ts"], "kind": r["kind"], "file": (r["file_id"] or "")[:4], "idx": r["idx"],
                   "nodes": [int(x) for x in r["nodes"].split(",")] if r["nodes"] else [], "size": r["size"], "detail": r["detail"]}
                  for r in c.execute("SELECT id, ts, kind, file_id, idx, nodes, size, detail FROM events ORDER BY id DESC LIMIT 40")]
        first = int(now // 10) - 29                              # 30 buckets of 10 s = the last 5 minutes
        b = {r["b"]: r["s"] for r in c.execute(
            "SELECT CAST(ts/10 AS INTEGER) AS b, SUM(size) AS s FROM events WHERE kind='chunk_stored' AND ts >= ? GROUP BY b", (first * 10,))}
    return {"now": now, "replicas": config.REPLICAS, "nodes": nodes,
            "totals": {"files": n_files, "bytes": bytes_files, "uploads_active": len(uploads), **counters},
            "uploads": uploads, "files": files, "events": events,
            "throughput": [{"t": (first + i) * 10, "bytes": b.get(first + i, 0)} for i in range(30)]}
