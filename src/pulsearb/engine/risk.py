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
    min_notional_usdt: float = 1
    max_open_orders: int = 4
    daily_loss_limit_usdt: float = 100
    cooldown_seconds: float = 8
    live_budget_usdt: float = 0.0
    live_spent: float = 0.0
    killed: bool = False
    realized_pnl: float = 0.0
    open_orders: int = 0
    last_order_ts: float = 0.0
    day_key: str = field(default_factory=lambda: time.strftime("%Y-%m-%d"))

    def kill(self) -> None:
        self.killed = True

    def resume(self) -> None:
        self.killed = False

    def remaining_budget(self) -> float | None:
        if self.live_budget_usdt <= 0:
            return None
        return round(max(0.0, self.live_budget_usdt - self.live_spent), 2)

    def taps_left(self, notional: float) -> int | None:
        left = self.remaining_budget()
        if left is None:
            return None
        if notional <= 0:
            return 0
        return int(left // notional)

    def reserve_live(self, notional: float) -> None:
        if self.live_budget_usdt > 0:
            self.live_spent = round(self.live_spent + float(notional), 2)

    def release_live(self, notional: float) -> None:
        if self.live_budget_usdt > 0:
            self.live_spent = round(max(0.0, self.live_spent - float(notional)), 2)

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
        if notional + 1e-9 < self.min_notional_usdt:
            return RiskDecision(False, f"size below ${self.min_notional_usdt:.0f} minimum")
        if notional > self.max_notional_usdt:
            return RiskDecision(False, "notional exceeds cap")
        left = self.remaining_budget()
        if left is not None and self.live_spent + notional > self.live_budget_usdt + 1e-9:
            return RiskDecision(False, f"live budget ${left:.2f} left of ${self.live_budget_usdt:.0f}")
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
