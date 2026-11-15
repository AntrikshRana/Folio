"""Room rules: defaults, server-side ceilings, and what may be previewed. Everything here is enforced on the server."""
import os

def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default

CEIL_FILE_MB = _int("MAX_FILE_MB_CEILING", 2048)          # the most a teacher can allow per file
CEIL_ROOM_MB = _int("ROOM_QUOTA_MB_CEILING", 10240)       # the most a teacher can allow for one room
CEIL_FILES = _int("MAX_FILES_PER_GUEST_CEILING", 50)
DEFAULT_FILE_MB = min(50, CEIL_FILE_MB)
DEFAULT_ROOM_MB = min(1024, CEIL_ROOM_MB)
DEFAULT_FILES = min(5, CEIL_FILES)

PREVIEW_MAX_MB = _int("PREVIEW_MAX_MB", 25)               # bigger images must be downloaded
# SVG is deliberately absent: an SVG opened directly can run scripts.
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
               ".webp": "image/webp", ".avif": "image/avif", ".bmp": "image/bmp"}

TEXT_MAX_CHARS = 20_000       # one shared text
TEXT_INLINE_CHARS = 2_000     # texts up to this length ride along with the room poll; longer ones are fetched on demand
TEXT_PER_GUEST = 20
TEXT_LIST_LIMIT = 50

def image_type(filename: str) -> str | None:
    return IMAGE_TYPES.get(os.path.splitext(filename.lower())[1])

def previewable(filename: str, size: int) -> bool:
    return image_type(filename) is not None and size <= PREVIEW_MAX_MB * 1048576
