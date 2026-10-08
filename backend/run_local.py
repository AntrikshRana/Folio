"""Local dev: starts 3 nodes (8001-8003) + the coordinator (8000). Run from the backend folder."""
import os, subprocess, sys
procs = []
def start(app, port, **env):
    procs.append(subprocess.Popen([sys.executable, "-m", "uvicorn", app, "--port", str(port)], env={**os.environ, **env}))
for i, n in enumerate(["alpha", "bravo", "charlie"], 1):
    start("app.node:app", 8000 + i, NODE_NAME=f"node-{n}", NODE_DIR=f"data/node{i}")
start("app.coordinator:app", 8000, DATA_DIR="data")
try:
    for p in procs: p.wait()
except KeyboardInterrupt:
    for p in procs: p.terminate()
