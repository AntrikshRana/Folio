"""End-to-end check against a RUNNING Folio:   python run_local.py   (one terminal)   then   python e2e_check.py   (another).

Uploads and downloads real data through the coordinator and the three storage nodes, fails nodes on purpose,
and prints PASS/FAIL for each claim. Exit code 0 means everything passed. Needs: pip install httpx
"""
import hashlib, os, sys, threading, time
import httpx

API = os.environ.get("FOLIO_API", "http://127.0.0.1:8000")
MB = 1 << 20
c = httpx.Client(base_url=API, timeout=120)
failed = 0

def check(name: str, cond: bool, detail: str = "") -> None:
    global failed
    failed += not cond
    print(("PASS  " if cond else "FAIL  ") + name + (f"   [{detail}]" if detail else ""))

def upload(code, hdr, data: bytes, name="data.bin", chunk_mb=4):
    r = c.post("/upload/init", json={"session": code, "filename": name, "size": len(data), "mode": "fixed", "chunk_size_mb": chunk_mb}, headers=hdr)
    if r.status_code != 200:
        return None, r
    uid, step = r.json()["upload_id"], chunk_mb * MB
    for i in range(0, len(data), step):
        r = c.put(f"/upload/{uid}/chunk/{i // step}", content=data[i:i + step], headers=hdr)
        if r.status_code != 200:
            return uid, r
    return uid, c.post(f"/upload/{uid}/complete", headers=hdr)

def files(code):
    return {f["filename"]: f for f in c.get(f"/sessions/{code}").json()["files"]}

def total_chunks():
    time.sleep(3.2)                                           # the coordinator caches node health for 3 s
    return sum(n["chunks"] for n in c.get("/nodes/health").json())

sha = lambda b: hashlib.sha256(b).hexdigest()

# ---- the stack is up
try:
    h = c.get("/healthz").json()
except httpx.HTTPError:
    sys.exit(f"Cannot reach {API}. Start the stack first:  python run_local.py")
nodes = c.get("/nodes/health").json()
check("coordinator is up and all 3 storage nodes are online", h["ok"] and len(nodes) == 3 and all(n["online"] for n in nodes), ", ".join(n["name"] for n in nodes))
rss0 = h["rss_mb"]

# ---- a room, a guest, approval
T = c.post("/sessions", json={"name": "Teacher", "upload_policy": "approval", "max_file_mb": 5, "max_files_per_guest": 2, "room_quota_mb": 300}).json()
code, H = T["code"], {"X-Host-Token": T["host_token"]}
G = c.post(f"/sessions/{code}/join", json={"name": "Asha"}).json(); GH = {"X-Member-Token": G["member_token"]}
check("guest cannot upload before approval", c.post("/upload/init", json={"session": code, "filename": "x", "size": 1}, headers=GH).status_code == 403)
c.post(f"/sessions/{code}/members/{G['member_id']}/upload", json={"allowed": True}, headers=H)
check("guest can upload once the teacher approves", c.post("/upload/init", json={"session": code, "filename": "probe", "size": 1}, headers=GH).status_code == 200)
r = c.post("/upload/init", json={"session": code, "filename": "big", "size": 6 * MB}, headers=GH)
check("file over the room limit is refused (413)", r.status_code == 413, r.json().get("detail", ""))

# ---- upload, replication, checksum
before = total_chunks()
data = os.urandom(18 * MB + 12345)
uid, r = upload(code, H, data, "movie.bin", 4)
check("18 MB upload in 5 chunks completes", r.status_code == 200, str(r.json()))
f = files(code)["movie.bin"]
check("every chunk is stored on 2 nodes", f["chunks"] == 5 and f["min_replicas"] == 2 and len(f["nodes"]) >= 2, f"nodes {f['nodes']}")
check("the nodes hold exactly 10 more chunk copies", total_chunks() - before == 10, f"+{total_chunks() - before}")
d = c.get(f"/sessions/{code}/files/{f['id']}/download")
check("download is byte-identical (SHA-256)", d.status_code == 200 and sha(d.content) == sha(data))

