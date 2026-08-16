# Start Lockwell locally on Windows (API + built UI on one port).
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Port = if ($env:PORT) { $env:PORT } else { "5000" }
# Bind on all interfaces so a Kali/gateway agent on the LAN can reach the API.
$HostAddr = if ($env:HOST) { $env:HOST } else { "0.0.0.0" }

Write-Host "==> Lockwell local package"
Write-Host "    root: $Root"

if (-not (Get-Command python -ErrorAction SilentlyContinue) -and -not (Get-Command python3 -ErrorAction SilentlyContinue)) {
  throw "Python 3 is required."
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw "Node.js/npm is required to build the UI."
}

$Python = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "python3" }

Write-Host "==> Building frontend"
Set-Location "$Root\frontend"
if (-not (Test-Path "node_modules")) {
  npm install
}
npm run build

Write-Host "==> Preparing Python environment"
Set-Location "$Root\backend"
if (-not (Test-Path ".venv")) {
  & $Python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt

Write-Host "==> Starting Lockwell on http://${HostAddr}:${Port}"
Write-Host "    Open that URL in your browser."

$env:HOST = $HostAddr
$env:PORT = $Port
$env:FLASK_DEBUG = if ($env:FLASK_DEBUG) { $env:FLASK_DEBUG } else { "0" }
$env:SECRET_KEY = if ($env:SECRET_KEY) { $env:SECRET_KEY } else { "lockwell-local-dev-key" }
$env:MONITOR_PEPPER = if ($env:MONITOR_PEPPER) { $env:MONITOR_PEPPER } else { "lockwell-local-pepper" }

& .\.venv\Scripts\python.exe app.py
