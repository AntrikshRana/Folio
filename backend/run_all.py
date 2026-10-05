"""Starts 3 nodes (8001-8003) + the coordinator (8000). Run from the backend folder."""
import os, subprocess, sys
procs = []
def start(app, port, **env):
    procs.append(subprocess.Popen([sys.executable, "-m", "uvicorn", app, "--port", str(port)],
                                  env={**os.environ, **env}))
for i in (1, 2, 3):
    start("node:app", 8000 + i, NODE_NAME=f"node-{['alpha','bravo','charlie'][i-1]}", NODE_DIR=f"data/node{i}")
start("coordinator:app", 8000)
try:
    for p in procs: p.wait()
except KeyboardInterrupt:
    for p in procs: p.terminate()
