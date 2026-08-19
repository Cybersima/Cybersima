from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

import httpx

from pulsearb.engine.risk import RiskManager
from pulsearb.models import Fill, Opportunity


class Broker:
    async def execute(self, opportunity: Opportunity) -> list[Fill]:
        raise NotImplementedError

    @property
    def paper(self) -> bool:
        return True


class PaperBroker(Broker):
    def __init__(self, risk: RiskManager) -> None:
        self.risk = risk
        self.fills: list[Fill] = []
        self.pnl = 0.0

    @property
    def paper(self) -> bool:
        return True

    async def execute(self, opportunity: Opportunity) -> list[Fill]:
        decision = self.risk.allow(opportunity.notional)
        if not decision.allowed:
            return [
                Fill(
                    venue="paper",
                    symbol="-",
                    side="blocked",
                    qty=0,
                    price=0,
                    notional=0,
                    ts=time.time(),
                    paper=True,
                    opportunity_id=opportunity.id,
                    status="blocked",
                    note=decision.reason,
                )
            ]
        if not opportunity.executable:
            return [
                Fill(
                    venue="alert",
                    symbol="-",
                    side="skip",
                    qty=0,
                    price=0,
                    notional=0,
                    ts=time.time(),
                    paper=True,
                    opportunity_id=opportunity.id,
                    status="alert_only",
                    note="Yahoo/data-only dislocation — not executable",
                )
            ]
        self.risk.on_submit()
        fills: list[Fill] = []
        now = time.time()
        expected = opportunity.notional * (opportunity.net_edge_bps / 10_000)
        for leg in opportunity.legs:
            qty = opportunity.notional / leg.price if leg.price else 0.0
            fills.append(
                Fill(
                    venue=leg.venue,
                    symbol=leg.symbol,
                    side=leg.action,
                    qty=qty,
                    price=leg.price,
                    notional=opportunity.notional,
                    ts=now,
                    paper=True,
                    opportunity_id=opportunity.id,
                    status="filled",
                )
            )
        self.pnl += expected
        self.risk.record_pnl(expected)
        self.risk.on_complete()
        self.fills.extend(fills)
        return fills


class LiveBinanceBroker(Broker):
    """Places Binance spot MARKET orders. Disabled unless live flags are set."""

    def __init__(
        self,
        risk: RiskManager,
        api_key: str,
        api_secret: str,
        rest_url: str,
        paper_fallback: PaperBroker,
    ) -> None:
        self.risk = risk
        self.api_key = api_key
        self.api_secret = api_secret.encode()
        self.rest_url = rest_url.rstrip("/")
        self.paper_fallback = paper_fallback
        self.fills: list[Fill] = []
        self.pnl = 0.0

    @property
    def paper(self) -> bool:
        return False

    def _sign(self, params: dict[str, str | int | float]) -> str:
        query = urlencode(params)
        return hmac.new(self.api_secret, query.encode(), hashlib.sha256).hexdigest()

    async def execute(self, opportunity: Opportunity) -> list[Fill]:
        decision = self.risk.allow(opportunity.notional)
        if not decision.allowed or not opportunity.executable:
            return await self.paper_fallback.execute(opportunity)
        binance_legs = [leg for leg in opportunity.legs if leg.venue == "binance" and leg.executable]
        if len(binance_legs) != len(opportunity.legs):
            return await self.paper_fallback.execute(opportunity)
        self.risk.on_submit()
        fills: list[Fill] = []
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                for leg in binance_legs:
                    side = "BUY" if leg.action == "buy" else "SELL"
                    params: dict[str, str | int | float] = {
                        "symbol": leg.symbol,
                        "side": side,
                        "type": "MARKET",
                        "quoteOrderQty": round(opportunity.notional, 2),
                        "timestamp": int(time.time() * 1000),
                        "recvWindow": 5000,
                    }
                    params["signature"] = self._sign(params)
                    response = await client.post(
                        f"{self.rest_url}/api/v3/order",
                        params=params,
                        headers={"X-MBX-APIKEY": self.api_key},
                    )
                    payload = response.json()
                    fills.append(
                        Fill(
                            venue="binance",
                            symbol=leg.symbol,
                            side=leg.action,
                            qty=float(payload.get("executedQty") or 0),
                            price=leg.price,
                            notional=opportunity.notional,
                            ts=time.time(),
                            paper=False,
                            opportunity_id=opportunity.id,
                            status="filled" if response.status_code == 200 else "error",
                            note=str(payload)[:240],
                        )
                    )
                    if response.status_code != 200:
                        break
        finally:
            self.risk.on_complete()
        self.fills.extend(fills)
        return fills


class LiveRouter(Broker):
    """Send live orders only when every executable leg is on one armed venue."""

    PAPER_CROSS_NOTE = (
        "paper: live orders only when every leg is on Coinbase. "
        "Cross-venue needs funds parked on both exchanges — that is not instant."
    )

    def __init__(
        self,
        paper_fallback: PaperBroker,
        coinbase: Broker | None = None,
        binance: Broker | None = None,
    ) -> None:
        self.paper_fallback = paper_fallback
        self.coinbase = coinbase
        self.binance = binance
        self.fills: list[Fill] = []

    @property
    def paper(self) -> bool:
        return False

    @property
    def live_pnl(self) -> float:
        total = 0.0
        if self.coinbase is not None:
            total += float(getattr(self.coinbase, "pnl", 0.0))
        if self.binance is not None:
            total += float(getattr(self.binance, "pnl", 0.0))
        return total

    @property
    def balances(self) -> dict[str, float]:
        if self.coinbase is not None:
            return dict(getattr(self.coinbase, "balances", {}) or {})
        return {}

    @property
    def live_venues(self) -> list[str]:
        names: list[str] = []
        if self.coinbase is not None:
            names.append("coinbase")
        if self.binance is not None:
            names.append("binance")
        return names

    async def execute(self, opportunity: Opportunity) -> list[Fill]:
        venues = {leg.venue for leg in opportunity.legs}
        if venues == {"coinbase"} and self.coinbase is not None:
            fills = await self.coinbase.execute(opportunity)
        elif venues == {"binance"} and self.binance is not None:
            fills = await self.binance.execute(opportunity)
        else:
            fills = await self.paper_fallback.execute(opportunity)
            for fill in fills:
                if fill.status == "filled":
                    fill.note = (f"{fill.note} {self.PAPER_CROSS_NOTE}").strip()
        self.fills.extend(fills)
        return fills
