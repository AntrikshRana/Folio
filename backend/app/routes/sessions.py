import secrets
from urllib.parse import quote
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from .. import config, db, files
from ..auth import get_session

router = APIRouter(prefix="/sessions", tags=["sessions"])
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"        # no 0/O/1/I so codes are easy to read out loud

class Person(BaseModel):
    name: str = Field(min_length=1, max_length=40)

@router.post("")
def create_session(p: Person):
    raw = "".join(secrets.choice(ALPHABET) for _ in range(8))
    code, token, sid = f"{raw[:4]}-{raw[4:]}", secrets.token_urlsafe(24), secrets.token_hex(8)
    with db.tx() as c:
        c.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")      # expired sessions + their metadata
        c.execute("INSERT INTO sessions(id,code,host_token,title,expires_at) VALUES(?,?,?,?,datetime('now', ?))",
                  (sid, code, token, f"{p.name}'s session", f"+{config.SESSION_TTL_HOURS} hours"))
        c.execute("INSERT INTO session_members(session_id,name,role) VALUES(?,?,'host')", (sid, p.name))
    return {"code": code, "host_token": token}

@router.post("/{code}/join")
def join_session(code: str, p: Person):
    with db.tx() as c:
        s = get_session(c, code)
        c.execute("INSERT OR IGNORE INTO session_members(session_id,name,role) VALUES(?,?,'guest')", (s["id"], p.name))
    return {"code": s["code"]}

@router.get("/{code}")
def session_info(code: str):
    with db.tx() as c:
        s = get_session(c, code)
        members = [dict(r) for r in c.execute(
            "SELECT name, role FROM session_members WHERE session_id=? ORDER BY joined_at, rowid", (s["id"],))]
        return {"code": s["code"], "title": s["title"], "expires_at": s["expires_at"],
                "members": members, "files": files.list_files(c, s["id"])}

@router.get("/{code}/files/{fid}/download")
async def download(code: str, fid: str):
    with db.tx() as c:
        s = get_session(c, code)
        f = c.execute("SELECT filename, size FROM files WHERE id=? AND session_id=? AND status='complete'",
                      (fid, s["id"])).fetchone()
        plan = files.chunk_plan(c, fid) if f else []
    if not f:
        raise HTTPException(404, "file not in this session")
    lost = await files.lost_chunks(plan)
    if lost:                                         # fail before streaming so the browser gets a clean error
        raise HTTPException(503, f"{len(lost)} chunk(s) have no online copy – too many nodes are down")
    return StreamingResponse(files.stream(fid, plan), media_type="application/octet-stream", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(f['filename'])}",
        "Content-Length": str(f["size"])})
