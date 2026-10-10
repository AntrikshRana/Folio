"""Coordinator entry point:  uvicorn app.coordinator:app"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from . import config, db, pool
from .routes import nodes, sessions, upload

@asynccontextmanager
async def lifespan(_):
    db.init()
    with db.tx() as c:
        for i, url in enumerate(config.NODES):
            c.execute("INSERT INTO nodes(id,url) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET url=excluded.url", (i, url))
        for r in c.execute("SELECT node_id, COUNT(*) AS n FROM chunk_replicas GROUP BY node_id"):
            pool.held[r["node_id"]] = r["n"]
    yield
    await pool.client.aclose()

app = FastAPI(title="Folio coordinator", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
for r in (nodes.router, sessions.router, upload.router):
    app.include_router(r)

def _rss_mb():
    try:
        for line in open("/proc/self/status"):
            if line.startswith("VmRSS"):
                return int(line.split()[1]) // 1024
    except OSError:
        return None

@app.get("/healthz")
def healthz():
    return {"ok": True, "version": "streaming-2", "rss_mb": _rss_mb()}
