# Lockwell Network Guard

## Is edge packet blocking possible?

Yes — if Lockwell runs **on the network path**.

```
Internet ──► Lockwell Network Guard (gateway/firewall) ──► Home/Business LAN
                         │
                         ▼
                 Lockwell dashboard / API
```

A browser dashboard alone cannot stop packets before they enter the LAN. The
edge agent can, because it sits on the router/firewall host and applies drops
on `input` / `forward` hooks.

## Detection (defensive)

- Port-scan bursts (many destination ports from one source)
- SYN-flood style bursts
- Local threat-intel source matches

## Enforcement

| Mode | Behavior |
| --- | --- |
| `simulate` | Safe demo stream + recorded block decisions |
| `live` | Sniff interface when scapy/permissions allow |
| `enforce` | Detections also push sources into an nftables set |

## Run

1. Register in the Lockwell app and open **Network Guard**.
2. Copy the node token.
3. On the gateway host:

```bash
cd backend
source .venv/bin/activate
export LOCKWELL_API=http://<controller-host>:5000
export LOCKWELL_GUARD_TOKEN=<token>
python -m network_guard.agent --mode simulate
# production-style:
# sudo python -m network_guard.agent --mode enforce --interface eth0
```
