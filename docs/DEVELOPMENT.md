# Folio development guide

This guide explains how to run, configure, and troubleshoot Folio locally and in deployment.

## Prerequisites

- Python 3.10 or newer
- Node.js 18 or newer
- npm
- A terminal with access to the repository

## Local setup

### 1. Start the backend services

From the repository root:

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

`run_local.py` starts:

- the coordinator on port `8000`
- three node services on ports `8001`, `8002`, and `8003`
- a shared SQLite database under `backend/data`

### 2. Start the frontend

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The UI runs on `http://localhost:5173` by default.

## Configuration

The backend reads configuration from environment variables in `backend/app/config.py`.

Common keys:

```bash
export NODES="http://127.0.0.1:8001,http://127.0.0.1:8002,http://127.0.0.1:8003"
export REPLICAS=2
export MAX_CHUNK_MB=64
export SESSION_TTL_HOURS=24
export DATA_DIR="data"
export CORS_ORIGINS="*"
export NODE_CONNECT_TIMEOUT=2
export PING_TIMEOUT=5
```

If you are using Render or another hosting provider, set these environment variables in the service configuration instead of exporting them in a local shell.

## Useful commands

### Backend checks

```bash
cd backend
python -m uvicorn app.coordinator:app --reload --port 8000
```

```bash
python -m uvicorn app.node:app --reload --port 8001
```

### Frontend build

```bash
cd frontend
npm run build
```

The production build is generated in `frontend/dist`.

## Deployment notes

The repo includes a Render blueprint in [`render.yaml`](../render.yaml). It creates:

- a static frontend deployment
- a coordinator service
- three node services

If the default public URLs are changed by Render, update the `NODES` value for the coordinator and redeploy the services.

## Troubleshooting

### The app cannot reach the storage nodes

Check that:

- the backend is running
- the node URLs in `NODES` match the actual services
- the node services are healthy at `/health` and `/healthz`

### Uploads fail

Common causes:

- a missing or expired session host token
- no healthy node accepting the chunk
- `MAX_CHUNK_MB` being too low for the file size or chosen chunk size

### Sessions do not appear to persist

Verify that:

- `DATA_DIR` points to a writable directory
- the database file is not being replaced during each deploy
- you are not running the app with a different data path than expected

## Contributing

When you change the API contract, update:

- [docs/API.md](./API.md)
- the frontend request code in `frontend/src`
- the backend routes and validation logic in `backend/app/routes`

If you add new configuration, document it in this file and in the root README.
