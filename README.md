# Folio

Folio is a distributed, chunked file-sharing app. A host creates a session, uploads a file, and the backend splits it across multiple storage nodes for replication and fault tolerance. Guests join using a short session code and can download the reconstructed file from the coordinator.

## Overview

- Frontend: React + TypeScript + Vite
- Backend: Python + FastAPI
- Metadata store: SQLite
- Storage layer: three FastAPI node services that hold chunk replicas
- Deployment pattern: one coordinator service plus multiple storage nodes

The architecture is intentionally simple:

React UI → FastAPI coordinator → SQLite metadata + chunk placement decisions → storage nodes

## Why this project exists

The app demonstrates:

- chunked upload and download workflows
- distributed storage with replica placement
- session-based collaboration and host authorization
- node health checks and simulated failure handling
- end-to-end file sharing over a lightweight web app

## Repository layout

```text
backend/
  app/
    auth.py
    config.py
    coordinator.py
    db.py
    files.py
    node.py
    pool.py
    routes/
      nodes.py
      sessions.py
      upload.py
  requirements.txt
  run_local.py
frontend/
  src/
  package.json
  vite.config.ts
render.yaml
README.md
work.md
```

## Documentation

- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) — system design, flow, and key modules
- [docs/DEVELOPMENT.md](./docs/DEVELOPMENT.md) — local setup, environment variables, and troubleshooting
- [docs/API.md](./docs/API.md) — coordinator API reference and request examples

## Quick start

### Prerequisites

- Python 3.10+
- Node.js 18+
- npm

### Local development

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt
python run_local.py
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Then open the frontend at `http://localhost:5173`.

Other machines on the same network can reach the Vite app via the LAN IP shown by Vite, usually `http://<your-ip>:5173`.

## Core runtime configuration

Most configuration is driven by environment variables in `backend/app/config.py`:

- `NODES` — comma-separated storage node URLs
- `REPLICAS` — number of copies to keep for each chunk
- `MAX_CHUNK_MB` — upper bound for chunk size
- `SESSION_TTL_HOURS` — session lifetime
- `DATA_DIR` — directory for the SQLite database
- `CORS_ORIGINS` — allowed origins for the coordinator
- `NODE_CONNECT_TIMEOUT` / `PING_TIMEOUT` — network timeout tuning

## Deployment

The repository includes a Render blueprint in [render.yaml](./render.yaml). It provisions:

- one static frontend service
- one coordinator service
- three storage node services

See [docs/DEVELOPMENT.md](./docs/DEVELOPMENT.md) for deployment notes.

## Project links

- Folio: https://folio-fc3b.onrender.com
- Coordinator: https://folio-coordinator.onrender.com
- Node 1: https://folio-node-1.onrender.com
- Node 2: https://folio-node-2.onrender.com
- Node 3: https://folio-node-3.onrender.com
