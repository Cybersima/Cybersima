"""Synthetic hostile traffic for Network Guard demos.

Emits packet *metadata* only — it does not send attack traffic to real hosts.
"""

from __future__ import annotations

import itertools
import random
from typing import Iterator

from .detector import PacketMeta

DEMO_BAD_ACTORS = [
    "203.0.113.50",
    "198.51.100.66",
    "192.0.2.88",
]

DEMO_THREAT_INTEL = {
    "198.51.100.66",
}


def iter_demo_packets() -> Iterator[PacketMeta]:
    """Yield repeating demo patterns: port scan, flood, threat-intel hit, benign."""

    scanner = DEMO_BAD_ACTORS[0]
    flooder = DEMO_BAD_ACTORS[2]
    intel = DEMO_BAD_ACTORS[1]
    target = "192.168.1.1"
    port_cycle = itertools.cycle(range(20, 120))

    while True:
        kind = random.choices(
            population=["scan", "flood", "intel", "benign"],
            weights=[0.35, 0.25, 0.15, 0.25],
            k=1,
        )[0]

        if kind == "scan":
            for _ in range(16):
                yield PacketMeta(
                    src_ip=scanner,
                    dst_ip=target,
                    dst_port=next(port_cycle),
                    protocol="TCP",
                    syn=True,
                    size=60,
                )
        elif kind == "flood":
            for _ in range(48):
                yield PacketMeta(
                    src_ip=flooder,
                    dst_ip=target,
                    dst_port=443,
                    protocol="TCP",
                    syn=True,
                    size=60,
                )
        elif kind == "intel":
            yield PacketMeta(
                src_ip=intel,
                dst_ip=target,
                dst_port=22,
                protocol="TCP",
                syn=True,
                size=60,
            )
        else:
            yield PacketMeta(
                src_ip="8.8.8.8",
                dst_ip=target,
                dst_port=443,
                protocol="UDP",
                syn=False,
                size=120,
            )
