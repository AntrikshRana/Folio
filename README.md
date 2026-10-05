# Folio – distributed chunked file upload

## Run (needs Python 3.10+ and Node 18+)

Terminal 1 – backend (3 nodes on 8001-8003 + coordinator on 8000)
    cd backend
    python -m venv .venv
    source .venv/bin/activate        # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    python run_all.py

Terminal 2 – frontend
    cd frontend
    npm install
    npm run dev                      # open http://localhost:5173

Chunks land in backend/data/nodeN/<upload_id>/<index>.part, manifests in backend/meta/.
Swagger docs: http://127.0.0.1:8000/docs

## API (coordinator, :8000; the UI reaches it through the /api proxy)
GET  /nodes/health                 -> [{id,name,url,online,throughput_mbps,chunks}]
POST /upload/init                  {filename,size,mode:auto|fixed,chunk_size_mb} -> {upload_id,chunk_size_mb}
PUT  /upload/{id}/chunk/{index}    raw bytes -> {index,node_index,size,throughput_mbps,next_chunk_size_mb}
POST /upload/{id}/complete         -> {ok,chunks}   (400 if byte total mismatches)
GET  /files                        -> [{id,filename,size,chunks}]
GET  /download/{id}                streams chunks back in order

## Node (:8001+)
GET /health · PUT /chunks/{fid}/{idx} · GET /chunks/{fid}/{idx}
