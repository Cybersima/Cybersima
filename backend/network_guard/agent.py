#!/usr/bin/env python3
"""Lockwell Network Guard edge agent.

Deploy this on the gateway / firewall host that sits in front of the LAN so
hostile packets can be dropped before they forward into home or business hosts.

Modes:
  simulate — demo metadata stream (safe default, no privileges required)
  live     — sniff local interface when scapy + permissions allow
  enforce  — live/sim detections also push drops through nftables when possible
"""

from __future__ import annotations

import argparse
import os
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
            "or use --mode simulate."
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

            sniff(
                iface=interface or None,
                prn=_handle,
                store=False,
                timeout=1,
                quiet=True,
            )
            yield from batch

    return _capture()


def run_agent(args: argparse.Namespace) -> None:
    client = GuardClient(args.api, args.token)
    blocker = PacketBlocker(mode="enforce" if args.mode == "enforce" else "simulate")
    backend = blocker.ensure_ready()
    detector = ThreatDetector(threat_ips=set(DEMO_THREAT_INTEL))

    packets_seen = 0
    packets_blocked = 0
    source = (
        sniff_live(args.interface)
        if args.mode in {"live", "enforce"} and not args.force_simulate
        else iter_demo_packets()
    )

    print(
        f"Lockwell Network Guard starting mode={args.mode} backend={backend}",
        flush=True,
    )

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
                action = "blocked" if decision.enforced or decision.backend == "simulate" else "logged"
                if action == "blocked":
                    packets_blocked += 1

            pending.append(
                {
                    "category": detection.category,
                    "severity": detection.severity,
                    "title": detection.title,
                    "detail": detection.detail
                    + (
                        f" [{decision.detail}]"
                        if decision is not None
                        else ""
                    ),
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

        if args.mode == "simulate" or args.force_simulate:
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
        help="Even in live/enforce, use the safe demo packet stream",
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
            print(f"{exc} Falling back to simulate.", flush=True)
            args.force_simulate = True
            args.mode = "simulate"
    run_agent(args)


if __name__ == "__main__":
    main()
