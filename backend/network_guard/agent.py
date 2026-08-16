#!/usr/bin/env python3
"""Lockwell Network Guard edge/host agent.

Deploy paths:
  1) Windows host enforce — protects THIS computer via Windows Firewall
  2) Linux gateway enforce — drops hostile sources before LAN forward (nftables)

Modes:
  simulate — demo metadata stream (safe default)
  live     — sniff interface when scapy + permissions allow
  enforce  — detections also apply real firewall drops when possible

Tip for first real blocks on Windows:
  --mode enforce --force-simulate
uses demo detections but writes real Windows Firewall rules for the demo IPs.
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

import requests

# Allow `python -m network_guard.agent` from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from network_guard.blocker import PacketBlocker
from network_guard.detector import PacketMeta, ThreatDetector
from network_guard.simulator import DEMO_THREAT_INTEL, iter_demo_packets


class GuardClient:
    def __init__(self, api_base: str, token: str) -> None:
        self.api_base = api_base.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"X-Guard-Token": token})

    def heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            f"{self.api_base}/api/network/agent/heartbeat", json=payload, timeout=10
        )
        response.raise_for_status()
        return response.json()

    def push_events(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        response = self.session.post(
            f"{self.api_base}/api/network/agent/events",
            json={"events": events},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def pull_blocklist(self) -> list[str]:
        response = self.session.get(
            f"{self.api_base}/api/network/agent/blocklist", timeout=10
        )
        response.raise_for_status()
        return [item["ip"] for item in response.json().get("blocks", [])]


def sniff_live(interface: str | None):
    try:
        from scapy.all import IP, TCP, sniff  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Live mode requires scapy. Install with `pip install scapy` "
            "or use --mode enforce --force-simulate."
        ) from exc

    def _capture():
        while True:
            batch: list[PacketMeta] = []

            def _handle(pkt) -> None:
                if IP not in pkt:
                    return
                ip = pkt[IP]
                syn = bool(TCP in pkt and pkt[TCP].flags & 0x02)
                dport = int(pkt[TCP].dport) if TCP in pkt else 0
                proto = "TCP" if TCP in pkt else "IP"
                batch.append(
                    PacketMeta(
                        src_ip=ip.src,
                        dst_ip=ip.dst,
                        dst_port=dport,
                        protocol=proto,
                        syn=syn,
                        size=len(pkt),
                    )
                )

            kwargs = {
                "prn": _handle,
                "store": False,
                "timeout": 1,
            }
            if interface:
                kwargs["iface"] = interface
            try:
                sniff(**kwargs, quiet=True)
            except TypeError:
                sniff(**kwargs)
            yield from batch

    return _capture()


def run_agent(args: argparse.Namespace) -> None:
    client = GuardClient(args.api, args.token)
    blocker = PacketBlocker(mode="enforce" if args.mode == "enforce" else "simulate")
    backend = blocker.ensure_ready()
    detector = ThreatDetector(threat_ips=set(DEMO_THREAT_INTEL))

    use_live = args.mode in {"live", "enforce"} and not args.force_simulate
    source = sniff_live(args.interface) if use_live else iter_demo_packets()

    print(
        f"Lockwell Network Guard starting mode={args.mode} backend={backend} "
        f"os={platform.system()} live_capture={use_live}",
        flush=True,
    )
    if getattr(blocker, "_last_error", ""):
        print(f"backend detail: {blocker._last_error}", flush=True)
    if args.mode != "enforce":
        print(
            "NOTE: mode is not enforce. Use --mode enforce to write real firewall rules.",
            flush=True,
        )
    if args.mode == "enforce" and backend.startswith("simulate"):
        print(
            "WARNING: enforce requested but firewall backend unavailable. "
            "On Windows: 1) enable Windows Firewall, 2) run PowerShell as Administrator, "
            "3) make sure you have the latest Lockwell files with Windows Firewall support.",
            flush=True,
        )

    packets_seen = 0
    packets_blocked = 0
    pending: list[dict[str, Any]] = []
    last_heartbeat = 0.0
    last_sync = 0.0

    for packet in source:
        packets_seen += 1
        detections = detector.observe(packet)
        for detection in detections:
            decision = None
            action = "logged"
            if detection.should_block and args.auto_block:
                decision = blocker.block(detection.src_ip, detection.title)
                if decision.enforced or decision.backend == "simulate":
                    action = "blocked"
                if decision.enforced or decision.backend == "simulate":
                    packets_blocked += 1

            pending.append(
                {
                    "category": detection.category,
                    "severity": detection.severity,
                    "title": detection.title,
                    "detail": detection.detail
                    + (f" [{decision.detail}]" if decision is not None else ""),
                    "srcIp": detection.src_ip,
                    "dstIp": detection.dst_ip,
                    "dstPort": detection.dst_port,
                    "protocol": detection.protocol,
                    "action": action,
                }
            )

        now = time.time()
        if pending and (len(pending) >= 5 or now - last_heartbeat > args.interval):
            try:
                client.push_events(pending)
                pending.clear()
            except Exception as exc:
                print(f"event push failed: {exc}", flush=True)

        if now - last_heartbeat >= args.interval:
            try:
                client.heartbeat(
                    {
                        "packetsSeen": packets_seen,
                        "packetsBlocked": packets_blocked,
                        "mode": args.mode,
                        "backend": backend,
                        "interface": args.interface or "any",
                        "status": "online",
                    }
                )
                last_heartbeat = now
            except Exception as exc:
                print(f"heartbeat failed: {exc}", flush=True)

        if now - last_sync >= max(args.interval, 5):
            try:
                blocker.sync(client.pull_blocklist())
                last_sync = now
            except Exception as exc:
                print(f"blocklist sync failed: {exc}", flush=True)

        if not use_live:
            time.sleep(args.demo_delay)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lockwell Network Guard agent")
    parser.add_argument(
        "--api",
        default=os.environ.get("LOCKWELL_API", "http://127.0.0.1:5000"),
        help="Lockwell API base URL",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("LOCKWELL_GUARD_TOKEN", ""),
        help="Guard node token from the Lockwell dashboard",
    )
    parser.add_argument(
        "--mode",
        choices=["simulate", "live", "enforce"],
        default=os.environ.get("LOCKWELL_GUARD_MODE", "simulate"),
    )
    parser.add_argument("--interface", default=os.environ.get("LOCKWELL_IFACE"))
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--demo-delay", type=float, default=0.05)
    parser.add_argument("--auto-block", action="store_true", default=True)
    parser.add_argument("--no-auto-block", action="store_false", dest="auto_block")
    parser.add_argument(
        "--force-simulate",
        action="store_true",
        help="Use demo packet stream even in live/enforce (still applies real blocks in enforce)",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not args.token:
        print("Missing --token / LOCKWELL_GUARD_TOKEN", file=sys.stderr)
        sys.exit(2)
    if args.mode in {"live", "enforce"} and not args.force_simulate:
        try:
            run_agent(args)
            return
        except RuntimeError as exc:
            print(f"{exc} Falling back to demo packet stream with current mode.", flush=True)
            args.force_simulate = True
    run_agent(args)


if __name__ == "__main__":
    main()
