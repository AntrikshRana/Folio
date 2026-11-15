#!/usr/bin/env python3
"""One command to run all of Folio:   python start.py

  1. builds the web UI if it is missing or out of date (needs Node.js 18+; skipped if there is no frontend folder)
  2. starts the 3 storage nodes (private, this computer only) and the coordinator
  3. serves the UI and the API from ONE address, so phones and laptops on the same Wi-Fi just open the link it prints

Options:  --seed      load sample files and texts so the stats page is not empty
          --fresh     delete previous data first      --no-build   do not build the UI
          --no-sim    hide the Simulate-failure buttons (use this for anything public)      --port N   (default 8000)
Stop with Ctrl+C.
"""
import argparse, json, os, pathlib, secrets, shutil, signal, socket, subprocess, sys, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
BACK, FRONT = ROOT / "backend", ROOT / "frontend"
DIST = FRONT / "dist"

ap = argparse.ArgumentParser(description="Run Folio with one command.")
ap.add_argument("--seed", action="store_true"); ap.add_argument("--fresh", action="store_true")
ap.add_argument("--no-build", action="store_true"); ap.add_argument("--no-sim", action="store_true")
ap.add_argument("--port", type=int, default=8000)
args = ap.parse_args()
BASE = f"http://127.0.0.1:{args.port}"

def get(path: str, timeout=2):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read())

def newest(*paths) -> float:
    t = 0.0
    for p in paths:
        p = pathlib.Path(p)
        files = [p] if p.is_file() else [f for f in p.rglob("*") if f.is_file()] if p.is_dir() else []
        t = max([t, *(f.stat().st_mtime for f in files)])
    return t

def build_ui() -> bool:
    if not (FRONT / "package.json").exists():
        print("  (no frontend folder found: running the API only)"); return False
    built = (DIST / "index.html").exists()
    if built and newest(DIST / "index.html") >= newest(FRONT / "src", FRONT / "index.html", FRONT / "package.json"):
        print("  UI is up to date."); return True
    npm = shutil.which("npm")
    if not npm:
        print("  Node.js / npm not found, so the UI cannot be built." + ("  Using the previous build." if built else "  Install Node.js 18+ and run again."))
        return built
    env = {**os.environ, "VITE_API_URL": ""}              # empty = the UI talks to the server it was loaded from
    print("  building the UI (first time takes a minute)...")
    if not (FRONT / "node_modules").exists():
        subprocess.run([npm, "install"], cwd=FRONT, env=env, check=True)
    subprocess.run([npm, "run", "build"], cwd=FRONT, env=env, check=True)
    return True

def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("10.255.255.255", 1)); ip = s.getsockname()[0]; s.close(); return ip
    except OSError:
        return "127.0.0.1"

try:
    get("/healthz"); sys.exit(f"Something is already running on port {args.port} (is Folio already started?). Stop it, or use --port.")
except OSError:
    pass

print("Folio")
have_ui = False if args.no_build else build_ui()
have_ui = have_ui or (DIST / "index.html").exists()
if args.fresh and (BACK / "data").exists():
    shutil.rmtree(BACK / "data"); print("  old data deleted.")

def _stop(*_):                                             # closing the terminal or a plain `kill` must also stop the servers
    raise KeyboardInterrupt
for _sig in ("SIGINT", "SIGTERM", "SIGHUP"):
    if hasattr(signal, _sig):
        signal.signal(getattr(signal, _sig), _stop)

SECRET = secrets.token_hex(16)                             # fresh shared secret every run; never leaves this machine
procs: list[subprocess.Popen] = []
def spawn(app: str, port: int, host: str, **env):
    procs.append(subprocess.Popen([sys.executable, "-m", "uvicorn", app, "--host", host, "--port", str(port), "--log-level", "warning"],
                                  cwd=BACK, env={**os.environ, "NODE_SECRET": SECRET, "ALLOW_SIMULATION": "0" if args.no_sim else "1", **env}))

try:
    for i, n in enumerate(["alpha", "bravo", "charlie"], 1):
        spawn("app.node:app", 8000 + i, "127.0.0.1", NODE_NAME=f"node-{n}", NODE_DIR=f"data/node{i}")      # nodes are never exposed to the network
    spawn("app.coordinator:app", args.port, "0.0.0.0", DATA_DIR="data", **({"FOLIO_STATIC": str(DIST)} if have_ui else {}))
    print("  starting...", end="", flush=True)
    for _ in range(80):
        time.sleep(0.5)
        if any(p.poll() is not None for p in procs):
            sys.exit("\n  A process stopped on start-up. Run it by hand to see why:  cd backend && python run_local.py")
        try:
            if len([n for n in get("/nodes/health", 3) if n["online"]]) == 3: break
        except (OSError, ValueError):
            print(".", end="", flush=True)
    else:
        sys.exit("\n  The nodes did not come up in 40 seconds.")
    print(" ready.\n")
    if args.seed:
        subprocess.run([sys.executable, str(BACK / "seed_demo.py")], env={**os.environ, "FOLIO_API": BASE}, check=False)
        print()
    ip = lan_ip()
    print(f"  On this computer : http://localhost:{args.port}" + ("" if have_ui else "   (API only: no UI was built)"))
    print(f"  Other devices    : http://{ip}:{args.port}   (same Wi-Fi; allow Python through the firewall if asked)")
    print(f"  Live stats       : http://localhost:{args.port}/#stats        Database tab: /#stats-db")
    print("\n  Press Ctrl+C to stop.")
    while True:
        time.sleep(1)
        if any(p.poll() is not None for p in procs):
            print("\n  A process exited unexpectedly; stopping."); break
except KeyboardInterrupt:
    print("\n  stopping...")
finally:
    for p in procs: p.terminate()
    for p in procs:
        try: p.wait(5)
        except subprocess.TimeoutExpired: p.kill()
