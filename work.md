# Folio Project — Work Distribution for 4 Members

Folio is a distributed, chunk-based file-sharing system. It splits large files into smaller chunks, distributes copies across storage nodes, and lets users share and download files through sessions.

**Technology stack**
- **Frontend:** React, TypeScript, Vite
- **Backend:** Python, FastAPI
- **Database:** SQLite
- **OS concepts:** File handling, disk I/O, chunking, concurrency, resource management, fault tolerance, and distributed storage
- **Deployment:** One coordinator and three storage nodes

Since the UI was designed with an AI tool, UI design should be treated as a shared, supporting contribution rather than giving one member most of the frontend work. Each member should own a meaningful system component, its database work, OS concepts, and frontend integration.

## 1. Member-wise Work Distribution

### Member 1 — File Chunking and Upload Management

**Primary files:** `backend/app/routes/upload.py`, `backend/app/db.py` (chunk-related schema)

#### Operating Systems (OS)
- Implement file splitting into smaller chunks.
- Handle file reads, temporary files, and disk I/O.
- Implement adaptive chunk sizing based on measured throughput.
- Handle interrupted uploads and cleanup of incomplete data.

#### Database Management Systems (DBMS)
- Store file metadata in the `files` table.
- Record chunk indexes and sizes in `chunks`.
- Use transactions to keep upload metadata consistent.
- Handle upload completion and cancellation without leaving inconsistent records.

#### Frontend contribution
- Connect the upload interface to the backend.
- Display upload progress, chunk sizes, and error messages.

**Deliverable:** A working upload pipeline with chunking, adaptive sizing, and database tracking.

---

### Member 2 — Distributed Storage and Fault Tolerance

**Primary files:** `backend/app/node.py`, `backend/app/pool.py`

#### Operating Systems (OS)
- Implement storage nodes that save chunks to disk.
- Use temporary files and atomic file replacement to prevent partially written chunks from being served.
- Implement node failure and recovery simulation.
- Handle disk storage, I/O errors, and node availability.

#### Database Management Systems (DBMS)
- Maintain node records in the `nodes` table.
- Track chunk replicas in `chunk_replicas`.
- Understand foreign keys and referential integrity between nodes, chunks, and replicas.
- Maintain consistent replica metadata when placement or cleanup operations occur.

#### Frontend contribution
- Integrate node-health information into the dashboard.
- Display online/offline nodes and their stored-chunk counts.

**Deliverable:** A distributed storage layer with replication tracking and simulated node failures.

---

### Member 3 — Sessions, Access Control, and Metadata Management

**Primary files:** `backend/app/routes/sessions.py`, `backend/app/auth.py`, `backend/app/db.py` (session-related schema)

#### Operating Systems (OS)
- Manage file and directory permissions at the application level.
- Handle concurrent session requests and database access safely.
- Manage temporary resources and cleanup associated with expired sessions.
- Understand the difference between application-level authorization and operating-system file permissions.

#### Database Management Systems (DBMS)
- Design and manage `sessions` and `session_members`.
- Implement session creation, joining, expiration, and membership queries.
- Use primary keys, unique constraints, foreign keys, and transactions.
- Validate database consistency when a session expires or is removed.

#### Frontend contribution
- Integrate the create-session and join-session screens.
- Handle session codes, host status, validation, and error messages.

**Deliverable:** A session-management system with persistent metadata and host authorization.

---

### Member 4 — File Retrieval, Reconstruction, and System Integration

**Primary files:** `backend/app/files.py`, download endpoint in `backend/app/routes/sessions.py`, `backend/app/coordinator.py`

#### Operating Systems (OS)
- Stream chunks from storage nodes in the correct order to reconstruct the original file.
- Manage memory efficiently instead of loading entire files into RAM.
- Handle node failures during downloads and select surviving replicas.
- Test concurrent requests, streaming behavior, and resource cleanup.

#### Database Management Systems (DBMS)
- Query `chunks` and `chunk_replicas` to construct a download plan.
- Use joins, aggregation, and subqueries to calculate file availability and replica counts.
- Query file metadata for the session dashboard.
- Test consistency between stored files, chunk records, and replica records.

#### Frontend contribution
- Integrate the download, file-listing, and availability features.
- Test end-to-end communication between the AI-designed UI and the backend.
- Coordinate integration testing and deployment checks.

**Deliverable:** A reliable download pipeline, availability reporting, and a fully integrated application.

---

## 2. Workload Balance

Every member has an OS component, a DBMS component, a frontend integration task, and a testable deliverable.

| Work category | Member 1 | Member 2 | Member 3 | Member 4 |
|---|---|---|---|---|
| Main system module | Upload | Storage nodes | Sessions/auth | Download/integration |
| OS focus | Chunk I/O | Disk I/O, failures | Concurrency, cleanup | Streaming, memory |
| DBMS focus | Files and chunks | Nodes and replicas | Sessions and members | Joins and availability |
| Frontend | Upload progress | Node dashboard | Session screens | Download/dashboard |
| Testing | Upload tests | Replication/failure tests | Session/auth tests | Download/integration tests |

This is a balanced starting point. Member 4 may have more integration work, so they should own fewer unrelated tasks, while Members 1–3 should help with the final end-to-end test.

## 3. Database Table Ownership

The core SQLite schema is defined in `db.py`. Divide ownership by table so that everyone has a clear DBMS contribution.

| Table or query area | Primary owner | Purpose |
|---|---|---|
| `files` | Member 1 | File name, size, status, upload mode |
| `chunks` | Member 1 | Chunk index and size |
| `nodes` | Member 2 | Storage-node URLs and identifiers |
| `chunk_replicas` | Member 2 | Which nodes store each chunk |
| `sessions` | Member 3 | Session codes, host tokens, expiration |
| `session_members` | Member 3 | Host/guest membership |
| Download queries | Member 4 | File reconstruction and availability |

Member 4 owns the queries and retrieval logic, not a redundant new set of database tables. All four members should understand the overall schema and how their tables relate.

## 4. Suggested Implementation Order

1. **Agree on API contracts and the database schema.** All members agree on request/response formats, table ownership, and error handling before coding in parallel.
2. **Develop the four modules independently.** Use separate Git branches and small commits; avoid having multiple people edit `db.py` or the same route at the same time.
3. **Integrate the backend.** Verify that upload, replication, sessions, and download work together.
4. **Connect the AI-designed UI.** Each member integrates and tests the frontend portion associated with their module.
5. **Run a shared demonstration.** Upload a file, show chunks and replicas, simulate a node failure, verify availability, and download the original file.