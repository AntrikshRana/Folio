import asyncio, sqlite3, tempfile, time, uuid
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

async def _spool(request: Request):
    """Receive the chunk into a temp file (RAM only up to 1 MB) so memory stays flat for any chunk size."""
    tmp, size = tempfile.SpooledTemporaryFile(max_size=config.MB), 0
    try:
        async for part in request.stream():
            size += len(part)
            if size > config.MAX_CHUNK_MB * config.MB:
                raise HTTPException(413, f"chunk larger than MAX_CHUNK_MB={config.MAX_CHUNK_MB}")
            tmp.write(part)
    except BaseException:
        tmp.close()
        raise
    return tmp, size

async def _send(tmp):
    tmp.seek(0)
    while block := tmp.read(config.MB):
        yield block

@router.put("/{uid}/chunk/{idx}")
async def upload_chunk(uid: str, idx: int, request: Request):
    with db.tx() as c:
        f = c.execute("SELECT mode, status FROM files WHERE id=?", (uid,)).fetchone()
    if not f or f["status"] != "uploading":
        raise HTTPException(404, "unknown or finished upload")
    tmp, size = await _spool(request)
    try:
        order = sorted(range(len(config.NODES)), key=lambda i: (not pool.up[config.NODES[i]], pool.held[i]))
        placed = []
        for i in order:                              # least-loaded online nodes first; skip failed ones
            if len(placed) == config.REPLICAS:
                break
            url, t0 = config.NODES[i], time.perf_counter()
            try:
                r = await pool.client.put(f"{url}/chunks/{uid}/{idx}", content=_send(tmp), headers={"Content-Length": str(size)})
                r.raise_for_status()
            except Exception:
                pool.up[url] = False
                continue
            pool.tp[url] = 0.7 * pool.tp[url] + 0.3 * (size / config.MB / max(time.perf_counter() - t0, 1e-3))
            pool.held[i] += 1
            placed.append(i)
        if not placed:
            raise HTTPException(503, "no node accepted the chunk")
        try:
            with db.tx() as c:
                c.execute("DELETE FROM chunk_replicas WHERE file_id=? AND idx=?", (uid, idx))
                c.execute("INSERT OR REPLACE INTO chunks(file_id,idx,size) VALUES(?,?,?)", (uid, idx, size))
                c.executemany("INSERT INTO chunk_replicas(file_id,idx,node_id) VALUES(?,?,?)", [(uid, idx, i) for i in placed])
        except sqlite3.IntegrityError:               # the upload was cancelled while this chunk was in flight
            await asyncio.gather(*(pool.client.delete(f"{config.NODES[i]}/chunks/{uid}") for i in placed), return_exceptions=True)
            for i in placed:
                pool.held[i] -= 1
            raise HTTPException(410, "upload was cancelled")
    finally:
        tmp.close()
    rate = pool.tp[config.NODES[placed[0]]]
    return {"index": idx, "node_index": placed[0], "nodes": placed, "replicas": len(placed), "size": size,
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

@router.delete("/{uid}")
async def cancel_upload(uid: str, x_host_token: str | None = Header(None)):
    """Cancel (or delete) a file: remove its metadata and, best effort, its chunk bytes from the nodes."""
    with db.tx() as c:
        f = c.execute("SELECT session_id FROM files WHERE id=?", (uid,)).fetchone()
        if not f:
            return {"ok": True, "removed": False}          # already gone: cancelling twice is harmless
        s = c.execute("SELECT * FROM sessions WHERE id=?", (f["session_id"],)).fetchone()
        if not s:
            raise HTTPException(403, "file has no session")
        check_host(s, x_host_token)
        holders = [r["node_id"] for r in c.execute("SELECT DISTINCT node_id FROM chunk_replicas WHERE file_id=?", (uid,))]
        c.execute("DELETE FROM files WHERE id=?", (uid,))   # cascades to chunks + chunk_replicas
    await asyncio.gather(*(pool.client.delete(f"{config.NODES[i]}/chunks/{uid}", timeout=config.PING_TIMEOUT)
                           for i in holders), return_exceptions=True)
    return {"ok": True, "removed": True}
