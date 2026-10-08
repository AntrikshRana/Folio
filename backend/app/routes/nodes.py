from fastapi import APIRouter, Depends
from .. import pool
from ..auth import require_any_host

router = APIRouter(prefix="/nodes", tags=["nodes"])

@router.get("/health")
async def health():
    return await pool.health()

@router.post("/{i}/fail", dependencies=[Depends(require_any_host)])
async def fail(i: int):
    return await pool.admin(i, "fail")

@router.post("/{i}/recover", dependencies=[Depends(require_any_host)])
async def recover(i: int):
    return await pool.admin(i, "recover")
