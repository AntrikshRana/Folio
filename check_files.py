"""Run from the project root (the folder that contains backend and frontend):   python check_files.py
Lists any Folio file that is missing, then tests that the backend can be imported. Changes nothing."""
import os, pathlib, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parent
EXPECTED = """
backend/run_local.py backend/e2e_check.py backend/seed_demo.py backend/requirements-pinned.txt
backend/app/__init__.py backend/app/config.py backend/app/coordinator.py backend/app/db.py backend/app/auth.py backend/app/pool.py
backend/app/files.py backend/app/rules.py backend/app/stats.py backend/app/dbinfo.py backend/app/node.py
backend/app/routes/__init__.py backend/app/routes/nodes.py backend/app/routes/sessions.py backend/app/routes/upload.py
backend/app/routes/texts.py backend/app/routes/live.py
frontend/src/main.tsx frontend/src/App.tsx frontend/src/api.ts frontend/src/types.ts frontend/src/copy.ts frontend/src/demo.ts frontend/src/styles.css
frontend/src/components/SessionGate.tsx frontend/src/components/Room.tsx frontend/src/components/Teacher.tsx frontend/src/components/Rules.tsx
frontend/src/components/TextShare.tsx frontend/src/components/Stats.tsx frontend/src/components/DbStats.tsx
frontend/src/components/stats.css frontend/src/components/extras.css start.py QUICKSTART.md
""".split()
missing = [p for p in EXPECTED if not (ROOT / p).is_file()]
print(f"Checked {len(EXPECTED)} files in {ROOT}")
if missing:
    print("\nMISSING:"); [print("  " + m) for m in missing]
    print("\nCopy these from the zip into the same folders (keep the folder structure).")
else:
    print("All files are present.")
env = {**os.environ, "FOLIO_DEV": "1"}
r = subprocess.run([sys.executable, "-c", "import app.coordinator, app.node"], cwd=ROOT / "backend", env=env, capture_output=True, text=True)
print("\nBackend imports cleanly." if r.returncode == 0 else "\nBackend does NOT import:\n" + r.stderr.strip().splitlines()[-1])
sys.exit(1 if missing or r.returncode else 0)
