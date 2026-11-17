"""Load sample data into a RUNNING Folio so the stats page and the room are not empty.

    python seed_demo.py            (or:  python start.py --seed)

Creates a room "Demo teacher" with two guests, uploads a few files (including two real images, so Preview works)
and shares two texts. Prints the room code. Safe to run more than once: each run makes a new room.
"""
import os, struct, sys, zlib
import httpx

API = os.environ.get("FOLIO_API", "http://127.0.0.1:8000")
MB = 1 << 20
c = httpx.Client(base_url=API, timeout=120)

def png(w: int, h: int, pixel) -> bytes:
    """A valid PNG made from scratch, so no image library is needed."""
    raw = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(w)) for y in range(h))
    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")

def sunset(x, y):                                           # sky gradient, a sun, and a dark horizon
    if y > 250: return (20, 30 + (y - 250) // 3, 60)
    d = ((x - 330) ** 2 + (y - 190) ** 2) ** 0.5
    if d < 46: return (255, 232, 120)
    return (255 - y // 3, 110 + y // 4 + x // 12, 90 + y // 2)

def pattern(x, y):                                          # colourful diagonal stripes
    k = ((x + y) // 24) % 4
    return [(43, 76, 155), (194, 59, 59), (47, 125, 91), (122, 79, 163)][k]

def upload(code, hdr, data, name, chunk_mb=4):
    r = c.post("/upload/init", json={"session": code, "filename": name, "size": len(data), "mode": "fixed", "chunk_size_mb": chunk_mb}, headers=hdr)
    r.raise_for_status(); uid, step = r.json()["upload_id"], chunk_mb * MB
    for i in range(0, len(data), step):
        c.put(f"/upload/{uid}/chunk/{i // step}", content=data[i:i + step], headers=hdr).raise_for_status()
    c.post(f"/upload/{uid}/complete", headers=hdr).raise_for_status()
    print(f"  uploaded {name}  ({len(data) / MB:.1f} MB, {-(-len(data) // step)} chunks)")

try:
    c.get("/healthz").raise_for_status()
except httpx.HTTPError:
    sys.exit(f"Cannot reach {API}. Start Folio first:  python start.py")

print("Loading demo data...")
t = c.post("/sessions", json={"name": "Demo teacher", "upload_policy": "open", "max_file_mb": 50, "max_files_per_guest": 5, "room_quota_mb": 1024}).json()
code, H = t["code"], {"X-Host-Token": t["host_token"]}
asha = c.post(f"/sessions/{code}/join", json={"name": "Asha"}).json(); ben = c.post(f"/sessions/{code}/join", json={"name": "Ben"}).json()
A, B = {"X-Member-Token": asha["member_token"]}, {"X-Member-Token": ben["member_token"]}

upload(code, H, os.urandom(26 * MB), "lecture-recording.bin")                       # 7 chunks: a good chunk map
upload(code, H, os.urandom(9 * MB), "dataset-sample.bin")
upload(code, A, png(480, 320, sunset), "sunset.png", 1)
upload(code, B, png(480, 320, pattern), "pattern.png", 1)
for hdr, body in ((H, "Wi-Fi: classroom-5G\nHomework: read chapter 4 and bring one question"), (A, "print('hello from Asha')\nfor i in range(3):\n    print(i)")):
    c.post(f"/sessions/{code}/texts", json={"body": body}, headers=hdr).raise_for_status()
print("  shared 2 texts")
print(f"\nDemo room ready.  Code: {code}   Link: {API}/?join={code}")
print("To see it as the teacher, open the app and Start a session (the demo room is owned by a separate demo teacher).")
