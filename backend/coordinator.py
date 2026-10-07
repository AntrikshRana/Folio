"""Coordinator: accepts chunks from the UI, spreads them over nodes, keeps metadata in SQLite."""
import asyncio, os, time, uuid
from contextlib import asynccontextmanager
from urllib.parse import quote
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import db

NODES = os.getenv("NODES", "http://127.0.0.1:8001,http://127.0.0.1:8002,http://127.0.0.1:8003").split(",")
MB, SIZES = 1 << 20, [1, 2, 4, 8, 16, 32, 64]
client = httpx.AsyncClient(timeout=httpx.Timeout(60, connect=2))
up = {u: True for u in NODES}       # last known reachability
tp = {u: 20.0 for u in NODES}       # smoothed throughput per node, MB/s
held = [0] * len(NODES)             # chunks placed per node (restored from the DB at startup)

@asynccontextmanager
async def lifespan(_):
    db.init()
    with db.tx() as c:
        for i, url in enumerate(NODES):
            c.execute("INSERT INTO nodes(id,url) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET url=excluded.url", (i, url))
        for r in c.execute("SELECT node_id, COUNT(*) AS n FROM chunks GROUP BY node_id"):
            held[r["node_id"]] = r["n"]
    yield
    await client.aclose()

app = FastAPI(title="Folio coordinator", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def recommend(mbps: float) -> int:
    """Chunk size (MB) ~ what a node can take in 0.4 s, snapped to 1..64."""
    return min(SIZES, key=lambda s: abs(s - mbps * 0.4))

@app.get("/nodes/health")
async def nodes_health():
    async def ping(i, url):
        try:
            d = (await client.get(f"{url}/health", timeout=1.5)).json()
            up[url] = True
            return {"id": i, "name": d["name"], "url": url, "online": True,
                    "throughput_mbps": round(tp[url], 1), "chunks": d["chunks"]}
        except Exception:
            up[url] = False
            return {"id": i, "name": f"node-{i+1}", "url": url, "online": False,
                    "throughput_mbps": 0, "chunks": 0}
    return await asyncio.gather(*(ping(i, u) for i, u in enumerate(NODES)))

class Init(BaseModel):
    filename: str
    size: int
    mode: str = "auto"          # "auto" | "fixed"
    chunk_size_mb: int = 8

@app.post("/upload/init")
def upload_init(b: Init):
    uid = uuid.uuid4().hex
    with db.tx() as c:
        c.execute("INSERT INTO files(id,filename,size,mode) VALUES(?,?,?,?)", (uid, b.filename, b.size, b.mode))
    return {"upload_id": uid, "chunk_size_mb": 4 if b.mode == "auto" else b.chunk_size_mb}

@app.put("/upload/{uid}/chunk/{idx}")
async def upload_chunk(uid: str, idx: int, request: Request):
    with db.tx() as c:
        f = c.execute("SELECT mode, status FROM files WHERE id=?", (uid,)).fetchone()
    if not f or f["status"] != "uploading":
        raise HTTPException(404, "unknown or finished upload")
    data = await request.body()
    order = sorted(range(len(NODES)), key=lambda i: (not up[NODES[i]], held[i]))
    for i in order:                                  # least-loaded online node first, then fail over
        url, t0 = NODES[i], time.perf_counter()
        try:
            (await client.put(f"{url}/chunks/{uid}/{idx}", content=data)).raise_for_status()
        except Exception:
            up[url] = False
            continue
        mbps = len(data) / MB / max(time.perf_counter() - t0, 1e-3)
        tp[url] = 0.7 * tp[url] + 0.3 * mbps
        held[i] += 1
        with db.tx() as c:
            c.execute("INSERT OR REPLACE INTO chunks(file_id,idx,node_id,size) VALUES(?,?,?,?)", (uid, idx, i, len(data)))
        return {"index": idx, "node_index": i, "size": len(data),
                "throughput_mbps": round(tp[url], 1),
                "next_chunk_size_mb": recommend(tp[url]) if f["mode"] == "auto" else None}
    raise HTTPException(503, "no node accepted the chunk")

@app.post("/upload/{uid}/complete")
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

@app.get("/files")
def list_files():
    with db.tx() as c:
        rows = c.execute("""
            SELECT f.id, f.filename, f.size, f.created_at, COUNT(k.idx) AS chunks,
                   GROUP_CONCAT(DISTINCT k.node_id) AS nodes
            FROM files f LEFT JOIN chunks k ON k.file_id = f.id
            WHERE f.status = 'complete'
            GROUP BY f.id ORDER BY f.created_at DESC, f.rowid DESC""").fetchall()
    out = []
    for r in rows:
        ns = sorted(int(x) for x in (r["nodes"] or "").split(",") if x)
        out.append({"id": r["id"], "filename": r["filename"], "size": r["size"], "chunks": r["chunks"],
                    "created_at": r["created_at"], "nodes": ns,
                    "available": all(up[NODES[n]] for n in ns)})   # false if a holding node is down
    return out

@app.get("/download/{uid}")
async def download(uid: str):
    with db.tx() as c:
        f = c.execute("SELECT filename, size FROM files WHERE id=? AND status='complete'", (uid,)).fetchone()
        chunks = c.execute("SELECT idx, node_id FROM chunks WHERE file_id=? ORDER BY idx", (uid,)).fetchall()
    if not f:
        raise HTTPException(404, "unknown file")
    needed = sorted({r["node_id"] for r in chunks})
    async def alive(i):
        try:
            await client.get(f"{NODES[i]}/health", timeout=1.5); up[NODES[i]] = True; return True
        except Exception:
            up[NODES[i]] = False; return False
    ok = await asyncio.gather(*(alive(i) for i in needed))
    down = [NODES[i] for i, a in zip(needed, ok) if not a]
    if down:                                         # fail before streaming so the browser gets a clean error
        raise HTTPException(503, f"node(s) holding this file are offline: {', '.join(down)}")
    async def gen():
        for r in chunks:
            resp = await client.get(f"{NODES[r['node_id']]}/chunks/{uid}/{r['idx']}")
            resp.raise_for_status()
            yield resp.content
    return StreamingResponse(gen(), media_type="application/octet-stream", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(f['filename'])}",
        "Content-Length": str(f["size"])})
