"""Coordinator: accepts chunks from the UI, spreads them over nodes, keeps the manifest."""
import asyncio, json, os, time, uuid
from pathlib import Path
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

NODES = os.getenv("NODES", "http://127.0.0.1:8001,http://127.0.0.1:8002,http://127.0.0.1:8003").split(",")
MB, SIZES = 1 << 20, [1, 2, 4, 8, 16, 32, 64]
META = Path("meta"); META.mkdir(exist_ok=True)

app = FastAPI(title="Folio coordinator")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
client = httpx.AsyncClient(timeout=httpx.Timeout(60, connect=2))
uploads: dict = {}
up = {u: True for u in NODES}       # last known reachability
tp = {u: 20.0 for u in NODES}       # smoothed throughput per node, MB/s
held = [0] * len(NODES)             # chunks placed per node (this session)

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
    uploads[uid] = {"id": uid, "filename": b.filename, "size": b.size, "mode": b.mode, "chunks": {}}
    return {"upload_id": uid, "chunk_size_mb": 4 if b.mode == "auto" else b.chunk_size_mb}

@app.put("/upload/{uid}/chunk/{idx}")
async def upload_chunk(uid: str, idx: int, request: Request):
    u = uploads.get(uid)
    if not u:
        raise HTTPException(404, "unknown upload")
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
        u["chunks"][idx] = {"node": i, "size": len(data)}
        return {"index": idx, "node_index": i, "size": len(data),
                "throughput_mbps": round(tp[url], 1),
                "next_chunk_size_mb": recommend(tp[url]) if u["mode"] == "auto" else None}
    raise HTTPException(503, "no node accepted the chunk")

@app.post("/upload/{uid}/complete")
def upload_complete(uid: str):
    u = uploads.get(uid)
    if not u:
        raise HTTPException(404, "unknown upload")
    got = sum(c["size"] for c in u["chunks"].values())
    if got != u["size"]:
        raise HTTPException(400, f"expected {u['size']} bytes, got {got}")
    (META / f"{uid}.json").write_text(json.dumps(u))
    return {"ok": True, "chunks": len(u["chunks"])}

@app.get("/files")
def list_files():
    ms = [json.loads(p.read_text()) for p in META.glob("*.json")]
    return [{"id": m["id"], "filename": m["filename"], "size": m["size"], "chunks": len(m["chunks"])} for m in ms]

@app.get("/download/{uid}")
async def download(uid: str):
    p = META / f"{uid}.json"
    if not p.exists():
        raise HTTPException(404, "unknown file")
    m = json.loads(p.read_text())
    async def gen():
        for idx in sorted(m["chunks"], key=int):
            r = await client.get(f"{NODES[m['chunks'][idx]['node']]}/chunks/{uid}/{idx}")
            r.raise_for_status()
            yield r.content
    return StreamingResponse(gen(), media_type="application/octet-stream",
                             headers={"Content-Disposition": f'attachment; filename="{m["filename"]}"'})
