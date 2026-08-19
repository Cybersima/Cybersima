from __future__ import annotations

import time
from dataclasses import dataclass, field

from securetrade.models import KillSource


@dataclass
class RiskDecision:
    allowed: bool
    reason: str = ""
    source: str = "risk"


@dataclass
class RiskManager:
    max_notional_usdt: float = 250
    max_open_orders: int = 4
    daily_loss_limit_usdt: float = 150
    cooldown_seconds: float = 8
    max_drawdown_pct: float = 5.0
    killed: bool = False
    kill_source: str | None = None
    realized_pnl: float = 0.0
    open_orders: int = 0
    last_order_ts: float = 0.0
    peak_equity: float = 0.0
    day_key: str = field(default_factory=lambda: time.strftime("%Y-%m-%d"))
    admin_locked: bool = False

    def kill(self, source: KillSource | str = KillSource.CUSTOMER) -> None:
        self.killed = True
        self.kill_source = source.value if isinstance(source, KillSource) else str(source)

    def resume(self, source: KillSource | str = KillSource.CUSTOMER) -> bool:
        requested = source.value if isinstance(source, KillSource) else str(source)
        if self.admin_locked and requested != KillSource.ADMIN.value:
            return False
        self.killed = False
        self.kill_source = None
        return True

    def admin_lock(self) -> None:
        self.admin_locked = True
        self.kill(KillSource.ADMIN)

    def _roll_day(self) -> None:
        today = time.strftime("%Y-%m-%d")
        if today != self.day_key:
            self.day_key = today
            self.realized_pnl = 0.0

    def record_pnl(self, pnl: float, equity: float | None = None) -> None:
        self._roll_day()
        self.realized_pnl += pnl
        if equity is not None:
            self.peak_equity = max(self.peak_equity, equity)

    def allow(self, notional: float, equity: float | None = None) -> RiskDecision:
        self._roll_day()
        if self.killed:
            return RiskDecision(False, f"kill switch is on ({self.kill_source or 'customer'})", "kill")
        if notional > self.max_notional_usdt:
            return RiskDecision(False, "notional exceeds cap")
        if self.open_orders >= self.max_open_orders:
            return RiskDecision(False, "too many open orders")
        if self.realized_pnl <= -abs(self.daily_loss_limit_usdt):
            self.kill(KillSource.RISK)
            return RiskDecision(False, "daily loss limit reached", "risk")
        if equity is not None and self.peak_equity > 0:
            drawdown = (self.peak_equity - equity) / self.peak_equity * 100
            if drawdown >= self.max_drawdown_pct:
                self.kill(KillSource.RISK)
                return RiskDecision(False, "max drawdown reached", "risk")
        if time.time() - self.last_order_ts < self.cooldown_seconds:
            return RiskDecision(False, "cooldown")
        return RiskDecision(True)

    def on_submit(self) -> None:
        self.open_orders += 1
        self.last_order_ts = time.time()

    def on_complete(self) -> None:
        self.open_orders = max(0, self.open_orders - 1)
