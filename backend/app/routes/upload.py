import asyncio, sqlite3, tempfile, time, uuid
from typing import Literal
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field
from .. import config, db, files, pool, stats
from ..auth import file_access, get_session, identify, require_uploader

router = APIRouter(prefix="/upload", tags=["upload"])

class Init(BaseModel):
    session: str
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0)
    # Restrict modes here so invalid client input cannot silently select fixed sizing.
    mode: Literal["auto", "fixed"] = "auto"
    # Fixed uploads need a positive size; the server also caps it to MAX_CHUNK_MB below.
    chunk_size_mb: int = Field(default=8, ge=1)

def _check_limits(c, s, me, size: int) -> None:
    mb = config.MB
    if size > s["max_file_mb"] * mb:
        raise HTTPException(413, f"this file is {size / mb:.1f} MB but the limit here is {s['max_file_mb']} MB per file")
    # Count only live uploads so cancelled/removed files stop consuming the guest's file allowance.
    n = c.execute(f"SELECT COUNT(*) FROM files WHERE session_id=? AND member_id=? AND {files.LIVE}", (s["id"], me["member_id"])).fetchone()[0]
    if n >= s["max_files_per_guest"]:
        raise HTTPException(403, f"you have reached the limit of {s['max_files_per_guest']} files per person")
    used = c.execute(f"SELECT COALESCE(SUM(size),0) FROM files WHERE session_id=? AND {files.LIVE}", (s["id"],)).fetchone()[0]
    if used + size > s["room_quota_mb"] * mb:
        raise HTTPException(413, f"the room's storage ({s['room_quota_mb']} MB) would be exceeded")

@router.post("/init")
def upload_init(b: Init, x_host_token: str | None = Header(None), x_member_token: str | None = Header(None)):
    uid = uuid.uuid4().hex
    with db.tx() as c:
        # Reserve the write lock before checking quotas to prevent two parallel inits exceeding them.
        c.execute("BEGIN IMMEDIATE")
        s = get_session(c, b.session)
        me = identify(c, s, x_member_token, x_host_token)     # who is asking?
        require_uploader(s, me)                               # guests only if the teacher allowed them
        if me["role"] != "host":                              # the teacher is exempt from the guest limits
            _check_limits(c, s, me, b.size)
        c.execute("INSERT INTO files(id,session_id,filename,size,mode,member_id) VALUES(?,?,?,?,?,?)",
                  (uid, s["id"], b.filename, b.size, b.mode, me["member_id"]))
    stats.record("upload_started", uid, size=b.size)
    first = min(4, config.MAX_CHUNK_MB) if b.mode == "auto" else max(1, min(b.chunk_size_mb, config.MAX_CHUNK_MB))
    return {"upload_id": uid, "replication": config.REPLICAS, "chunk_size_mb": first}

async def _spool(request: Request, limit: int):
    """Spool each request to disk after 1 MB to keep large chunk uploads from filling RAM."""
    tmp, size = tempfile.SpooledTemporaryFile(max_size=config.MB), 0
    try:
        async for part in request.stream():
            size += len(part)
            if size > config.MAX_CHUNK_MB * config.MB:
                raise HTTPException(413, f"chunk larger than MAX_CHUNK_MB={config.MAX_CHUNK_MB}")
            if size > limit:
                raise HTTPException(413, "more data than the file size announced at the start")
            tmp.write(part)
    except BaseException:
        tmp.close()
        raise
    return tmp, size

async def _send(tmp):
    # Rewind before every node request so replicas receive the same complete chunk bytes.
    tmp.seek(0)
    while block := tmp.read(config.RELAY_BLOCK):
        yield block

# Bound simultaneous chunk relays; each relay uses a temp file and node connections.
_slots = asyncio.Semaphore(config.MAX_PARALLEL_UPLOADS)

