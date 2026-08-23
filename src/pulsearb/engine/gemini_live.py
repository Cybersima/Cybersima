from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

import httpx

from pulsearb.engine.broker import Broker, PaperBroker
from pulsearb.engine.money import STABLE, cash_pnl
from pulsearb.engine.risk import RiskManager
from pulsearb.feeds.headers import HTTP_HEADERS
from pulsearb.models import Fill, Opportunity
from pulsearb.symbols import split_pair, to_native_symbol

"""
Gemini has no native "market order" type on /v1/order/new - confirmed via
a real captured request/response example, not guessed. The standard way to
get market-like behavior is an "exchange limit" order with the
"immediate-or-cancel" option, priced aggressively enough to guarantee a
cross: any unfilled remainder cancels automatically (IOC), and you only pay
the price that actually matched, not your aggressive limit price, for
whatever portion fills. AGGRESSIVE_BUFFER controls how far through the
touch that limit is placed - wide enough to reliably fill through normal
spread/slippage, not so wide it would accept a wildly bad fill on a thin,
fast-moving book.

Scoped simpler than Kraken's broker on purpose: both legs are IOC
"market-like" fills, no maker-then-market-fallback retry logic. Gemini
does support maker-or-cancel orders too, which could save on fees the way
Kraken's broker does - not implemented here to keep this first pass
smaller and lower-risk. Worth adding later if the fee difference matters
to you.
"""

AGGRESSIVE_BUFFER = 0.01  # 1% through the touch, guarantees an IOC cross on a normal book


def explain_gemini_order_error(err: str) -> str:
    text = str(err)
    lower = text.lower()
    if "invalidsignature" in lower.replace(" ", "") or "invalid signature" in lower:
        return "Gemini rejected the signed request. Recheck keys\\gemini.json (API Key + Secret Key, session must allow Trading)."
    if "insufficientfunds" in lower.replace(" ", "") or "insufficient" in lower:
        return "Gemini said insufficient funds. Live starts with USD, not USDC/USDT."
    if "invalidnonce" in lower.replace(" ", ""):
        return "Gemini rejected the nonce - if another SecureTrade window is using the same key, close it (Gemini nonces must always increase)."
    if "marketnottradable" in lower.replace(" ", "") or "not tradable" in lower:
        return "Gemini says this pair isn't tradable right now."
    return text[:240]


