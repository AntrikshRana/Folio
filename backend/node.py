"""Storage node. Run several, each with its own NODE_DIR / NODE_NAME."""
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

NAME = os.getenv("NODE_NAME", "node")
ROOT = Path(os.getenv("NODE_DIR", "data/node")); ROOT.mkdir(parents=True, exist_ok=True)
app = FastAPI(title=f"Folio {NAME}")

@app.get("/health")
def health():
    return {"ok": True, "name": NAME, "chunks": sum(1 for _ in ROOT.rglob("*.part"))}

@app.put("/chunks/{fid}/{idx}")
async def put_chunk(fid: str, idx: int, request: Request):
    d = ROOT / fid; d.mkdir(exist_ok=True)
    (d / f"{idx}.part").write_bytes(await request.body())
    return {"stored": idx}

@app.get("/chunks/{fid}/{idx}")
def get_chunk(fid: str, idx: int):
    p = ROOT / fid / f"{idx}.part"
    if not p.exists():
        raise HTTPException(404, "chunk not found")
    return Response(p.read_bytes(), media_type="application/octet-stream")
