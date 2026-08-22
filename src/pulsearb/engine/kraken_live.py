from __future__ import annotations

import math
import time
from typing import Any

import httpx

from pulsearb.engine.broker import Broker, PaperBroker
from pulsearb.engine.kraken_auth import kraken_body, kraken_signature
from pulsearb.engine.money import CONVERT_TO_USD, STABLE, cash_pnl
from pulsearb.engine.risk import RiskManager
from pulsearb.feeds.headers import HTTP_HEADERS
from pulsearb.models import Fill, Opportunity
from pulsearb.symbols import normalize_asset, to_native_symbol, split_pair


KRAKEN_ASSETS = {
    "ZUSD": "USD",
    "USD": "USD",
    "USDC": "USDC",
    "USDT": "USDT",
    "ZUSDT": "USDT",
    "XXBT": "BTC",
    "XBT": "BTC",
    "XETH": "ETH",
    "XLTC": "LTC",
    "XXRP": "XRP",
    "XXLM": "XLM",
}


def from_kraken_asset(code: str) -> str:
    text = str(code or "").upper()
    if text in KRAKEN_ASSETS:
        return KRAKEN_ASSETS[text]
    return normalize_asset(text)


# Conservative Kraken market-order floors (base asset). BTC 0.0001 means a
# $10 tap fails when BTC is above $100k.
KRAKEN_MIN_BASE = {
    "BTC": 0.0001,
    "ETH": 0.002,
    "SOL": 0.02,
    "XRP": 5.0,
    "LTC": 0.02,
    "ADA": 10.0,
    "DOGE": 50.0,
    "LINK": 0.2,
    "AVAX": 0.15,
    "DOT": 0.6,
    "UNI": 0.25,
    "AAVE": 0.02,
}


def explain_kraken_order_error(err: str) -> str:
    text = str(err)
    lower = text.lower()
    if "volume" in lower and ("minimum" in lower or "min" in lower):
        return (
            "Kraken rejected the size — this pair’s minimum is larger than the tap. "
            "BTC often needs more than $10. Raise the tap or pick a cheaper coin."
        )
    if "insufficient" in lower or "funds" in lower:
        return "Kraken said insufficient funds. Live starts with USD, not USDC."
    if "invalid key" in lower or "invalid signature" in lower:
        return (
            "Kraken rejected the key. Recheck keys\\kraken.json "
            "(API Key + Private Key, Query Funds + Create & Modify Orders)."
        )
    if "permission" in lower:
        return "Kraken key is missing Create & Modify Orders."
    return text[:240]


def kraken_min_notional(base: str, price: float) -> float:
    floor = float(KRAKEN_MIN_BASE.get(str(base or "").upper(), 0.0) or 0.0)
    if floor <= 0 or price <= 0:
        return 0.0
    return floor * float(price)


def _floor_qty(qty: float, digits: int = 8) -> float:
    if qty <= 0:
        return 0.0
    scale = 10 ** digits
    return math.floor((qty + 1e-15) * scale) / scale


