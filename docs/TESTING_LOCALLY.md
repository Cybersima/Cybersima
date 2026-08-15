# Test Lockwell on your computer

You do **not** need the cloud agent environment.

## Download the files to your computer

### Option 1 — portable ZIP from GitHub (easiest)

Download this file and unzip it on your Desktop:

https://github.com/Cybersima/Cybersima/raw/cursor/lockwell-identity-mvp-1cbb/dist/lockwell-portable.zip

If the browser only shows a page instead of downloading, use the folder view and click the zip file’s download button:

https://github.com/Cybersima/Cybersima/tree/cursor/lockwell-identity-mvp-1cbb/dist

### Option 2 — full branch ZIP

https://github.com/Cybersima/Cybersima/archive/refs/heads/cursor/lockwell-identity-mvp-1cbb.zip

## Run it

Requirements: Python 3.11+, Node.js 20+, npm (or Docker).

### macOS / Linux

```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

### Windows (PowerShell)

```powershell
.\scripts\start.ps1
```

Open **http://127.0.0.1:5000**

### Docker

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
