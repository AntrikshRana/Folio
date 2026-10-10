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

## API (coordinator)
POST /sessions {name} → {code, host_token}        POST /sessions/{code}/join {name}
GET  /sessions/{code} → members + files           GET  /sessions/{code}/files/{id}/download
POST /upload/init (X-Host-Token) · PUT /upload/{id}/chunk/{i} · POST /upload/{id}/complete
GET  /nodes/health · POST /nodes/{i}/fail|recover (host only) · GET /healthz