class LiveKrakenBroker(Broker):
    """Places Kraken market orders. Same-venue USD-start round-trips only."""

    def __init__(
        self,
        risk: RiskManager,
        api_key: str,
        api_secret: str,
        paper_fallback: PaperBroker,
        rest_url: str = "https://api.kraken.com",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.risk = risk
        self.api_key = api_key
        self.api_secret = api_secret
        self.paper_fallback = paper_fallback
        self.rest_url = rest_url.rstrip("/")
        self.fills: list[Fill] = []
        self.pnl = 0.0
        self.balances: dict[str, float] = {}
        self.status = "idle"
        self._client = client
        self._nonce = int(time.time() * 1000)

    @property
    def paper(self) -> bool:
        return False

    def _next_nonce(self) -> str:
        self._nonce = max(self._nonce + 1, int(time.time() * 1000))
        return str(self._nonce)

    async def _private(self, client: httpx.AsyncClient, method: str, extra: dict[str, str] | None = None) -> dict[str, Any]:
        path = f"/0/private/{method}"
        params = {"nonce": self._next_nonce()}
        if extra:
            params.update({str(k): str(v) for k, v in extra.items() if v is not None and str(v) != ""})
        body = kraken_body(params)
        headers = {
            **HTTP_HEADERS,
            "API-Key": self.api_key,
            "API-Sign": kraken_signature(self.api_secret, path, params["nonce"], body),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        response = await client.post(f"{self.rest_url}{path}", content=body, headers=headers)
        try:
            payload = response.json() if response.content else {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {"error": [str(payload)[:200]]}
        errors = payload.get("error") or []
        if response.status_code != 200 or errors:
            detail = ", ".join(str(item) for item in errors) if errors else (response.text or "")[:200]
            self.status = f"auth error {response.status_code}"
            raise RuntimeError(f"Kraken HTTP {response.status_code}: {detail}"[:240])
        result = payload.get("result")
        return result if isinstance(result, dict) else {}

    async def refresh_balances(self, client: httpx.AsyncClient | None = None) -> dict[str, float]:
        own = client is None and self._client is None
        session = client or self._client or httpx.AsyncClient(timeout=8.0)
        try:
            result = await self._private(session, "Balance")
            balances: dict[str, float] = {}
            for raw, value in result.items():
                asset = from_kraken_asset(str(raw))
                amount = float(value or 0)
                if asset:
                    balances[asset] = balances.get(asset, 0.0) + amount
            self.balances = balances
            self.status = "connected"
            return balances
        finally:
            if own:
                await session.aclose()

    def _blocked(self, opportunity: Opportunity, reason: str) -> list[Fill]:
        return [
            Fill(
                venue="kraken",
                symbol="-",
                side="blocked",
                qty=0,
                price=0,
                notional=0,
                ts=time.time(),
                paper=False,
                opportunity_id=opportunity.id,
                status="blocked",
                note=reason,
            )
        ]

    def _pair(self, symbol: str) -> tuple[str, str]:
        try:
            return split_pair(symbol)
        except ValueError:
            return symbol.upper(), "USD"

    def _order_pair(self, symbol: str) -> str:
        try:
            base, quote = split_pair(symbol)
            return to_native_symbol("kraken", f"{base}-{quote}")
        except ValueError:
            return symbol

    def _fmt_size(self, amount: float, asset: str) -> str:
        digits = 2 if asset in STABLE else 8
        text = f"{_floor_qty(amount, digits):.{digits}f}"
        if asset in STABLE:
            return text
        return text.rstrip("0").rstrip(".") or "0"

    def _credit_pocket(
        self,
        pocket: dict[str, float],
        last_px: dict[str, float],
        action: str,
        symbol: str,
        qty: float,
        price: float,
        quote_spent: float,
    ) -> None:
        base, quote = self._pair(symbol)
        if qty <= 0:
            return
        if action == "buy":
            spent = quote_spent if quote_spent else qty * price
            pocket[quote] = max(0.0, pocket.get(quote, 0.0) - spent)
            pocket[base] = pocket.get(base, 0.0) + qty
        else:
            pocket[base] = max(0.0, pocket.get(base, 0.0) - qty)
            pocket[quote] = pocket.get(quote, 0.0) + (qty * price if price else 0.0)
        if price:
            last_px[base] = price

    def _size_leg(
        self,
        opportunity: Opportunity,
        action: str,
        symbol: str,
        price: float,
        pocket: dict[str, float],
        *,
        first_cash: bool,
    ) -> dict[str, Any] | str:
        base, quote = self._pair(symbol)
        if action == "buy":
            if first_cash and quote == "USD" and pocket.get(quote, 0.0) <= 0:
                spend = min(opportunity.notional, self.balances.get(quote, 0.0))
            else:
                spend = pocket.get(quote, 0.0)
            if quote in STABLE and spend + 1e-9 < max(1.0, float(self.risk.min_notional_usdt)):
                return f"insufficient {quote} ({spend:.4f} < {self.risk.min_notional_usdt:.2f})"
            if spend <= 0 or price <= 0:
                return f"no {quote} from this tap to buy {symbol}"
            qty = spend / price
            need = kraken_min_notional(base, price)
            if need and spend + 1e-9 < need:
                return (
                    f"{symbol} needs about ${need:.2f} on Kraken "
                    f"(min {KRAKEN_MIN_BASE.get(base, 0):g} {base}). "
                    f"This ${spend:.0f} tap is too small — raise the tap or pick a cheaper coin."
                )
            if float(self._fmt_size(qty, base) or 0) <= 0:
                return f"{symbol} size rounded to 0 at ${spend:.2f}"
            return {
                "action": "buy",
                "symbol": symbol,
                "pair": self._order_pair(symbol),
                "volume": self._fmt_size(qty, base),
                "quote_spent": spend,
                "price": price,
            }
        qty = _floor_qty(pocket.get(base, 0.0))
        if qty <= 0:
            return f"no {base} from this tap to sell — this tap does not sell coins you already hold"
        return {
            "action": "sell",
            "symbol": symbol,
            "pair": self._order_pair(symbol),
            "volume": self._fmt_size(qty, base),
            "quote_spent": 0.0,
            "price": price,
        }

    async def execute(self, opportunity: Opportunity) -> list[Fill]:
        decision = self.risk.allow(opportunity.notional)
        if not decision.allowed:
            return self._blocked(opportunity, decision.reason)
        if not opportunity.executable:
            return await self.paper_fallback.execute(opportunity)
        legs = [leg for leg in opportunity.legs if leg.venue == "kraken" and leg.executable]
        if not legs or len(legs) != len(opportunity.legs):
            return await self.paper_fallback.execute(opportunity)
        _, first_quote = self._pair(legs[0].symbol)
        if legs[0].action != "buy" or first_quote != "USD":
            return self._blocked(
                opportunity,
                "Live taps start with USD, then sell back to USD. This one would use coins you already hold.",
            )

        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=8.0)
        self.risk.on_submit()
        reserved = False
        fills: list[Fill] = []
        pocket: dict[str, float] = {}
        last_px: dict[str, float] = {}
        try:
            try:
                await self.refresh_balances(client)
            except Exception as exc:
                return self._blocked(opportunity, f"kraken balance check failed: {exc}"[:200])
            self.risk.reserve_live(opportunity.notional)
            reserved = True
            first_cash = True
            for leg in legs:
                sized = self._size_leg(
                    opportunity,
                    leg.action,
                    leg.symbol,
                    leg.price,
                    pocket,
                    first_cash=first_cash,
                )
                if isinstance(sized, str):
                    fills.append(
                        Fill(
                            venue="kraken",
                            symbol=leg.symbol,
                            side=leg.action,
                            qty=0,
                            price=leg.price,
                            notional=opportunity.notional,
                            ts=time.time(),
                            paper=False,
                            opportunity_id=opportunity.id,
                            status="blocked",
                            note=sized,
                        )
                    )
                    break
                fill = await self._place_order(client, opportunity, sized)
                fills.append(fill)
                if fill.status != "filled" or fill.qty <= 0:
                    break
                self._credit_pocket(
                    pocket,
                    last_px,
                    sized["action"],
                    sized["symbol"],
                    fill.qty,
                    fill.price,
                    float(sized.get("quote_spent") or 0.0),
                )
                if sized["action"] == "buy" and self._pair(sized["symbol"])[1] in STABLE:
                    first_cash = False
            leftover = await self._flatten_pocket(client, opportunity, pocket, last_px)
            fills.extend(leftover)
            realized = cash_pnl(fills)
            if any(item.status == "filled" and item.qty > 0 for item in fills):
                self.pnl += realized
                self.risk.record_pnl(realized)
            if self._pocket_stuck(pocket, last_px):
                self.risk.kill()
        finally:
            try:
                await self.refresh_balances(client)
            except Exception:
                pass
            if reserved and not any(item.status == "filled" for item in fills):
                self.risk.release_live(opportunity.notional)
            self.risk.on_complete()
            if own_client:
                await client.aclose()
        self.fills.extend(fills)
        return fills

    def _pocket_stuck(self, pocket: dict[str, float], last_px: dict[str, float]) -> bool:
        for asset, qty in pocket.items():
            qty = _floor_qty(qty)
            if asset == "USD" or qty <= 0:
                continue
            px = float(last_px.get(asset, 0.0) or 0.0)
            if asset in CONVERT_TO_USD:
                px = px or 1.0
            if px and qty * px < 1.0:
                continue
            if asset in CONVERT_TO_USD or asset not in STABLE:
                return True
        return False

    async def _place_order(
        self,
        client: httpx.AsyncClient,
        opportunity: Opportunity,
        body: dict[str, Any],
    ) -> Fill:
        fallback_price = float(body.get("price") or 0.0)
        try:
            result = await self._private(
                client,
                "AddOrder",
                {
                    "pair": str(body["pair"]),
                    "type": str(body["action"]),
                    "ordertype": "market",
                    "volume": str(body["volume"]),
                },
            )
            txid = ""
            ids = result.get("txid") or []
            if isinstance(ids, list) and ids:
                txid = str(ids[0])
            qty = 0.0
            price = fallback_price
            note = txid or str(result)[:240]
            ok = bool(txid)
            if txid:
                qty, price = await self._lookup_fill(client, txid, fallback_price)
                note = f"order {txid}"
                if qty <= 0:
                    ok = False
                    note = f"order {txid} returned no fill"
        except Exception as exc:
            return Fill(
                venue="kraken",
                symbol=str(body["symbol"]),
                side=str(body["action"]),
                qty=0,
                price=fallback_price,
                notional=opportunity.notional,
                ts=time.time(),
                paper=False,
                opportunity_id=opportunity.id,
                status="error",
                note=explain_kraken_order_error(str(exc)),
            )
        notional = qty * price if qty and price else opportunity.notional
        return Fill(
            venue="kraken",
            symbol=str(body["symbol"]),
            side=str(body["action"]),
            qty=qty,
            price=price,
            notional=notional,
            ts=time.time(),
            paper=False,
            opportunity_id=opportunity.id,
            status="filled" if ok else "error",
            note=note,
        )

    async def _flatten_pocket(
        self,
        client: httpx.AsyncClient,
        opportunity: Opportunity,
        pocket: dict[str, float],
        last_px: dict[str, float],
    ) -> list[Fill]:
        out: list[Fill] = []
        for asset, qty in list(pocket.items()):
            qty = _floor_qty(qty)
            if asset == "USD" or qty <= 0:
                continue
            if asset not in CONVERT_TO_USD and asset in STABLE:
                continue
            px = last_px.get(asset, 0.0)
            if asset in CONVERT_TO_USD:
                px = px or 1.0
            if px and qty * px < 1.0:
                continue
            symbol = f"{asset}-USD"
            body = self._size_leg(opportunity, "sell", symbol, px or 0.0, pocket, first_cash=False)
            if isinstance(body, str):
                continue
            fill = await self._place_order(client, opportunity, body)
            fill.note = f"flatten to USD · {fill.note}".strip(" ·")
            out.append(fill)
            if fill.status == "filled" and fill.qty > 0:
                self._credit_pocket(pocket, last_px, "sell", symbol, fill.qty, fill.price, 0.0)
            else:
                fill.note = f"could not sell leftover {asset} back to USD · {fill.note}"
        return out

    async def _lookup_fill(self, client: httpx.AsyncClient, txid: str, fallback_price: float) -> tuple[float, float]:
        try:
            result = await self._private(client, "QueryOrders", {"txid": txid})
            row = result.get(txid) or (next(iter(result.values())) if result else {}) or {}
            qty = float(row.get("vol_exec") or row.get("vol") or 0)
            price = float(row.get("avg_price") or row.get("price") or 0) or fallback_price
            return qty, price
        except Exception:
            return 0.0, fallback_price
