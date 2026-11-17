"""Coordinator entry point:  uvicorn app.coordinator:app"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from . import config, db, pool
from .routes import live, nodes, sessions, texts, upload

@asynccontextmanager
async def lifespan(_):
    db.init()
    with db.tx() as c:
        for i, url in enumerate(config.NODES):
            c.execute("INSERT INTO nodes(id,url) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET url=excluded.url", (i, url))
        # Restore the scheduler's load counts so uploads keep balancing against chunks already on disk after a restart.
        for r in c.execute("SELECT node_id, COUNT(*) AS n FROM chunk_replicas GROUP BY node_id"):
            pool.held[r["node_id"]] = r["n"]
    yield
    await pool.client.aclose()

app = FastAPI(
    title="Folio coordinator",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "upload", "description": "Initialize uploads, store chunks across nodes, complete, or cancel files."},
    ],
)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
# The coordinator publishes the upload router's endpoints as part of its public API.
for r in (nodes.router, sessions.router, upload.router, live.router, texts.router):
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
    return {"ok": True, "version": "streaming-4", "rss_mb": _rss_mb()}

@app.get("/config")
def public_config():
    return {"simulation": config.ALLOW_SIMULATION}      # lets the UI hide buttons the server would reject

# Optional: serve the built frontend from this same server (start.py does this), so one address and one port is the whole app.
# Mounted last so every API route above wins; anything else falls through to the UI.
_ui = os.environ.get("FOLIO_STATIC", "")
if _ui and os.path.isdir(_ui):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_ui, html=True), name="ui")
