import secrets
from fastapi import Header, HTTPException
from . import db

def get_session(c, code: str):
    row = c.execute("SELECT * FROM sessions WHERE code=? AND expires_at > datetime('now')", (code.strip().upper(),)).fetchone()
    if not row:
        raise HTTPException(404, "session not found or expired")
    return row

def check_host(session_row, token: str | None) -> None:
    if not token or not secrets.compare_digest(token, session_row["host_token"]):
        raise HTTPException(403, "only the session host can do this")

def require_any_host(x_host_token: str | None = Header(None)) -> None:
    with db.tx() as c:
        ok = x_host_token and c.execute(
            "SELECT 1 FROM sessions WHERE host_token=? AND expires_at > datetime('now')", (x_host_token,)).fetchone()
    if not ok:
        raise HTTPException(403, "host token required")
