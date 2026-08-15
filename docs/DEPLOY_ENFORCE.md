# Deploy Network Guard in enforce mode

There are two different “next steps,” depending on what you want to protect.

## A) Protect this Windows PC now (recommended next step)

This applies **real Windows Firewall block rules** on the computer running Lockwell.
It protects that PC. It does **not** by itself protect every device on your home/business LAN.

### Steps

1. Keep Lockwell running at http://127.0.0.1:5000
2. Open **Network Guard** and copy the agent token
3. Stop the old simulate agent (`Ctrl+C`)
4. Open **PowerShell as Administrator**
5. Run:

```powershell
cd "C:\CyberSym\Lockwell Identity\lockwell-portable1\lockwell\backend"
$env:LOCKWELL_API="http://127.0.0.1:5000"
$env:LOCKWELL_GUARD_TOKEN="paste-your-token-here"
.\.venv\Scripts\python.exe -m network_guard.agent --mode enforce --force-simulate
```

Or double-click / run:

```bat
scripts\start-network-guard-enforce.cmd
```

(after editing the token in that script or setting the env var)

### What success looks like

- Agent console shows: `backend=windows-firewall`
- Network Guard events say Windows Firewall block rule applied
- In Windows, check:

```powershell
Get-NetFirewallRule -DisplayName "Lockwell Block*" | Format-Table DisplayName, Enabled, Direction
```

Demo IPs (safe documentation ranges) such as `203.0.113.50` will get real firewall rules.

### Cleanup / remove Lockwell firewall rules

```powershell
Get-NetFirewallRule -DisplayName "Lockwell Block*" | Remove-NetFirewallRule
```

## B) Protect the whole home/business network

For packets to be stopped **before they enter the LAN**, Network Guard must run on the
**gateway/firewall** machine (router box, pfSense/OPNsense box, Raspberry Pi router, etc.).

```
Internet → Lockwell Network Guard (gateway) → LAN devices
```

On a Linux gateway:

```bash
cd backend
source .venv/bin/activate
export LOCKWELL_API=http://<pc-running-dashboard>:5000
export LOCKWELL_GUARD_TOKEN=<token>
sudo python -m network_guard.agent --mode enforce --interface eth0
```

Requirements:
- Machine is actually routing/firewalling LAN traffic
- Root privileges
- `nftables` available
- Prefer live capture (no `--force-simulate`) once ready

## Safety notes

- Always run enforce first with `--force-simulate` on Windows so you can verify firewall rule creation safely.
- Do not block your router, DNS, or critical LAN IPs manually without checking.
- Lockwell refuses to block loopback/link-local addresses.
