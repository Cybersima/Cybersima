from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RiskDecision:
    allowed: bool
    reason: str = ""


@dataclass
class RiskManager:
    max_notional_usdt: float = 250
    max_open_orders: int = 4
    daily_loss_limit_usdt: float = 100
    cooldown_seconds: float = 8
    killed: bool = False
    realized_pnl: float = 0.0
    open_orders: int = 0
    last_order_ts: float = 0.0
    day_key: str = field(default_factory=lambda: time.strftime("%Y-%m-%d"))

    def kill(self) -> None:
        self.killed = True

    def resume(self) -> None:
        self.killed = False

    def _roll_day(self) -> None:
        today = time.strftime("%Y-%m-%d")
        if today != self.day_key:
            self.day_key = today
            self.realized_pnl = 0.0

    def record_pnl(self, pnl: float) -> None:
        self._roll_day()
        self.realized_pnl += pnl

    def allow(self, notional: float) -> RiskDecision:
        self._roll_day()
        if self.killed:
            return RiskDecision(False, "kill switch is on")
        if notional > self.max_notional_usdt:
            return RiskDecision(False, "notional exceeds cap")
        if self.open_orders >= self.max_open_orders:
            return RiskDecision(False, "too many open orders")
        if self.realized_pnl <= -abs(self.daily_loss_limit_usdt):
            return RiskDecision(False, "daily loss limit reached")
        if time.time() - self.last_order_ts < self.cooldown_seconds:
            return RiskDecision(False, "cooldown")
        return RiskDecision(True)

    def on_submit(self) -> None:
        self.open_orders += 1
        self.last_order_ts = time.time()

    def on_complete(self) -> None:
        self.open_orders = max(0, self.open_orders - 1)