# ---- node failure
fail = lambda i, act: c.post(f"/nodes/{i}/{act}", headers=H)
check("host can simulate a node failure", fail(0, "fail").status_code == 200)
time.sleep(3.2)
check("the failed node shows as failed in /nodes/health", [n for n in c.get("/nodes/health").json() if n["id"] == 0][0]["failed"])
check("a guest cannot fail nodes", c.post("/nodes/1/fail", headers=GH).status_code == 403)
d = c.get(f"/sessions/{code}/files/{f['id']}/download")
check("download still works with one node down (replica failover)", d.status_code == 200 and sha(d.content) == sha(data))
up2 = os.urandom(6 * MB)
uid2, r = upload(code, H, up2, "during-failure.bin", 2)
f2 = files(code).get("during-failure.bin")
check("uploading while a node is down still gets 2 copies, on the surviving nodes", r.status_code == 200 and f2 and f2["min_replicas"] == 2 and 0 not in f2["nodes"], f"nodes {f2 and f2['nodes']}")
time.sleep(1.2)
snap = c.get("/stats").json()
check("the stats page reports that node as offline", snap["nodes"][0]["online"] is False)
fail(0, "recover"); time.sleep(3.2)
check("recovering brings the node back", all(n["online"] for n in c.get("/nodes/health").json()))
for i in range(3): fail(i, "fail")
time.sleep(3.2)
d = c.get(f"/sessions/{code}/files/{f['id']}/download")
check("with every node down, download fails cleanly (503) instead of sending a broken file", d.status_code == 503, d.text[:80])
for i in range(3): fail(i, "recover")
time.sleep(3.2)

# ---- cancel removes bytes from the nodes
before = total_chunks()
u3, _ = upload(code, H, os.urandom(8 * MB), "to-cancel.bin", 4)
mid = total_chunks()
c.delete(f"/upload/{u3}", headers=H)
check("cancelling an upload deletes its chunks from the nodes", mid - before == 4 and total_chunks() == before, f"+{mid - before} then back to +{total_chunks() - before}")

# ---- preview and text
png = os.urandom(20000); upload(code, H, png, "pic.png", 1); upload(code, H, b"<script>1</script>", "page.html", 1)
fl = files(code)
v = c.get(f"/sessions/{code}/files/{fl['pic.png']['id']}/view")
check("an image previews inline with safe headers", v.status_code == 200 and v.headers["content-type"] == "image/png" and v.headers["x-content-type-options"] == "nosniff" and v.content == png)
check("an HTML file cannot be previewed", c.get(f"/sessions/{code}/files/{fl['page.html']['id']}/view").status_code == 415)
tid = c.post(f"/sessions/{code}/texts", json={"body": "wifi: classroom-5G"}, headers=GH).json()["id"]
check("a shared text can be read back", c.get(f"/sessions/{code}/texts/{tid}").json()["body"] == "wifi: classroom-5G")

# ---- load: 96 MB file, 6 downloads at once, memory sampled
big = os.urandom(96 * MB)
_, r = upload(code, H, big, "huge.bin", 8)
check("96 MB upload completes", r.status_code == 200)
fid = files(code)["huge.bin"]["id"]; peak = [0]; stop = threading.Event()
def sampler():
    s = httpx.Client(base_url=API)
    while not stop.is_set():
        peak[0] = max(peak[0], s.get("/healthz").json()["rss_mb"] or 0); time.sleep(0.15)
threading.Thread(target=sampler, daemon=True).start()
hashes, t0 = [], time.time()
def dl():
    hashes.append(sha(httpx.get(f"{API}/sessions/{code}/files/{fid}/download", timeout=300).content))
ts = [threading.Thread(target=dl) for _ in range(6)]; [t.start() for t in ts]; [t.join() for t in ts]; stop.set()
check("6 simultaneous downloads of 96 MB are all byte-identical", len(hashes) == 6 and set(hashes) == {sha(big)}, f"{time.time() - t0:.1f}s")
print(f"INFO  coordinator memory (RSS): {rss0} MB at start, peak {peak[0]} MB during 576 MB of simultaneous downloads")

# ---- the database agrees with all of the above
checks = c.get("/stats/db").json()["checks"]
check("database integrity report is clean after all of this", all(x["bad"] == 0 for x in checks), "; ".join(f"{x['name']}={x['bad']}" for x in checks if x["bad"]))

print(f"\n{'ALL CHECKS PASSED' if not failed else str(failed) + ' CHECK(S) FAILED'}")
sys.exit(1 if failed else 0)
