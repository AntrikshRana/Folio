# Folio architecture

Folio is a small distributed file-sharing system built around a coordinator and a set of storage nodes. The coordinator owns session logic and metadata, while each storage node stores file chunks and reports back its health and throughput.

## High-level flow

1. A host creates a session.
2. The frontend opens the session and keeps the host token.
3. The host uploads a file through the coordinator.
4. The coordinator records file metadata in SQLite and distributes chunks across nodes.
5. Guests join with the session code and can request a file download.
6. The coordinator checks replica availability and streams the reconstructed file.

## Components

### Frontend

The React app in `frontend/src` provides the session UI, file upload workflow, download actions, and node health presentation.

Responsibilities:

- create a session and get code + host token
- join an existing session
- submit uploaded chunks and monitor progress
- list files in the session
- request downloads and surface errors

### Coordinator

The coordinator is the main FastAPI service in `backend/app/coordinator.py` and the route modules under `backend/app/routes/`.

Responsibilities:

- manage sessions and host authorization
- validate file metadata and session membership
- decide which storage nodes hold each chunk
- reconstruct a file by fetching chunk replicas from healthy nodes
- expose health endpoints for the deployment and admin actions

### Storage nodes

Each storage node runs a FastAPI app defined in `backend/app/node.py`.

Responsibilities:

- accept chunk uploads for a file id and index
- persist chunk bytes to disk under a node-local data directory
- report health and throughput information
- serve chunks for file recovery
- allow simulated failure or recovery actions

### Metadata store

`backend/app/db.py` defines the SQLite schema used by the system.

Key tables:

- `sessions` — session code, host token, title, expiration
- `session_members` — host/guest membership per session
- `files` — file id, file name, size, upload status, session
- `chunks` — chunk index and size for each file
- `chunk_replicas` — which nodes store a given chunk replica
- `nodes` — known storage node URLs

## Upload lifecycle

A typical upload goes through the following steps:

1. `POST /sessions` creates a session and returns a session code and host token.
2. `POST /upload/init` creates a file record and sets the upload mode.
3. The frontend sends file chunks using `PUT /upload/{uid}/chunk/{idx}`.
4. The coordinator chooses healthy nodes with the lowest load and each node stores the chunk.
5. `POST /upload/{uid}/complete` marks the file as complete after the expected total byte count is reached.

The system supports an `auto` mode, where chunk size adapts to measured throughput, and a `fixed` mode that uses a user-specified chunk size.

## Download lifecycle

When a guest downloads a file:

1. `GET /sessions/{code}` returns the list of files for the session.
2. `GET /sessions/{code}/files/{fid}/download` resolves the file and builds a chunk plan.
3. The coordinator checks whether any chunks are missing from healthy nodes.
4. It streams the file back from the highest-availability replica set.

## Fault tolerance

The app includes basic failure handling:

- node health is tracked in `backend/app/pool.py`
- failed nodes are skipped for uploads and retrieval
- `REPLICAS` controls how many copies of a chunk are kept
- the coordinator refuses downloads if too many chunks are unavailable

This keeps the system resilient to temporary node outages while staying lightweight enough for a demo or learning project.

## Key implementation files

- `backend/app/config.py` — environment-based runtime configuration
- `backend/app/auth.py` — session and host-token validation
- `backend/app/files.py` — chunk planning and file streaming logic
- `backend/app/pool.py` — node state, load, and simulated health behavior
- `backend/app/coordinator.py` — app assembly and route registration
- `backend/app/node.py` — storage-node service implementation

## Design notes

This project favors clarity over production complexity. The implementation keeps SQLite as the metadata service, moves chunk data to separate node services, and makes deployment easy through the Render blueprint. That makes it a good example of a compact distributed storage workflow without needing a full distributed database or container orchestration system.
