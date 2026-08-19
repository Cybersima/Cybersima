from __future__ import annotations

import time


class TakeoverGuard:
    """Suspend automated trading on new device, unusual IP, or anomalous configuration."""

    def __init__(self) -> None:
        self.known_devices: set[str] = set()
        self.known_ips: set[str] = set()
        self.baseline_geo: str | None = None
        self.suspended = False
        self.reason = ""

    def observe(
        self,
        device_id: str,
        ip: str,
        geo: str = "unknown",
        config_changed: bool = False,
        api_anomaly: bool = False,
    ) -> bool:
        if not self.known_devices:
            self.known_devices.add(device_id)
            self.known_ips.add(ip)
            self.baseline_geo = geo
            return False
        reasons: list[str] = []
        if device_id not in self.known_devices:
            reasons.append("new device")
        if ip not in self.known_ips:
            reasons.append("unusual IP")
        if self.baseline_geo and geo != self.baseline_geo and geo != "unknown":
            reasons.append("unusual geography")
        if config_changed:
            reasons.append("unauthorized configuration change")
        if api_anomaly:
            reasons.append("abnormal API activity")
        if reasons:
            self.suspended = True
            self.reason = ", ".join(reasons)
            return True
        self.known_devices.add(device_id)
        self.known_ips.add(ip)
        return False

    def reauthenticate(self, device_id: str, ip: str, geo: str = "unknown") -> None:
        self.known_devices.add(device_id)
        self.known_ips.add(ip)
        self.baseline_geo = geo
        self.suspended = False
        self.reason = ""
        _ = time.time()
