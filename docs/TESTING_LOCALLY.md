# Test Lockwell on your computer

You do **not** need the cloud agent environment. Use either option below after cloning this branch/PR.

## Option A — one command (recommended)

Requirements: Python 3.11+, Node.js 20+, npm.

### macOS / Linux

```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

Open **http://127.0.0.1:5000**

### Windows (PowerShell)

```powershell
.\scripts\start.ps1
```

Open **http://127.0.0.1:5000**

This builds the UI, installs Python deps, and serves API + app together on port 5000.

## Option B — Docker

Requirements: Docker Desktop.

```bash
docker compose up --build
```

Open **http://127.0.0.1:5000**

## Try Network Guard (optional second terminal)

1. Create an account in the app.
2. Open **Network Guard** and copy the agent token.
3. Run:

```bash
export LOCKWELL_GUARD_TOKEN=paste-token-here
./scripts/start-network-guard.sh
```

Windows:

```powershell
$env:LOCKWELL_GUARD_TOKEN="paste-token-here"
cd backend
.\.venv\Scripts\python.exe -m network_guard.agent --mode simulate --force-simulate
```

## What you can click through

1. Register → dashboard
2. Vault → unlock with a passphrase → store a secret
3. Monitoring → add an identifier
4. Network Guard → start the agent → watch blocks/events
5. Audit log → confirm actions were recorded

## Stop

- Local scripts: `Ctrl+C` in the terminal
- Docker: `docker compose down`
