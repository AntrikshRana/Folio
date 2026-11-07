"""GET /stats: one cached snapshot for the live stats page. Read-only, no names, no node URLs."""
import asyncio, time
from fastapi import APIRouter
from .. import config, pool, stats

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
