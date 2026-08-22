from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

import httpx

from pulsearb.engine.money import CONVERT_TO_USD, STABLE, paper_tap_pnl
from pulsearb.engine.risk import RiskManager
from pulsearb.models import Fill, Opportunity
from pulsearb.symbols import split_pair


def _usd_price_from_opportunity(opportunity: Opportunity, asset: str) -> float | None:
    wanted = str(asset or "").upper()
    for leg in opportunity.legs:
        if not leg.price:
            continue
        try:
            base, quote = split_pair(leg.symbol)
        except ValueError:
            continue
        if base == wanted and quote in STABLE:
            return float(leg.price)
        if quote == wanted and base in STABLE:
            return 1.0 / float(leg.price)
    return None


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
        start_quote = ""
        try:
            if opportunity.legs:
                _base0, start_quote = split_pair(opportunity.legs[0].symbol)
        except ValueError:
            start_quote = ""
        chained = bool(
            opportunity.legs
            and opportunity.legs[0].action == "buy"
            and start_quote in STABLE
        )
        if chained:
            fills = self._chain_fills(opportunity, now, start_quote=start_quote)
            realized = paper_tap_pnl(fills, opportunity.notional, start_quote=start_quote or "USD")
        else:
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
                        note="paper fill",
                    )
                )
            realized = expected
        self.pnl += realized
        self.risk.record_pnl(realized)
        self.risk.on_complete()
        self.fills.extend(fills)
        return fills

    def _chain_fills(self, opportunity: Opportunity, now: float, start_quote: str = "USD") -> list[Fill]:
        fills: list[Fill] = []
        cash = start_quote if start_quote in STABLE else "USD"
        pocket: dict[str, float] = {cash: float(opportunity.notional)}
        for leg in opportunity.legs:
            try:
                base, quote = split_pair(leg.symbol)
            except ValueError:
                base, quote = leg.symbol.upper(), "USD"
            if leg.action == "buy":
                spend = float(pocket.get(quote, 0.0) or 0.0)
                if spend <= 0:
                    fills.append(
                        Fill(
                            venue=leg.venue,
                            symbol=leg.symbol,
                            side="buy",
                            qty=0,
                            price=leg.price,
                            notional=opportunity.notional,
                            ts=now,
                            paper=True,
                            opportunity_id=opportunity.id,
                            status="blocked",
                            note=f"paper: no {quote} in this tap to buy {leg.symbol}",
                        )
                    )
                    break
                qty = spend / leg.price if leg.price else 0.0
                pocket[quote] = max(0.0, pocket.get(quote, 0.0) - spend)
                pocket[base] = pocket.get(base, 0.0) + qty
                fills.append(
                    Fill(
                        venue=leg.venue,
                        symbol=leg.symbol,
                        side="buy",
                        qty=qty,
                        price=leg.price,
                        notional=spend,
                        ts=now,
                        paper=True,
                        opportunity_id=opportunity.id,
                        status="filled",
                        note="paper fill",
                    )
                )
            else:
                qty = float(pocket.get(base, 0.0) or 0.0)
                proceeds = qty * leg.price if leg.price else 0.0
                pocket[base] = 0.0
                pocket[quote] = pocket.get(quote, 0.0) + proceeds
                fills.append(
                    Fill(
                        venue=leg.venue,
                        symbol=leg.symbol,
                        side="sell",
                        qty=qty,
                        price=leg.price,
                        notional=proceeds,
                        ts=now,
                        paper=True,
                        opportunity_id=opportunity.id,
                        status="filled",
                        note="paper fill",
                    )
                )
        for asset in CONVERT_TO_USD:
            qty = float(pocket.get(asset, 0.0) or 0.0)
            if qty < 0.01:
                continue
            fills.append(
                Fill(
                    venue="coinbase",
                    symbol=f"{asset}-USD",
                    side="sell",
                    qty=qty,
                    price=1.0,
                    notional=qty,
                    ts=now,
                    paper=True,
                    opportunity_id=opportunity.id,
                    status="filled",
                    note="paper flatten to USD",
                )
            )
            pocket[asset] = 0.0
            pocket["USD"] = pocket.get("USD", 0.0) + qty
        for asset, qty in list(pocket.items()):
            if asset in STABLE or qty <= 1e-8:
                continue
            px = _usd_price_from_opportunity(opportunity, asset)
            if px is None or px <= 0:
                continue
            usd = qty * px
            fills.append(
                Fill(
                    venue=opportunity.legs[-1].venue if opportunity.legs else "paper",
                    symbol=f"{asset}-USD",
                    side="sell",
                    qty=qty,
                    price=px,
                    notional=usd,
                    ts=now,
                    paper=True,
                    opportunity_id=opportunity.id,
                    status="filled",
                    note="paper mark leftover to USD",
                )
            )
            pocket[asset] = 0.0
            pocket["USD"] = pocket.get("USD", 0.0) + usd
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
    """Send live orders only when every executable leg is on the armed live venue."""

    PAPER_CROSS_NOTE = (
        "That gap is two exchanges. Live cannot move coins between them, "
        "so it would mean holding. Live taps only one exchange at a time, "
        "buying with USD and selling back toward USD."
    )

    def __init__(
        self,
        paper_fallback: PaperBroker,
        coinbase: Broker | None = None,
        kraken: Broker | None = None,
        binance: Broker | None = None,
        *,
        armed: bool = True,
        live_venue: str = "coinbase",
    ) -> None:
        self.paper_fallback = paper_fallback
        self.coinbase = coinbase
        self.kraken = kraken
        self.binance = binance
        self.armed = armed
        self.live_venue = str(live_venue or "coinbase").strip().lower()
        self.fills: list[Fill] = []

    @property
    def paper(self) -> bool:
        return not self.armed

    def _broker(self, venue: str) -> Broker | None:
        if venue == "coinbase":
            return self.coinbase
        if venue == "kraken":
            return self.kraken
        if venue == "binance":
            return self.binance
        return None

    @property
    def live_pnl(self) -> float:
        total = 0.0
        for name in ("coinbase", "kraken", "binance"):
            broker = self._broker(name)
            if broker is not None:
                total += float(getattr(broker, "pnl", 0.0))
        return total

    @property
    def balances(self) -> dict[str, float]:
        broker = self._broker(self.live_venue) or self.coinbase or self.kraken
        if broker is not None:
            return dict(getattr(broker, "balances", {}) or {})
        return {}

    @property
    def live_venues(self) -> list[str]:
        names: list[str] = []
        if self.coinbase is not None:
            names.append("coinbase")
        if self.kraken is not None:
            names.append("kraken")
        if self.binance is not None:
            names.append("binance")
        return names

    async def execute(self, opportunity: Opportunity) -> list[Fill]:
        if not self.armed:
            fills = await self.paper_fallback.execute(opportunity)
            self.fills.extend(fills)
            return fills
        venues = {leg.venue for leg in opportunity.legs}
        wanted = self.live_venue
        broker = self._broker(wanted)
        if venues == {wanted} and broker is not None:
            fills = await broker.execute(opportunity)
        else:
            fills = [
                Fill(
                    venue="live",
                    symbol="-",
                    side="blocked",
                    qty=0,
                    price=0,
                    notional=0,
                    ts=time.time(),
                    paper=False,
                    opportunity_id=opportunity.id,
                    status="blocked",
                    note=self.PAPER_CROSS_NOTE,
                )
            ]
        self.fills.extend(fills)
        return fills
