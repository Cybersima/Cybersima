# Lockwell

Identity-protection MVP with a security-first architecture: zero-knowledge vault, hashed monitoring, device posture, alerts, and a transparent audit log.

## What’s included

- **Landing + app UI** (React / Vite / TypeScript)
- **API** (Flask / SQLAlchemy / SQLite)
- **Zero-knowledge vault** — AES-GCM encryption in the browser; server stores ciphertext only
- **Monitored identifiers** — peppered HMAC hashes + masked display values
- **Alerts & device posture** — demo breach/device signals and protection toggles
- **Network Guard** — edge agent for live hostile-packet detection and blocking
- **Audit log** — every sensitive action recorded for the account owner

## Quick start

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

API listens on `http://127.0.0.1:5000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App listens on `http://127.0.0.1:5173` and proxies `/api` to the backend.

### Optional demo alert injector

```bash
cd backend
source .venv/bin/activate
python threat_generator.py
```

### Network Guard edge agent

```bash
cd backend
source .venv/bin/activate
export LOCKWELL_API=http://127.0.0.1:5000
export LOCKWELL_GUARD_TOKEN=<token from /app/network>
python -m network_guard.agent --mode simulate
```

On a real gateway/firewall host with privileges:

```bash
sudo python -m network_guard.agent --mode enforce --interface eth0
```

See `docs/NETWORK_GUARD.md`.

## Security notes (MVP)

Lockwell is a working product shell, not a licensed identity-theft insurance / credit-bureau service.

- Vault keys never leave the browser in this design.
- Breach / dark-web alerts are **simulated** for the demo corpus.
- Credit monitoring, insurance, and restoration still require partner integrations.
- Stopping bad packets **before they enter the LAN** requires deploying Network Guard on the edge gateway, not only in the browser.

See `/architecture` in the app or `GET /api/architecture`.
