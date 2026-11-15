import secrets, sqlite3
from typing import Literal
from urllib.parse import quote
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from .. import config, db, files, rules, stats
from ..auth import check_host, get_session, token_hash, upload_state

router = APIRouter(prefix="/sessions", tags=["sessions"])
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"        # no 0/O/1/I so codes are easy to read out loud

class Person(BaseModel):
    name: str = Field(min_length=1, max_length=40)

class RulesIn(BaseModel):
    """What the teacher picks when starting a session."""
    upload_policy: Literal["open", "approval"] = "approval"
    max_file_mb: int = Field(rules.DEFAULT_FILE_MB, ge=1, le=rules.CEIL_FILE_MB)
    max_files_per_guest: int = Field(rules.DEFAULT_FILES, ge=1, le=rules.CEIL_FILES)
    room_quota_mb: int = Field(rules.DEFAULT_ROOM_MB, ge=1, le=rules.CEIL_ROOM_MB)

class NewSession(Person, RulesIn):
    pass

class Settings(BaseModel):
    """Any subset of the rules; fields left out stay as they are."""
    upload_policy: Literal["open", "approval"] | None = None
    max_file_mb: int | None = Field(None, ge=1, le=rules.CEIL_FILE_MB)
    max_files_per_guest: int | None = Field(None, ge=1, le=rules.CEIL_FILES)
    room_quota_mb: int | None = Field(None, ge=1, le=rules.CEIL_ROOM_MB)

class MemberUpload(BaseModel):
    allowed: bool | None = None                     # true: allow, false: block, null: follow the room policy again