@router.put("/{uid}/chunk/{idx}")
async def upload_chunk(uid: str, idx: int, request: Request,
                       x_host_token: str | None = Header(None), x_member_token: str | None = Header(None)):
    with db.tx() as c:                                # check identity before taking a slot or reading the body
        f, s, me = file_access(c, uid, x_member_token, x_host_token)
        require_uploader(s, me)
        others = c.execute("SELECT COALESCE(SUM(size),0) FROM chunks WHERE file_id=? AND idx!=?", (uid, idx)).fetchone()[0]
    if f["status"] != "uploading":
        raise HTTPException(404, "unknown or finished upload")
    async with _slots:                                # a 0.1-CPU instance is better off finishing chunks one by one
        return await _handle_chunk(uid, idx, request, f, f["size"] - others)

async def _handle_chunk(uid: str, idx: int, request: Request, f, room: int):
    tmp, size = await _spool(request, room)
    try:
        # Prefer healthy nodes with fewer stored chunks to spread disk and request load.
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
                # Publish metadata only after storage accepted the bytes, so downloads never see a partial write.
                c.execute("DELETE FROM chunk_replicas WHERE file_id=? AND idx=?", (uid, idx))
                c.execute("INSERT OR REPLACE INTO chunks(file_id,idx,size) VALUES(?,?,?)", (uid, idx, size))
                c.executemany("INSERT INTO chunk_replicas(file_id,idx,node_id) VALUES(?,?,?)", [(uid, idx, i) for i in placed])
            stats.record("chunk_stored", uid, idx, placed, size)
        except sqlite3.IntegrityError:               # the upload was cancelled while this chunk was in flight
            # The file row may have disappeared during node I/O; remove any orphaned bytes we just wrote.
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
def upload_complete(uid: str, x_host_token: str | None = Header(None), x_member_token: str | None = Header(None)):
    with db.tx() as c:
        f, s, me = file_access(c, uid, x_member_token, x_host_token)
        require_uploader(s, me)
        got, n, first_idx, last_idx = c.execute(
            "SELECT COALESCE(SUM(size),0), COUNT(*), MIN(idx), MAX(idx) FROM chunks WHERE file_id=?", (uid,)
        ).fetchone()
        if got != f["size"]:
            raise HTTPException(400, f"expected {f['size']} bytes, got {got}")
        # Matching byte totals alone can hide a missing middle chunk; downloads need indexes 0 through n-1.
        if n and (first_idx != 0 or last_idx != n - 1):
            raise HTTPException(400, "upload is missing one or more chunks")
        c.execute("UPDATE files SET status='complete' WHERE id=?", (uid,))
    stats.record("upload_completed", uid, size=got, detail=f"{n} chunks")
    return {"ok": True, "chunks": n}

@router.delete("/{uid}")
async def cancel_upload(uid: str, x_host_token: str | None = Header(None), x_member_token: str | None = Header(None)):
    """Cancel (or delete) a file: remove its metadata and, best effort, its chunk bytes from the nodes."""
    with db.tx() as c:
        f = c.execute("SELECT session_id, member_id FROM files WHERE id=?", (uid,)).fetchone()
        if not f:
            return {"ok": True, "removed": False}          # already gone: cancelling twice is harmless
        s = c.execute("SELECT * FROM sessions WHERE id=?", (f["session_id"],)).fetchone()
        if not s:
            raise HTTPException(403, "file has no session")
        me = identify(c, s, x_member_token, x_host_token)
        if me["role"] != "host" and me["member_id"] != f["member_id"]:      # you may cancel your own files; the host may cancel any
            raise HTTPException(403, "this upload belongs to someone else")
        # Read the replica list before cascading metadata deletion so the corresponding node bytes can be removed.
        holders = [r["node_id"] for r in c.execute("SELECT DISTINCT node_id FROM chunk_replicas WHERE file_id=?", (uid,))]
        c.execute("DELETE FROM files WHERE id=?", (uid,))   # cascades to chunks + chunk_replicas
    stats.record("upload_cancelled", uid)
    await asyncio.gather(*(pool.client.delete(f"{config.NODES[i]}/chunks/{uid}", timeout=config.PING_TIMEOUT)
                           for i in holders), return_exceptions=True)
    return {"ok": True, "removed": True}
