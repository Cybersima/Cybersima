"""Defensive block enforcement for Lockwell Network Guard.

Uses nftables when available and permitted; otherwise records intended drops
in simulation mode so the dashboard still shows protection decisions.
"""

from __future__ import annotations

import ipaddress
import shutil
import subprocess
from dataclasses import dataclass, field


@dataclass
class BlockDecision:
    ip: str
    reason: str
    enforced: bool
    backend: str
    detail: str


@dataclass
class PacketBlocker:
    mode: str = "simulate"  # simulate | enforce
    table_family: str = "inet"
    table_name: str = "lockwell"
    set_name: str = "bad_actors"
    blocked: set[str] = field(default_factory=set)
    _ready: bool = False

    def ensure_ready(self) -> str:
        if self.mode != "enforce":
            return "simulate"
        if not shutil.which("nft"):
            self.mode = "simulate"
            return "simulate-fallback-no-nft"
        script = f"""
add table {self.table_family} {self.table_name}
add set {self.table_family} {self.table_name} {self.set_name} {{ type ipv4_addr; flags interval; }}
add chain {self.table_family} {self.table_name} input {{ type filter hook input priority 0; policy accept; }}
add chain {self.table_family} {self.table_name} forward {{ type filter hook forward priority 0; policy accept; }}
add rule {self.table_family} {self.table_name} input ip saddr @{self.set_name} drop
add rule {self.table_family} {self.table_name} forward ip saddr @{self.set_name} drop
"""
        try:
            self._nft_script(script)
            self._ready = True
            return "nftables"
        except Exception:
            self.mode = "simulate"
            self._ready = False
            return "simulate-fallback-nft-error"

    def block(self, ip: str, reason: str) -> BlockDecision:
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            return BlockDecision(
                ip=ip,
                reason=reason,
                enforced=False,
                backend=self.mode,
                detail="Invalid IP address",
            )

        self.blocked.add(ip)
        if self.mode != "enforce" or not self._ready:
            return BlockDecision(
                ip=ip,
                reason=reason,
                enforced=False,
                backend="simulate",
                detail="Recorded block decision (simulation mode)",
            )

        try:
            self._nft_script(
                f"add element {self.table_family} {self.table_name} "
                f"{self.set_name} {{ {ip} }}"
            )
            return BlockDecision(
                ip=ip,
                reason=reason,
                enforced=True,
                backend="nftables",
                detail="Source dropped on input/forward hooks",
            )
        except Exception as exc:
            return BlockDecision(
                ip=ip,
                reason=reason,
                enforced=False,
                backend="simulate",
                detail=f"nftables add failed: {exc}",
            )

    def unblock(self, ip: str) -> BlockDecision:
        self.blocked.discard(ip)
        if self.mode != "enforce" or not self._ready:
            return BlockDecision(
                ip=ip,
                reason="manual unblock",
                enforced=False,
                backend="simulate",
                detail="Removed from simulated blocklist",
            )
        try:
            self._nft_script(
                f"delete element {self.table_family} {self.table_name} "
                f"{self.set_name} {{ {ip} }}"
            )
            return BlockDecision(
                ip=ip,
                reason="manual unblock",
                enforced=True,
                backend="nftables",
                detail="Removed from nftables set",
            )
        except Exception as exc:
            return BlockDecision(
                ip=ip,
                reason="manual unblock",
                enforced=False,
                backend="simulate",
                detail=f"nftables delete failed: {exc}",
            )

    def sync(self, ips: list[str]) -> None:
        for ip in ips:
            if ip not in self.blocked:
                self.block(ip, "synced from controller")

    def _nft_script(self, script: str) -> None:
        result = subprocess.run(
            ["nft", "-f", "-"],
            input=script,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return
        err = (result.stderr or result.stdout or "").lower()
        # Idempotent setup: ignore objects that already exist.
        if any(
            token in err
            for token in ("file exists", "already exists", "exists", "busy")
        ):
            return
        raise RuntimeError(result.stderr or result.stdout or "nft failed")