def _clean(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise HTTPException(400, "please enter a name")
    return name

def _rules_of(s) -> dict:
    return {k: s[k] for k in ("upload_policy", "max_file_mb", "max_files_per_guest", "room_quota_mb")}

def _add_member(c, sid: str, name: str, role: str) -> dict:
    """Give someone an identity: a unique display name, a public id, and a secret token (only its hash is stored)."""
    taken = {r["name"].lower() for r in c.execute("SELECT name FROM session_members WHERE session_id=?", (sid,))}
    final, n = name, 1
    while final.lower() in taken:                    # two people called Asha become "Asha" and "Asha (2)"
        n += 1
        final = f"{name} ({n})"
    token, mid = secrets.token_urlsafe(24), secrets.token_hex(4)
    c.execute("INSERT INTO session_members(session_id,name,role,member_id,token_hash) VALUES(?,?,?,?,?)",
              (sid, final, role, mid, token_hash(token)))
    return {"name": final, "member_id": mid, "member_token": token}

@router.post("")
def create_session(p: NewSession):
    name = _clean(p.name)
    raw = "".join(secrets.choice(ALPHABET) for _ in range(8))
    code, token, sid = f"{raw[:4]}-{raw[4:]}", secrets.token_urlsafe(24), secrets.token_hex(8)
    with db.tx() as c:
        c.execute("DELETE FROM sessions WHERE expires_at <= datetime('now')")      # expired sessions + their metadata
        c.execute("""INSERT INTO sessions(id,code,host_token,title,expires_at,upload_policy,max_file_mb,max_files_per_guest,room_quota_mb)
                     VALUES(?,?,?,?,datetime('now', ?),?,?,?,?)""",
                  (sid, code, token, f"{name}'s session", f"+{config.SESSION_TTL_HOURS} hours",
                   p.upload_policy, p.max_file_mb, p.max_files_per_guest, p.room_quota_mb))
        me = _add_member(c, sid, name, "host")
    return {"code": code, "host_token": token, **me}

@router.post("/{code}/join")
def join_session(code: str, p: Person):
    name = _clean(p.name)
    for _ in range(5):                               # two people joining at the same instant may pick the same name: retry
        try:
            with db.tx() as c:
                s = get_session(c, code)
                me = _add_member(c, s["id"], name, "guest")
            return {"code": s["code"], **me}
        except sqlite3.IntegrityError:
            continue
    raise HTTPException(409, "could not pick a unique name, please try again")

@router.post("/{code}/settings")
def update_settings(code: str, b: Settings, x_host_token: str | None = Header(None)):
    changes = {k: v for k, v in b.model_dump().items() if v is not None}     # keys come from the model, never from the client
    with db.tx() as c:
        s = get_session(c, code)
        check_host(s, x_host_token)
        if changes:
            c.execute(f"UPDATE sessions SET {', '.join(k + '=?' for k in changes)} WHERE id=?", [*changes.values(), s["id"]])
        return _rules_of(get_session(c, code))

@router.post("/{code}/members/{mid}/upload")
def set_member_upload(code: str, mid: str, b: MemberUpload, x_host_token: str | None = Header(None)):
    with db.tx() as c:
        s = get_session(c, code)
        check_host(s, x_host_token)
        r = c.execute("UPDATE session_members SET can_upload=? WHERE session_id=? AND member_id=? AND role='guest'",
                      (None if b.allowed is None else int(b.allowed), s["id"], mid))
        if r.rowcount == 0:
            raise HTTPException(404, "no such guest in this session")
    return {"ok": True}

@router.get("/{code}")
def session_info(code: str):
    with db.tx() as c:
        s = get_session(c, code)
        members = [{"id": r["id"], "name": r["name"], "role": r["role"], "upload": upload_state(s, r)} for r in c.execute(
            "SELECT member_id AS id, name, role, can_upload FROM session_members WHERE session_id=? ORDER BY joined_at, rowid", (s["id"],))]
        used = c.execute(f"SELECT COALESCE(SUM(size),0) FROM files WHERE session_id=? AND {files.LIVE}", (s["id"],)).fetchone()[0]
        texts = [dict(r) for r in c.execute(
            """SELECT t.id, t.member_id, t.created_at, LENGTH(t.body) AS length,
                      CASE WHEN LENGTH(t.body) <= ? THEN t.body END AS body, SUBSTR(t.body, 1, 200) AS head,
                      (SELECT m.name FROM session_members m WHERE m.session_id = t.session_id AND m.member_id = t.member_id) AS author
               FROM texts t WHERE t.session_id = ? ORDER BY t.created_at DESC, t.rowid DESC LIMIT ?""",
            (rules.TEXT_INLINE_CHARS, s["id"], rules.TEXT_LIST_LIMIT))]
        return {"code": s["code"], "title": s["title"], "expires_at": s["expires_at"], "upload_policy": s["upload_policy"],
                "limits": _rules_of(s) | {"preview_max_mb": rules.PREVIEW_MAX_MB, "text_max_chars": rules.TEXT_MAX_CHARS},
                "room_used": used, "members": members, "texts": texts, "files": files.list_files(c, s["id"])}

async def _serve(code: str, fid: str, inline: bool):
    with db.tx() as c:
        s = get_session(c, code)
        f = c.execute("SELECT filename, size FROM files WHERE id=? AND session_id=? AND status='complete'",
                      (fid, s["id"])).fetchone()
        plan = files.chunk_plan(c, fid) if f else []
    if not f:
        raise HTTPException(404, "file not in this session")
    headers = {"X-Content-Type-Options": "nosniff", "Content-Length": str(f["size"])}
    if inline:                                       # preview: only whitelisted images, and never anything that could run as a page
        media = rules.image_type(f["filename"])
        if not media:
            raise HTTPException(415, "only images can be previewed")
        if f["size"] > rules.PREVIEW_MAX_MB * config.MB:
            raise HTTPException(413, f"too large to preview (limit {rules.PREVIEW_MAX_MB} MB), download it instead")
        headers |= {"Content-Disposition": f"inline; filename*=UTF-8''{quote(f['filename'])}",
                    "Content-Security-Policy": "default-src 'none'; sandbox", "Cache-Control": "private, max-age=60"}
    else:
        media = "application/octet-stream"
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(f['filename'])}"
    stats.record("preview_started" if inline else "download_started", fid, size=f["size"])
    lost = await files.lost_chunks(plan)
    if lost:                                         # fail before streaming so the browser gets a clean error
        raise HTTPException(503, f"{len(lost)} chunk(s) have no online copy – too many nodes are down")
    return StreamingResponse(files.stream(fid, plan), media_type=media, headers=headers)

@router.get("/{code}/files/{fid}/download")
async def download(code: str, fid: str):
    return await _serve(code, fid, inline=False)

@router.get("/{code}/files/{fid}/view")
async def view(code: str, fid: str):
    return await _serve(code, fid, inline=True)
