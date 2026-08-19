from __future__ import annotations

import shutil
import time
from pathlib import Path

from securetrade.models import HealthReport, KillSource


class HealthMonitor:
    def __init__(self) -> None:
        self.started = time.time()
        self.last_execution_ms = 0.0

    def report(self, feed_status: dict[str, str], stale_feeds: list[str], clock_skew_ms: float = 0.0) -> HealthReport:
        memory_mb = 0.0
        cpu_pct = 0.0
        try:
            import resource

            memory_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        except Exception:
            memory_mb = 0.0
        issues: list[str] = []
        if stale_feeds:
            issues.append("stale price feed")
        disconnected = [name for name, status in feed_status.items() if "error" in status.lower() or status == "stopped"]
        if disconnected:
            issues.append("exchange disconnect")
        usage = shutil.disk_usage(Path.home())
        if usage.free < 50 * 1024 * 1024:
            issues.append("low disk")
        ok = not issues
        return HealthReport(
            ok=ok,
            api_connectivity="ok" if not disconnected else "degraded",
            websocket_latency_ms=self.last_execution_ms,
            clock_skew_ms=clock_skew_ms,
            memory_mb=round(memory_mb, 1),
            cpu_pct=cpu_pct,
            database="ok",
            stale_feeds=stale_feeds,
            exchange_status=dict(feed_status),
            execution_latency_ms=self.last_execution_ms,
            issues=issues,
        )

    def auto_kill_reasons(self, report: HealthReport) -> list[str]:
        reasons = []
        if "stale price feed" in report.issues:
            reasons.append(KillSource.HEALTH.value)
        if "exchange disconnect" in report.issues:
            reasons.append(KillSource.HEALTH.value)
        if report.websocket_latency_ms > 1500:
            reasons.append("excessive latency")
        return reasons
