"""File queries and chunk streaming shared by the routes."""
from . import config, pool

def list_files(c, session_id: str) -> list[dict]:
    online = [i for i, u in enumerate(config.NODES) if pool.up[u]]
    ph = ",".join("?" * len(online))
    rows = c.execute(f"""
        SELECT f.id, f.filename, f.size, f.created_at,
          (SELECT COUNT(*) FROM chunks k WHERE k.file_id = f.id) AS chunks,
          (SELECT GROUP_CONCAT(DISTINCT r.node_id) FROM chunk_replicas r WHERE r.file_id = f.id) AS nodes,
          NOT EXISTS (SELECT 1 FROM chunks k WHERE k.file_id = f.id AND NOT EXISTS (
              SELECT 1 FROM chunk_replicas r
              WHERE r.file_id = k.file_id AND r.idx = k.idx AND r.node_id IN ({ph}))) AS available
        FROM files f WHERE f.session_id = ? AND f.status = 'complete'
        ORDER BY f.created_at DESC, f.rowid DESC""", [*online, session_id]).fetchall()
    mins = dict(c.execute("""SELECT file_id, MIN(n) FROM (
        SELECT file_id, idx, COUNT(*) AS n FROM chunk_replicas GROUP BY file_id, idx) GROUP BY file_id""").fetchall())
    return [{"id": r["id"], "filename": r["filename"], "size": r["size"], "chunks": r["chunks"],
             "created_at": r["created_at"], "nodes": sorted(int(x) for x in (r["nodes"] or "").split(",") if x),
             "min_replicas": mins.get(r["id"], 0), "available": bool(r["available"])} for r in rows]

def chunk_plan(c, file_id: str) -> list[tuple[int, list[int]]]:
    """[(chunk index, [node ids holding a copy]), ...] in file order."""
    rows = c.execute("""SELECT k.idx, GROUP_CONCAT(r.node_id) AS nodes FROM chunks k
        JOIN chunk_replicas r ON r.file_id = k.file_id AND r.idx = k.idx
        WHERE k.file_id = ? GROUP BY k.idx ORDER BY k.idx""", (file_id,)).fetchall()
    return [(r["idx"], [int(x) for x in r["nodes"].split(",")]) for r in rows]

async def lost_chunks(plan) -> list[int]:
    await pool.refresh(n for _, ns in plan for n in ns)
    return [idx for idx, ns in plan if not any(pool.up[config.NODES[n]] for n in ns)]

async def stream(file_id: str, plan):
    for idx, ns in plan:
        for n in sorted(ns, key=lambda n: not pool.up[config.NODES[n]]):     # any surviving replica will do
            try:
                r = await pool.client.get(f"{config.NODES[n]}/chunks/{file_id}/{idx}")
                r.raise_for_status()
                yield r.content
                break
            except Exception:
                pool.up[config.NODES[n]] = False
        else:
            raise RuntimeError("chunk lost mid-download")
