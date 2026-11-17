# Folio: quick start

You need Python 3.10+ and (once, to build the web page) Node.js 18+.

```
cd backend
pip install -r requirements-pinned.txt     # exact versions that were tested
cd ..
python start.py --seed                     # builds the UI, starts everything, loads sample data
```

Open the address it prints. Phones and laptops on the same Wi-Fi can open the "Other devices" address
(allow Python through the firewall if asked).

- Start a session as the teacher, share the code or invite link, join from another device.
- Live stats: add `/#stats` to the address. Database tab: `/#stats-db`.
- Check everything works end to end (second terminal): `cd backend && python e2e_check.py`

Options: `--fresh` (delete old data), `--no-sim` (hide Simulate failure), `--no-build`, `--port N`.
Stop with Ctrl+C. Nothing is installed outside the project folder except the Python and npm packages.
