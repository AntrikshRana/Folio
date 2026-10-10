"""All settings come from environment variables, so the same code runs locally and on Render."""
import os

def _csv(name: str, default: str) -> list[str]:
    return [x.strip().rstrip("/") for x in os.getenv(name, default).split(",") if x.strip()]

NODES = _csv("NODES", "http://127.0.0.1:8001,http://127.0.0.1:8002,http://127.0.0.1:8003")
CORS_ORIGINS = _csv("CORS_ORIGINS", "*")
REPLICAS = int(os.getenv("REPLICAS", "2"))                  # copies kept of every chunk
MAX_CHUNK_MB = int(os.getenv("MAX_CHUNK_MB", "64"))         # lower this on small instances (RAM)
SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "24"))
DATA_DIR = os.getenv("DATA_DIR", ".")                       # point at a persistent disk on Render
DB_PATH = os.path.join(DATA_DIR, "folio.db")
NODE_CONNECT_TIMEOUT = float(os.getenv("NODE_CONNECT_TIMEOUT", "2"))   # raise on free hosts (cold starts)
PING_TIMEOUT = float(os.getenv("PING_TIMEOUT", "5"))
MAX_PARALLEL_UPLOADS = int(os.getenv("MAX_PARALLEL_UPLOADS", "2"))
MB = 1 << 20
SIZES = [s for s in (1, 2, 4, 8, 16, 32, 64) if s <= MAX_CHUNK_MB]
