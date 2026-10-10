# Folio – distributed chunked file sharing

React UI  →  FastAPI coordinator (+ SQLite metadata)  →  FastAPI storage nodes.
Hosts upload big files in adaptive chunks (replicated on 2 nodes); guests join with a code and download.

## Structure
    render.yaml                  Render Blueprint (static site + coordinator + 3 nodes)
    backend/
      requirements.txt
      run_local.py               starts 3 nodes + coordinator for local dev
      app/
        config.py                every setting is an environment variable
        db.py                    SQLite schema + migrations
        pool.py                  node state: health, throughput, load, simulated failures
        auth.py                  session / host-token checks
        files.py                 file listing, chunk plan, streaming download
        coordinator.py           FastAPI app (uvicorn app.coordinator:app)
        node.py                  storage node (uvicorn app.node:app)
        routes/ upload.py  sessions.py  nodes.py
    frontend/
      src/ App.tsx  api.ts  types.ts  demo.ts  components/{SessionGate,Room}.tsx

## Run locally (Python 3.10+, Node 18+)
    cd backend && python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
    pip install -r requirements.txt && python run_local.py
    # new terminal
    cd frontend && npm install && npm run dev        # http://localhost:5173
Other devices on your Wi-Fi can join at http://<your-LAN-IP>:5173 (dev server runs with --host).

## Deploy on Render
1. Push this folder to a GitHub repo (render.yaml must be in the repo root).
2. Render dashboard → New → Blueprint → select the repo → Apply.
3. Check the real service URLs. If Render added suffixes, update NODES, CORS_ORIGINS and VITE_API_URL
   in render.yaml (or the dashboard) and redeploy.
4. Open the static site URL, start a session, share the code.
Free-plan caveats: services sleep when idle (first request is slow), and the filesystem is ephemeral – uploaded
chunks and the SQLite file are lost on restart/redeploy. For durable data use paid instances with a disk
(set DATA_DIR / NODE_DIR to the disk's mount path).

## Settings (env vars)
NODES, CORS_ORIGINS, REPLICAS (2), MAX_CHUNK_MB (64), SESSION_TTL_HOURS (24), DATA_DIR, NODE_NAME, NODE_DIR, VITE_API_URL (frontend build)

## API (coordinator)
POST /sessions {name} → {code, host_token}        POST /sessions/{code}/join {name}
GET  /sessions/{code} → members + files           GET  /sessions/{code}/files/{id}/download
POST /upload/init (X-Host-Token) · PUT /upload/{id}/chunk/{i} · POST /upload/{id}/complete
GET  /nodes/health · POST /nodes/{i}/fail|recover (host only) · GET /healthz

## Known limits
No automatic re-replication after a failure; deleted/expired sessions leave orphaned chunk bytes on nodes;
no per-chunk checksums; the coordinator relays chunk bytes (a bottleneck at scale).

Cold-start settings (Render free plan): NODE_CONNECT_TIMEOUT, PING_TIMEOUT (seconds, defaults 2 / 5; render.yaml sets 30).
"Failed to fetch" checklist: open <coordinator>/healthz; check VITE_API_URL (needs a rebuild); CORS_ORIGINS="*" is the simplest.

DELETE /upload/{id} (X-Host-Token) cancels/deletes a file: removes its rows and best-effort deletes chunk bytes from the nodes.

## Memory (Render free = 512 MB per service)
Chunks are streamed through disk/small blocks, never held whole in RAM: a node writes uploads to disk as they arrive and
serves downloads with FileResponse; the coordinator spools each incoming chunk to a temp file, forwards it from disk, and
relays downloads in 1 MB blocks. Measured (MAX_CHUNK_MB=64): coordinator ~58 MB, node ~50 MB, flat over repeated uploads.
