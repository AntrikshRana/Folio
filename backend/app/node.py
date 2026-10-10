"""Storage node:  uvicorn app.node:app   (run several, each with its own NODE_NAME / NODE_DIR)."""
import os, re, shutil
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

NAME = os.getenv("NODE_NAME", "node")
ROOT = Path(os.getenv("NODE_DIR", "data/node")); ROOT.mkdir(parents=True, exist_ok=True)
app = FastAPI(title=f"Folio {NAME}")

def _dir(fid: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", fid):
        raise HTTPException(400, "bad file id")
    return ROOT / fid

failed = False   # simulated failure: every route except /admin answers 503

@app.middleware("http")
async def simulate_failure(request: Request, call_next):
    if failed and not request.url.path.startswith("/admin"):
        return JSONResponse({"detail": "simulated node failure"}, status_code=503)
    return await call_next(request)

@app.post("/admin/fail")
def admin_fail():
    global failed; failed = True; return {"failed": True}

@app.post("/admin/recover")
def admin_recover():
    global failed; failed = False; return {"failed": False}

@app.get("/health")
def health():
    return {"ok": True, "name": NAME, "chunks": sum(1 for _ in ROOT.rglob("*.part"))}

@app.put("/chunks/{fid}/{idx}")
async def put_chunk(fid: str, idx: int, request: Request):
    d = _dir(fid); d.mkdir(exist_ok=True)
    tmp, size = d / f"{idx}.tmp", 0
    with open(tmp, "wb") as f:                       # write as bytes arrive: memory stays flat for any chunk size
        async for part in request.stream():
            f.write(part); size += len(part)
    os.replace(tmp, d / f"{idx}.part")               # atomic: readers never see a half-written chunk
    return {"stored": idx, "size": size}

@app.get("/chunks/{fid}/{idx}")
def get_chunk(fid: str, idx: int):
    p = _dir(fid) / f"{idx}.part"
    if not p.exists():
        raise HTTPException(404, "chunk not found")
    return FileResponse(p, media_type="application/octet-stream")   # streamed from disk in small blocks

@app.delete("/chunks/{fid}")
def delete_chunks(fid: str):
    shutil.rmtree(_dir(fid), ignore_errors=True)
    return {"deleted": fid}
