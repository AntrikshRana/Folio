# Folio: quick start

You need Python 3.10+ and Node.js 18+.

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
pip install -r requirements-pinned.txt     # exact versions that were tested
```

Start the coordinator and storage nodes in separate terminals:

```bash
# terminal 1
cd backend
python -m uvicorn app.coordinator:app --host 0.0.0.0 --port 8000

# terminal 2
cd backend
python -m uvicorn app.node:app --host 0.0.0.0 --port 8001

# terminal 3
cd backend
python -m uvicorn app.node:app --host 0.0.0.0 --port 8002

# terminal 4
cd backend
python -m uvicorn app.node:app --host 0.0.0.0 --port 8003
```

Then start the frontend in another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the UI at http://localhost:5173. Phones and laptops on the same Wi‑Fi can use the LAN address from the dev server.

- Start a session as the teacher, share the code or invite link, join from another device.
- Live stats: add `/#stats` to the address. Database tab: `/#stats-db`.
- Check everything works end to end in a separate terminal: `cd backend && python e2e_check.py`

Nothing is installed outside the project folder except the Python and npm packages.
