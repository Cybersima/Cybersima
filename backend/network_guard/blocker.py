"""Defensive block enforcement for Lockwell Network Guard.

Backends:
  - Windows Firewall (New-NetFirewallRule) on Windows hosts
  - nftables on Linux gateways
  - simulate fallback when privileges/tools are unavailable
"""

from __future__ import annotations

import ipaddress
import platform
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
    backend: str = "simulate"
    _ready: bool = False

    def ensure_ready(self) -> str:
        if self.mode != "enforce":
            self.backend = "simulate"
            return "simulate"

        system = platform.system().lower()
        if system == "windows":
            return self._ensure_windows()
        return self._ensure_nftables()

    def _ensure_windows(self) -> str:
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-NetFirewallProfile | Out-Null; 'ok'",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                self.mode = "simulate"
                self.backend = "simulate"
                self._ready = False
                return "simulate-fallback-windows-firewall-unavailable"
            self.backend = "windows-firewall"
            self._ready = True
            return "windows-firewall"
        except Exception:
            self.mode = "simulate"
            self.backend = "simulate"
            self._ready = False
            return "simulate-fallback-windows-error"

    def _ensure_nftables(self) -> str:
        if not shutil.which("nft"):
            self.mode = "simulate"
            self.backend = "simulate"
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
            self.backend = "nftables"
            self._ready = True
            return "nftables"
        except Exception:
            self.mode = "simulate"
            self.backend = "simulate"
            self._ready = False
            return "simulate-fallback-nft-error"

    def block(self, ip: str, reason: str) -> BlockDecision:
        try:
            parsed = ipaddress.ip_address(ip)
        except ValueError:
            return BlockDecision(
                ip=ip,
                reason=reason,
                enforced=False,
                backend=self.backend,
                detail="Invalid IP address",
            )

        if parsed.is_loopback or parsed.is_link_local:
            return BlockDecision(
                ip=ip,
                reason=reason,
                enforced=False,
                backend=self.backend,
                detail="Refusing to block loopback/link-local address",
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

        if self.backend == "windows-firewall":
            return self._windows_block(ip, reason)
        return self._nft_block(ip, reason)

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
        if self.backend == "windows-firewall":
            return self._windows_unblock(ip)
        return self._nft_unblock(ip)

    def sync(self, ips: list[str]) -> None:
        for ip in ips:
            if ip not in self.blocked:
                self.block(ip, "synced from controller")

    def _windows_block(self, ip: str, reason: str) -> BlockDecision:
        # Documentation/test ranges are safe for demos; still create real firewall rules.
        inbound = f"Lockwell Block {ip}"
        outbound = f"Lockwell Block {ip} Out"
        script = f"""
$ErrorActionPreference = 'Stop'
$in = '{inbound}'
$out = '{outbound}'
if (-not (Get-NetFirewallRule -DisplayName $in -ErrorAction SilentlyContinue)) {{
  New-NetFirewallRule -DisplayName $in -Direction Inbound -RemoteAddress {ip} -Action Block -Enabled True -Profile Any | Out-Null
}}
if (-not (Get-NetFirewallRule -DisplayName $out -ErrorAction SilentlyContinue)) {{
  New-NetFirewallRule -DisplayName $out -Direction Outbound -RemoteAddress {ip} -Action Block -Enabled True -Profile Any | Out-Null
}}
'ok'
"""
        try:
            self._powershell(script)
            return BlockDecision(
                ip=ip,
                reason=reason,
                enforced=True,
                backend="windows-firewall",
                detail="Windows Firewall inbound/outbound block rule applied",
            )
        except Exception as exc:
            return BlockDecision(
                ip=ip,
                reason=reason,
                enforced=False,
                backend="simulate",
                detail=f"Windows Firewall block failed (run PowerShell as Administrator?): {exc}",
            )

    def _windows_unblock(self, ip: str) -> BlockDecision:
        script = f"""
$ErrorActionPreference = 'SilentlyContinue'
Get-NetFirewallRule -DisplayName 'Lockwell Block {ip}' | Remove-NetFirewallRule
Get-NetFirewallRule -DisplayName 'Lockwell Block {ip} Out' | Remove-NetFirewallRule
'ok'
"""
        try:
            self._powershell(script)
            return BlockDecision(
                ip=ip,
                reason="manual unblock",
                enforced=True,
                backend="windows-firewall",
                detail="Removed Windows Firewall Lockwell rules",
            )
        except Exception as exc:
            return BlockDecision(
                ip=ip,
                reason="manual unblock",
                enforced=False,
                backend="simulate",
                detail=f"Windows Firewall unblock failed: {exc}",
            )

    def _nft_block(self, ip: str, reason: str) -> BlockDecision:
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

    def _nft_unblock(self, ip: str) -> BlockDecision:
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

    @staticmethod
    def _powershell(script: str) -> None:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout or "powershell failed")

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
        if any(
            token in err
            for token in ("file exists", "already exists", "exists", "busy")
        ):
            return
        raise RuntimeError(result.stderr or result.stdout or "nft failed")
