"""Defensive traffic heuristics for Lockwell Network Guard.

These detectors look for hostile *patterns* (scans, floods, known-bad sources).
They do not implement offense, evasion, or exploit payloads.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from time import time


@dataclass(frozen=True)
class PacketMeta:
    src_ip: str
    dst_ip: str
    dst_port: int
    protocol: str
    syn: bool = False
    rst: bool = False
    size: int = 0


@dataclass(frozen=True)
class Detection:
    category: str
    severity: str
    title: str
    detail: str
    src_ip: str
    dst_ip: str
    dst_port: int
    protocol: str
    should_block: bool


class ThreatDetector:
    """Sliding-window detectors suitable for a home/business edge gateway."""

    def __init__(
        self,
        *,
        scan_ports_threshold: int = 12,
        scan_window_sec: float = 8.0,
        syn_flood_threshold: int = 40,
        syn_flood_window_sec: float = 3.0,
        threat_ips: set[str] | None = None,
    ) -> None:
        self.scan_ports_threshold = scan_ports_threshold
        self.scan_window_sec = scan_window_sec
        self.syn_flood_threshold = syn_flood_threshold
        self.syn_flood_window_sec = syn_flood_window_sec
        self.threat_ips = threat_ips or set()
        self._port_hits: dict[str, deque[tuple[float, int]]] = defaultdict(deque)
        self._syn_hits: dict[str, deque[float]] = defaultdict(deque)
        self._cooldown_until: dict[str, float] = {}

    def observe(self, packet: PacketMeta) -> list[Detection]:
        now = time()
        findings: list[Detection] = []

        if packet.src_ip in self.threat_ips:
            findings.append(
                Detection(
                    category="threat_intel",
                    severity="high",
                    title="Packet from known-bad source",
                    detail=f"{packet.src_ip} matched the local threat-intel blocklist.",
                    src_ip=packet.src_ip,
                    dst_ip=packet.dst_ip,
                    dst_port=packet.dst_port,
                    protocol=packet.protocol,
                    should_block=True,
                )
            )

        if packet.syn and packet.protocol.upper() == "TCP":
            findings.extend(self._check_port_scan(packet, now))
            findings.extend(self._check_syn_flood(packet, now))

        # De-dupe noisy repeats from the same source for a short cooldown.
        filtered: list[Detection] = []
        for item in findings:
            key = f"{item.category}:{item.src_ip}"
            until = self._cooldown_until.get(key, 0.0)
            if now < until:
                continue
            self._cooldown_until[key] = now + 5.0
            filtered.append(item)
        return filtered

    def _check_port_scan(self, packet: PacketMeta, now: float) -> list[Detection]:
        window = self._port_hits[packet.src_ip]
        window.append((now, packet.dst_port))
        while window and now - window[0][0] > self.scan_window_sec:
            window.popleft()
        unique_ports = {port for _, port in window}
        if len(unique_ports) < self.scan_ports_threshold:
            return []
        return [
            Detection(
                category="port_scan",
                severity="high",
                title="Inbound port scan detected",
                detail=(
                    f"{packet.src_ip} probed {len(unique_ports)} ports within "
                    f"{self.scan_window_sec:.0f}s."
                ),
                src_ip=packet.src_ip,
                dst_ip=packet.dst_ip,
                dst_port=packet.dst_port,
                protocol=packet.protocol,
                should_block=True,
            )
        ]

    def _check_syn_flood(self, packet: PacketMeta, now: float) -> list[Detection]:
        window = self._syn_hits[packet.src_ip]
        window.append(now)
        while window and now - window[0] > self.syn_flood_window_sec:
            window.popleft()
        if len(window) < self.syn_flood_threshold:
            return []
        return [
            Detection(
                category="syn_flood",
                severity="high",
                title="SYN flood pattern detected",
                detail=(
                    f"{packet.src_ip} sent {len(window)} TCP SYNs within "
                    f"{self.syn_flood_window_sec:.0f}s."
                ),
                src_ip=packet.src_ip,
                dst_ip=packet.dst_ip,
                dst_port=packet.dst_port,
                protocol=packet.protocol,
                should_block=True,
            )
        ]
