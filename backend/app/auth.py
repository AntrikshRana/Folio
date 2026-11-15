import hashlib, secrets
from fastapi import Header, HTTPException
from . import config, db

def get_session(c, code: str):
    row = c.execute("SELECT * FROM sessions WHERE code=? AND expires_at > datetime('now')", (code.strip().upper(),)).fetchone()
    if not row:
        raise HTTPException(404, "session not found or expired")
    return row

def check_host(session_row, token: str | None) -> None:
    if not token or not secrets.compare_digest(token.encode(), session_row["host_token"].encode()):
        raise HTTPException(403, "only the session host can do this")

def require_any_host(x_host_token: str | None = Header(None)) -> None:
    with db.tx() as c:
        ok = x_host_token and c.execute(
            "SELECT 1 FROM sessions WHERE host_token=? AND expires_at > datetime('now')", (x_host_token,)).fetchone()
    if not ok:
        raise HTTPException(403, "host token required")

def require_simulation() -> None:
    if not config.ALLOW_SIMULATION:
        raise HTTPException(403, "failure simulation is disabled on this server")

def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def identify(c, session_row, member_token: str | None, host_token: str | None):
    """Who is calling? Returns their session_members row, or raises 401. The host's own token also counts."""
    sid = session_row["id"]
    if host_token and secrets.compare_digest(host_token.encode(), session_row["host_token"].encode()):
        row = c.execute("SELECT * FROM session_members WHERE session_id=? AND role='host'", (sid,)).fetchone()
        if row:
            return row
    if member_token:
        row = c.execute("SELECT * FROM session_members WHERE session_id=? AND token_hash=?", (sid, token_hash(member_token))).fetchone()
        if row:
            return row
    raise HTTPException(401, "missing or invalid member token: join the session first")

def upload_state(session_row, member) -> str:
    """'allowed', 'blocked' (the teacher said no) or 'pending' (the room needs approval and none was given)."""
    if member["role"] == "host":
        return "allowed"
    if member["can_upload"] is not None:                      # the teacher's decision about this person wins
        return "allowed" if member["can_upload"] else "blocked"
    return "allowed" if session_row["upload_policy"] == "open" else "pending"

def require_uploader(session_row, member) -> None:
    state = upload_state(session_row, member)
    if state == "blocked":
        raise HTTPException(403, "the teacher has turned off uploading for you")
    if state == "pending":
        raise HTTPException(403, "waiting for the teacher to approve your uploads")

def file_access(c, uid: str, member_token: str | None, host_token: str | None):
    """(file, session, member) for an upload the caller may touch: its owner, or the session host."""
    f = c.execute("SELECT * FROM files WHERE id=?", (uid,)).fetchone()
    s = c.execute("SELECT * FROM sessions WHERE id=? AND expires_at > datetime('now')", (f["session_id"],)).fetchone() if f else None
    if not f or not s:
        raise HTTPException(404, "unknown or finished upload")
    m = identify(c, s, member_token, host_token)
    if m["role"] != "host" and m["member_id"] != f["member_id"]:
        raise HTTPException(403, "this upload belongs to someone else")
    return f, s, m
