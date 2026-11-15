"""Short texts people share in a room (notes, links, code) so others can copy them without a file."""
import secrets
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from .. import db, rules, stats
from ..auth import get_session, identify, require_uploader

router = APIRouter(prefix="/sessions", tags=["texts"])

class TextIn(BaseModel):
    body: str = Field(min_length=1, max_length=rules.TEXT_MAX_CHARS)

@router.post("/{code}/texts")
def share_text(code: str, b: TextIn, x_host_token: str | None = Header(None), x_member_token: str | None = Header(None)):
    if not b.body.strip():
        raise HTTPException(400, "nothing to share")
    tid = secrets.token_hex(6)
    with db.tx() as c:
        c.execute("BEGIN IMMEDIATE")                  # the per-person count check and the insert must not interleave
        s = get_session(c, code)
        me = identify(c, s, x_member_token, x_host_token)
        require_uploader(s, me)                       # same permission as sharing files
        if me["role"] != "host":
            n = c.execute("SELECT COUNT(*) FROM texts WHERE session_id=? AND member_id=?", (s["id"], me["member_id"])).fetchone()[0]
            if n >= rules.TEXT_PER_GUEST:
                raise HTTPException(403, f"limit of {rules.TEXT_PER_GUEST} shared texts per person reached; delete one first")
        c.execute("INSERT INTO texts(id,session_id,member_id,body) VALUES(?,?,?,?)", (tid, s["id"], me["member_id"], b.body))
    stats.record("text_shared", detail=f"{len(b.body)} characters")
    return {"id": tid}

@router.get("/{code}/texts/{tid}")
def read_text(code: str, tid: str):
    with db.tx() as c:
        s = get_session(c, code)
        row = c.execute("SELECT id, body FROM texts WHERE id=? AND session_id=?", (tid, s["id"])).fetchone()
    if not row:
        raise HTTPException(404, "text not found")
    return {"id": row["id"], "body": row["body"]}

@router.delete("/{code}/texts/{tid}")
def delete_text(code: str, tid: str, x_host_token: str | None = Header(None), x_member_token: str | None = Header(None)):
    with db.tx() as c:
        s = get_session(c, code)
        me = identify(c, s, x_member_token, x_host_token)
        row = c.execute("SELECT member_id FROM texts WHERE id=? AND session_id=?", (tid, s["id"])).fetchone()
        if not row:
            return {"ok": True, "removed": False}
        if me["role"] != "host" and me["member_id"] != row["member_id"]:       # your own texts; the host may remove any
            raise HTTPException(403, "this text belongs to someone else")
        c.execute("DELETE FROM texts WHERE id=?", (tid,))
    return {"ok": True, "removed": True}
