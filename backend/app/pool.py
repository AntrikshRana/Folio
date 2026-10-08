"""Live view of the storage nodes: reachability, throughput, load, health checks, simulated failures."""
import asyncio
import httpx
from fastapi import HTTPException
from . import config

client = httpx.AsyncClient(timeout=httpx.Timeout(60, connect=2))
up = {u: True for u in config.NODES}       # last known reachability
tp = {u: 20.0 for u in config.NODES}       # smoothed throughput per node, MB/s
held = [0] * len(config.NODES)             # replicas placed per node (restored from the DB at startup)
names: dict[int, str] = {}

def recommend(mbps: float) -> int:
    """Chunk size (MB) ~ what a node can take in 0.4 s, snapped to the allowed sizes."""
    return min(config.SIZES, key=lambda s: abs(s - mbps * 0.4))

async def ping(i: int) -> dict:
    url = config.NODES[i]
    base = {"id": i, "url": url, "name": names.get(i, f"node-{i+1}"), "online": False,
            "failed": False, "throughput_mbps": 0, "chunks": 0}
    try:
        r = await client.get(f"{url}/health", timeout=5)      # generous: free hosts wake up slowly
        r.raise_for_status()
        d = r.json(); up[url] = True; names[i] = d["name"]
        return {**base, "name": d["name"], "online": True, "throughput_mbps": round(tp[url], 1), "chunks": d["chunks"]}
    except httpx.HTTPStatusError as e:                        # node answered 503 = simulated failure
        up[url] = False
        return {**base, "failed": "simulated" in e.response.text}
    except Exception:                                         # node process unreachable
        up[url] = False
        return base

async def health() -> list[dict]:
    return await asyncio.gather(*(ping(i) for i in range(len(config.NODES))))

async def refresh(indices) -> None:
    await asyncio.gather(*(ping(i) for i in set(indices)))

async def admin(i: int, action: str) -> dict:
    if not 0 <= i < len(config.NODES):
        raise HTTPException(404, "no such node")
    try:
        (await client.post(f"{config.NODES[i]}/admin/{action}", timeout=5)).raise_for_status()
    except Exception:
        raise HTTPException(502, "node process is unreachable")
    up[config.NODES[i]] = action == "recover"
    return {"ok": True, "node": i, "action": action}
