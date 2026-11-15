"""GET /stats: one cached snapshot for the live stats page. Read-only, no names, no node URLs."""
import asyncio, time
from fastapi import APIRouter
from .. import config, dbinfo, pool, stats

router = APIRouter(prefix="/stats", tags=["stats"])
TTL = 1.0                                   # many viewers share one snapshot per second
_cache: dict = {"at": 0.0, "data": None}
_lock = asyncio.Lock()

@router.get("")
async def live_stats():
    if _cache["data"] is None or time.monotonic() - _cache["at"] > TTL:
        async with _lock:
            if _cache["data"] is None or time.monotonic() - _cache["at"] > TTL:    # someone else may have refreshed meanwhile
                try:
                    await pool.refresh(range(len(config.NODES)))                   # so online/offline is current
                except Exception:
                    pass
                _cache["data"] = await asyncio.to_thread(stats.snapshot)
                _cache["at"] = time.monotonic()
    return _cache["data"]

_db_cache: dict = {"at": 0.0, "data": None}
_db_lock = asyncio.Lock()

@router.get("/db")
async def db_stats():
    """Structure, integrity checks and query timings of the database. Cached for a few seconds."""
    if _db_cache["data"] is None or time.monotonic() - _db_cache["at"] > 5:
        async with _db_lock:
            if _db_cache["data"] is None or time.monotonic() - _db_cache["at"] > 5:
                _db_cache["data"] = await asyncio.to_thread(dbinfo.snapshot)
                _db_cache["at"] = time.monotonic()
    return _db_cache["data"]

@router.get("/db/demo")
async def db_demo():
    return await asyncio.to_thread(dbinfo.demo)
