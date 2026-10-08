import time, uuid
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel
from .. import config, db, pool
from ..auth import check_host, get_session

router = APIRouter(prefix="/upload", tags=["upload"])

class Init(BaseModel):
    session: str
    filename: str
    size: int
    mode: str = "auto"          # "auto" | "fixed"
    chunk_size_mb: int = 8

@router.post("/init")
def upload_init(b: Init, x_host_token: str | None = Header(None)):
    uid = uuid.uuid4().hex
    with db.tx() as c:
        s = get_session(c, b.session)
        check_host(s, x_host_token)                  # only the host uploads into a session
        c.execute("INSERT INTO files(id,session_id,filename,size,mode) VALUES(?,?,?,?,?)",
                  (uid, s["id"], b.filename, b.size, b.mode))
    first = min(4, config.MAX_CHUNK_MB) if b.mode == "auto" else max(1, min(b.chunk_size_mb, config.MAX_CHUNK_MB))
    return {"upload_id": uid, "replication": config.REPLICAS, "chunk_size_mb": first}

@router.put("/{uid}/chunk/{idx}")
async def upload_chunk(uid: str, idx: int, request: Request):
    with db.tx() as c:
        f = c.execute("SELECT mode, status FROM files WHERE id=?", (uid,)).fetchone()
    if not f or f["status"] != "uploading":
        raise HTTPException(404, "unknown or finished upload")
    data = await request.body()
    order = sorted(range(len(config.NODES)), key=lambda i: (not pool.up[config.NODES[i]], pool.held[i]))
    placed = []
    for i in order:                                  # least-loaded online nodes first; skip failed ones
        if len(placed) == config.REPLICAS:
            break
        url, t0 = config.NODES[i], time.perf_counter()
        try:
            (await pool.client.put(f"{url}/chunks/{uid}/{idx}", content=data)).raise_for_status()
        except Exception:
            pool.up[url] = False
            continue
        pool.tp[url] = 0.7 * pool.tp[url] + 0.3 * (len(data) / config.MB / max(time.perf_counter() - t0, 1e-3))
        pool.held[i] += 1
        placed.append(i)
    if not placed:
        raise HTTPException(503, "no node accepted the chunk")
    with db.tx() as c:
        c.execute("DELETE FROM chunk_replicas WHERE file_id=? AND idx=?", (uid, idx))
        c.execute("INSERT OR REPLACE INTO chunks(file_id,idx,size) VALUES(?,?,?)", (uid, idx, len(data)))
        c.executemany("INSERT INTO chunk_replicas(file_id,idx,node_id) VALUES(?,?,?)", [(uid, idx, i) for i in placed])
    rate = pool.tp[config.NODES[placed[0]]]
    return {"index": idx, "node_index": placed[0], "nodes": placed, "replicas": len(placed), "size": len(data),
            "throughput_mbps": round(rate, 1), "next_chunk_size_mb": pool.recommend(rate) if f["mode"] == "auto" else None}

@router.post("/{uid}/complete")
def upload_complete(uid: str):
    with db.tx() as c:
        f = c.execute("SELECT size FROM files WHERE id=?", (uid,)).fetchone()
        if not f:
            raise HTTPException(404, "unknown upload")
        got, n = c.execute("SELECT COALESCE(SUM(size),0), COUNT(*) FROM chunks WHERE file_id=?", (uid,)).fetchone()
        if got != f["size"]:
            raise HTTPException(400, f"expected {f['size']} bytes, got {got}")
        c.execute("UPDATE files SET status='complete' WHERE id=?", (uid,))
    return {"ok": True, "chunks": n}
