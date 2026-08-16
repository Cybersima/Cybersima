# Protect the whole home/business network (gateway deploy)

Host enforce (what you just did) protects **one PC**.  
Gateway enforce protects **every device on the LAN**.

```
Modem/ONT ──► Lockwell Gateway ──► Switch / Wi‑Fi / LAN devices
                     │
                     ▼
            Lockwell dashboard (can stay on your PC)
```

## What you need

A computer that sits **in front of** the rest of your network:

| Option | Notes |
| --- | --- |
| Raspberry Pi / mini PC | Best DIY path |
| Old laptop/desktop with 2 NICs | Ethernet in + Ethernet/Wi‑Fi out |
| OpenWrt / firewall appliance | Advanced; run agent there if Python/nft available |

Your normal Windows PC alone cannot protect the whole LAN unless it becomes the router (two network interfaces + routing). That is possible, but a small Linux box is cleaner.

## Kali Linux laptop quickstart

A Kali laptop is a good test gateway if it has **two network interfaces**
(example: Ethernet + Wi‑Fi, or Ethernet + USB-Ethernet).

### A) Protect only the Kali laptop first (fastest)

On Kali:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export LOCKWELL_API=http://<windows-pc-lan-ip>:5000
export LOCKWELL_GUARD_TOKEN=<token from Network Guard>
sudo -E .venv/bin/python -m network_guard.agent --mode enforce --force-simulate
```

Success line:

```text
mode=enforce backend=nftables
```

Check rules:

```bash
sudo nft list table inet lockwell
```

### B) Use Kali as the whole-LAN gateway

1. Interfaces:
   - `eth0` (or similar): cable toward modem/ONT (**WAN**)
   - `wlan0` or second Ethernet: toward your home LAN / AP (**LAN**)
2. List interfaces:

```bash
ip -br link
```

3. Enable forwarding:

```bash
sudo sysctl -w net.ipv4.ip_forward=1
```

4. Basic NAT example (adjust interface names):

```bash
sudo nft add table ip nat
sudo nft 'add chain ip nat postrouting { type nat hook postrouting priority 100 ; }'
sudo nft add rule ip nat postrouting oifname "eth0" masquerade
```

5. Point LAN devices at Kali as their gateway/DNS (or set DHCP on Kali).

6. Run live enforce on the WAN-facing interface:

```bash
export LOCKWELL_API=http://<windows-pc-lan-ip>:5000
export LOCKWELL_GUARD_TOKEN=<token>
sudo -E .venv/bin/python -m network_guard.agent --mode enforce --interface eth0
```

Success line:

```text
mode=enforce backend=nftables live_capture=True
```

### Allow dashboard access from Kali

On the Windows PC firewall, allow inbound TCP 5000 from the Kali LAN IP, and use the Windows LAN IP in `LOCKWELL_API` (not `127.0.0.1` from Kali).

### Cleanup Lockwell nftables

```bash
sudo nft delete table inet lockwell
```

## Recommended path: Linux mini‑PC / Raspberry Pi

### 1. Network wiring

1. Connect modem/ONT → **WAN** port/NIC on the gateway.
2. Connect gateway **LAN** port/NIC → your switch/router-AP (AP in access-point mode if possible).
3. Give the gateway a stable LAN IP (example: `192.168.1.1` as router, or keep your existing router LAN and put the Pi as a firewall bridge — advanced).

Simplest home design:
- Gateway does DHCP/NAT for the LAN, or
- Put gateway in bridged/firewall path with nftables forward filtering.

### 2. Install Lockwell agent on the gateway

Copy the Lockwell `backend/` folder (or full portable package) to the gateway, then:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Keep the dashboard on your Windows PC

Leave http://127.0.0.1:5000 running on the Windows machine (or bind it to your LAN IP).

On the gateway, point at that dashboard:

```bash
export LOCKWELL_API=http://<windows-pc-lan-ip>:5000
export LOCKWELL_GUARD_TOKEN=<token from Network Guard page>
sudo -E .venv/bin/python -m network_guard.agent --mode enforce --interface eth0
```

Replace `eth0` with the WAN-facing interface (`ip -br link` to list).

If the dashboard PC firewall blocks port 5000 from LAN, allow it once for the gateway IP.

### 4. Success checks

On the gateway console you want:

```text
mode=enforce backend=nftables live_capture=True
```

In the Lockwell Network Guard page:
- Node online
- Backend shows `nftables`
- New blocks appear for real sniffed traffic (not only demo IPs)

## Docker gateway agent (optional)

From the project root on the Linux gateway:

```bash
export LOCKWELL_API=http://<dashboard-host>:5000
export LOCKWELL_GUARD_TOKEN=<token>
export LOCKWELL_IFACE=eth0
docker compose -f docker-compose.gateway.yml up --build
```

## Windows-as-gateway (only if you have 2 NICs)

Possible, but more fragile:

1. NIC A: connected toward internet modem
2. NIC B: connected to LAN switch
3. Enable Internet Connection Sharing / routing
4. Run Lockwell enforce on that Windows gateway host

For most homes, a Raspberry Pi/Linux box is less painful.

## Safety

- Start with monitoring first if unsure: `--mode live` (detect only), then switch to `--mode enforce`.
- Don’t lock yourself out: keep a local console session on the gateway.
- Keep a cleanup plan for nftables (`nft delete table inet lockwell`).
- Demo IPs (`192.0.2.x`, `198.51.100.x`, `203.0.113.x`) are documentation ranges; real gateway mode should use live capture without `--force-simulate`.

## What to buy if you have no gateway box yet

- Raspberry Pi 4/5 (or any small x86 mini PC)
- 2 Ethernet interfaces (USB-Ethernet adapter is fine)
- 16GB+ microSD / SSD
- Ubuntu Server or Raspberry Pi OS

Then follow the Linux steps above.
