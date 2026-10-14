# Folio API reference

This document describes the coordinator endpoints used by the frontend and any external clients.

## Base URLs

- Local coordinator: `http://localhost:8000`
- Local node services: `http://localhost:8001`, `http://localhost:8002`, `http://localhost:8003`

## Session endpoints

### Create a session

`POST /sessions`

Request body:

```json
{
  "name": "Alice"
}
```

Response:

```json
{
  "code": "K7Q2-9XMA",
  "host_token": "<secret-token>"
}
```

The session code is the shareable code used by guests. The host token is used in `X-Host-Token` headers for privileged actions.

### Join a session

`POST /sessions/{code}/join`

Request body:

```json
{
  "name": "Bob"
}
```

Response:

```json
{
  "code": "K7Q2-9XMA"
}
```

### Get session details

`GET /sessions/{code}`

Response:

```json
{
  "code": "K7Q2-9XMA",
  "title": "Alice's session",
  "expires_at": "2026-10-15T15:00:00",
  "members": [
    { "name": "Alice", "role": "host" },
    { "name": "Bob", "role": "guest" }
  ],
  "files": [
    {
      "id": "abc123",
      "filename": "report.pdf",
      "size": 1024000,
      "status": "complete"
    }
  ]
}
```

### Download a file from a session

`GET /sessions/{code}/files/{fid}/download`

This returns a binary stream with the file content and `Content-Disposition` headers for download behavior.

## Upload endpoints

### Initialize an upload

`POST /upload/init`

Headers:

```http
X-Host-Token: <host-token>
```

Request body:

```json
{
  "session": "K7Q2-9XMA",
  "filename": "large-video.mp4",
  "size": 54200000,
  "mode": "auto",
  "chunk_size_mb": 8
}
```

Response:

```json
{
  "upload_id": "abc123",
  "replication": 2,
  "chunk_size_mb": 8
}
```

### Upload a chunk

`PUT /upload/{uid}/chunk/{idx}`

This endpoint receives the raw binary chunk in the request body. The file index is the zero-based chunk position.

Response:

```json
{
  "index": 0,
  "node_index": 1,
  "nodes": [1, 2],
  "replicas": 2,
  "size": 8388608,
  "throughput_mbps": 12.3,
  "next_chunk_size_mb": 8
}
```

### Complete the upload

`POST /upload/{uid}/complete`

Response:

```json
{
  "ok": true,
  "chunks": 7
}
```

### Cancel an upload

`DELETE /upload/{uid}`

Headers:

```http
X-Host-Token: <host-token>
```

Response:

```json
{
  "ok": true,
  "removed": true
}
```

## Node management endpoints

### Node health

`GET /nodes/health`

Returns the node status for the configured storage layer.

### Fail a node

`POST /nodes/{i}/fail`

Requires host access through the session host token flow used by the app's admin controls.

### Recover a node

`POST /nodes/{i}/recover`

Requires the same host-level authorization.

## Health endpoints

### Coordinator health

`GET /healthz`

### Node health

`GET /health`

`health` is exposed by each storage service and is useful during deployment verification or manual failure testing.

## Notes

- The host token is not a cookie; it is passed as the `X-Host-Token` header.
- Session codes are human-readable and safe to share with guests.
- File data is reconstructed from chunk replicas and streamed back as a download response, not as a prebuilt file on disk.