class LiveGeminiBroker(Broker):
    """Places Gemini IOC 'exchange limit' orders that behave like market
    orders. Walks every leg of a same-venue USD-start route (2-leg
    dislocation or 3-leg triangle), then sells leftover tap coins back
    to USD. Does not skip the middle of a triangle."""

    def __init__(
        self,
        risk: RiskManager,
        api_key: str,
        api_secret: str,
        paper_fallback: PaperBroker,
        rest_url: str = "https://api.gemini.com",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.risk = risk
        self.api_key = api_key
        self.api_secret = api_secret.encode()
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

    def _next_nonce(self) -> int:
        self._nonce = max(self._nonce + 1, int(time.time() * 1000))
        return self._nonce

    def _headers(self, payload: dict) -> dict[str, str]:
        encoded = base64.b64encode(json.dumps(payload).encode())
        signature = hmac.new(self.api_secret, encoded, hashlib.sha384).hexdigest()
        return {
            **HTTP_HEADERS,
            "Content-Type": "text/plain",
            "Content-Length": "0",
            "X-GEMINI-APIKEY": self.api_key,
            "X-GEMINI-PAYLOAD": encoded.decode(),
            "X-GEMINI-SIGNATURE": signature,
            "Cache-Control": "no-cache",
        }

    async def _private(self, client: httpx.AsyncClient, request_path: str, params: dict | None = None) -> Any:
        payload = {"request": request_path, "nonce": self._next_nonce()}
        if params:
            payload.update(params)
        response = await client.post(f"{self.rest_url}{request_path}", headers=self._headers(payload))
        try:
            data = response.json()
        except Exception:
            data = {}
        if response.status_code != 200 or (isinstance(data, dict) and data.get("result") == "error"):
            reason = data.get("reason") or data.get("message") if isinstance(data, dict) else None
            self.status = f"auth error {response.status_code}"
            raise RuntimeError(f"Gemini HTTP {response.status_code}: {reason or str(data)[:200]}")
        return data

    async def refresh_balances(self, client: httpx.AsyncClient | None = None) -> dict[str, float]:
        own = client is None and self._client is None
        session = client or self._client or httpx.AsyncClient(timeout=8.0)
        try:
            rows = await self._private(session, "/v1/balances")
            balances: dict[str, float] = {}
            for row in rows if isinstance(rows, list) else []:
                currency = str(row.get("currency") or "").upper()
                amount = float(row.get("available") or 0)
                if currency:
                    balances[currency] = amount
            self.balances = balances
            self.status = "connected"
            return balances
        finally:
            if own:
                await session.aclose()

    def _blocked(self, opportunity: Opportunity, reason: str) -> list[Fill]:
        return [
            Fill(
                venue="gemini", symbol="-", side="blocked", qty=0, price=0, notional=0,
                ts=time.time(), paper=False, opportunity_id=opportunity.id,
                status="blocked", note=reason,
            )
        ]

    def _fmt(self, amount: float, digits: int = 8) -> str:
        text = f"{amount:.{digits}f}"
        return text.rstrip("0").rstrip(".") or "0"

    async def execute(self, opportunity: Opportunity) -> list[Fill]:
        decision = self.risk.allow(opportunity.notional)
        if not decision.allowed:
            return self._blocked(opportunity, decision.reason)
        if not opportunity.executable:
            return await self.paper_fallback.execute(opportunity)
        legs = [leg for leg in opportunity.legs if leg.venue == "gemini" and leg.executable]
        if not legs or len(legs) != len(opportunity.legs):
            return await self.paper_fallback.execute(opportunity)
        if legs[0].action != "buy":
            return self._blocked(opportunity, "Live taps start with USD, then sell back to USD. This one would use coins you already hold.")
        try:
            _base0, quote0 = split_pair(legs[0].symbol)
        except ValueError:
            return self._blocked(opportunity, f"Could not read currency pair from {legs[0].symbol}")
        if quote0 != "USD":
            return self._blocked(opportunity, "Live taps start with USD, then sell back to USD. This one would use coins you already hold.")

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
                return self._blocked(opportunity, f"gemini balance check failed: {exc}"[:200])
            floor = max(0.01, float(self.risk.min_notional_usdt))
            if self.balances.get("USD", 0.0) + 1e-9 < floor:
                return self._blocked(opportunity, f"insufficient USD ({self.balances.get('USD', 0.0):.4f} < {floor:.2f})")
            self.risk.reserve_live(opportunity.notional)
            reserved = True

            first_cash = True
            failed = False
            for leg in legs:
                try:
                    base, quote = split_pair(leg.symbol)
                except ValueError:
                    fills.append(self._error_fill(opportunity, leg.symbol, leg.price, f"Could not read {leg.symbol}"))
                    failed = True
                    break
                if leg.action == "buy":
                    spend = (
                        min(opportunity.notional, self.balances.get("USD", 0.0))
                        if first_cash and quote == "USD" and pocket.get(quote, 0.0) <= 0
                        else pocket.get(quote, 0.0)
                    )
                    if quote in STABLE and spend + 1e-9 < floor:
                        fills.append(self._error_fill(opportunity, leg.symbol, leg.price, f"insufficient {quote} ({spend:.4f} < {floor:.2f})"))
                        failed = True
                        break
                    fill = await self._place_ioc(
                        client, opportunity, leg.symbol, "buy", usd_amount=spend, price_hint=leg.price
                    )
                    fills.append(fill)
                    if fill.status != "filled" or fill.qty <= 0:
                        failed = True
                        break
                    pocket[quote] = max(0.0, pocket.get(quote, 0.0) - fill.notional)
                    pocket[base] = pocket.get(base, 0.0) + fill.qty
                    last_px[base] = fill.price
                    if quote in STABLE:
                        first_cash = False
                else:
                    qty = pocket.get(base, 0.0)
                    if qty <= 1e-12:
                        fills.append(
                            self._error_fill(
                                opportunity,
                                leg.symbol,
                                leg.price,
                                f"no {base} from this tap to sell — this tap does not sell coins you already hold",
                            )
                        )
                        failed = True
                        break
                    fill = await self._place_ioc(
                        client, opportunity, leg.symbol, "sell", base_qty=qty, price_hint=leg.price
                    )
                    fills.append(fill)
                    if fill.status != "filled" or fill.qty <= 0:
                        failed = True
                        break
                    pocket[base] = max(0.0, pocket.get(base, 0.0) - fill.qty)
                    pocket[quote] = pocket.get(quote, 0.0) + fill.notional
                    last_px[base] = fill.price
            leftover = await self._flatten_pocket(client, opportunity, pocket, last_px)
            fills.extend(leftover)
            realized = cash_pnl(fills)
            if any(item.status == "filled" and item.qty > 0 for item in fills):
                self.pnl += realized
                self.risk.record_pnl(realized)
            if any(abs(qty) > 1e-8 for asset, qty in pocket.items() if asset not in STABLE):
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

    async def _flatten_pocket(
        self,
        client: httpx.AsyncClient,
        opportunity: Opportunity,
        pocket: dict[str, float],
        last_px: dict[str, float],
    ) -> list[Fill]:
        fills: list[Fill] = []
        for asset, qty in list(pocket.items()):
            if asset in STABLE or qty <= 1e-10:
                continue
            fill = await self._place_ioc(
                client,
                opportunity,
                f"{asset}-USD",
                "sell",
                base_qty=qty,
                price_hint=last_px.get(asset, 0.0),
            )
            fills.append(fill)
            if fill.status == "filled" and fill.qty > 0:
                pocket[asset] = max(0.0, pocket.get(asset, 0.0) - fill.qty)
                pocket["USD"] = pocket.get("USD", 0.0) + fill.notional
        return fills

    async def _place_ioc(
        self,
        client: httpx.AsyncClient,
        opportunity: Opportunity,
        symbol: str,
        side: str,
        price_hint: float,
        usd_amount: float | None = None,
        base_qty: float | None = None,
    ) -> Fill:
        native = to_native_symbol("gemini", symbol)
        if side == "buy":
            limit_price = price_hint * (1 + AGGRESSIVE_BUFFER)
            amount = (usd_amount or 0.0) / limit_price if limit_price else 0.0
        else:
            limit_price = price_hint * (1 - AGGRESSIVE_BUFFER)
            amount = base_qty or 0.0
        if amount <= 0:
            return self._error_fill(opportunity, symbol, price_hint, f"{symbol}: nothing to {side}")
        params = {
            "client_order_id": uuid.uuid4().hex,
            "symbol": native,
            "amount": self._fmt(amount),
            "price": self._fmt(limit_price, 2 if limit_price >= 1 else 8),
            "side": side,
            "type": "exchange limit",
            "options": ["immediate-or-cancel"],
        }
        try:
            result = await self._private(client, "/v1/order/new", params)
        except Exception as exc:
            return self._error_fill(opportunity, symbol, price_hint, explain_gemini_order_error(str(exc)))
        if not isinstance(result, dict):
            return self._error_fill(opportunity, symbol, price_hint, "Gemini returned an unexpected response")
        executed_qty = float(result.get("executed_amount") or 0)
        avg_price = float(result.get("avg_execution_price") or 0) or price_hint
        order_id = str(result.get("order_id") or "")
        if executed_qty <= 0:
            return self._error_fill(opportunity, symbol, price_hint, f"{symbol}: IOC order did not fill (no liquidity at this price)")
        return Fill(
            venue="gemini", symbol=symbol, side=side, qty=executed_qty, price=avg_price,
            notional=executed_qty * avg_price, ts=time.time(), paper=False,
            opportunity_id=opportunity.id, status="filled", note=f"order {order_id}",
        )

    def _error_fill(self, opportunity: Opportunity, symbol: str, fallback_price: float, note: str) -> Fill:
        return Fill(
            venue="gemini", symbol=symbol, side="error", qty=0, price=fallback_price, notional=opportunity.notional,
            ts=time.time(), paper=False, opportunity_id=opportunity.id, status="error", note=note,
        )
