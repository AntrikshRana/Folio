"""Local dev: starts 3 nodes (8001-8003) + the coordinator (8000). Run from the backend folder."""
import os, secrets, subprocess, sys
SECRET = secrets.token_hex(16)               # fresh shared secret each run; never leaves this machine
procs = []
def start(app, port, **env):
    procs.append(subprocess.Popen([sys.executable, "-m", "uvicorn", app, "--port", str(port)], env={**os.environ, "NODE_SECRET": SECRET, "ALLOW_SIMULATION": "1", **env}))
for i, n in enumerate(["alpha", "bravo", "charlie"], 1):
    start("app.node:app", 8000 + i, NODE_NAME=f"node-{n}", NODE_DIR=f"data/node{i}")
start("app.coordinator:app", 8000, DATA_DIR="data")
try:
    for p in procs: p.wait()
except KeyboardInterrupt:
    for p in procs: p.terminate()
