from __future__ import annotations

import time
from typing import Any

import httpx

from pulsearb.engine.broker import Broker, PaperBroker
from pulsearb.engine.risk import RiskManager
from pulsearb.feeds.headers import HTTP_HEADERS
from pulsearb.feeds.oanda import LIVE_URL, PRACTICE_URL
from pulsearb.models import Fill, Opportunity
from pulsearb.symbols import split_pair, to_native_symbol

"""
CRITICAL SIZING DECISION - read before touching this file:

OANDA is a MARGIN broker: leverage means a small deposit controls a much
bigger position. Every other venue in this app ("spend $X, get $X of the
asset") is spot - what you tap is what you risk. To keep that exact same
mental model here, a "$5 tap" on OANDA opens a position worth $5 of
notional currency exposure, period - NOT "$5 of margin at max account
leverage" (which could silently open a position 20-50x bigger than the
number on the button). The account's leverage setting only affects how
much margin OANDA reserves to hold that $5 position open, never the size
of the position itself. Do not "improve" this by scaling position size
with leverage - that would make the tap-size number lie to the user in
exactly the way the rest of this app goes out of its way not to.

Second deliberate choice: every OANDA trade here is an immediate
open-then-close round trip (market order in, then a full position close),
never a position left open and unmanaged. This app's risk system (kill
switch, daily loss limit, cooldowns) was built around round trips
finishing in the same tap - it does not monitor open positions over time,
which a real margin position needs (stop-loss, ongoing margin checks).
Leaving positions open here would be running real leveraged risk this
app cannot see or protect against.
"""


OANDA_MIN_UNITS = 1  # OANDA accepts single-unit orders on major pairs; this is a sanity floor, not a real exchange minimum table


def explain_oanda_order_error(err: str) -> str:
    text = str(err)
    lower = text.lower()
    if "insufficient_margin" in lower or "insufficient margin" in lower:
        return "OANDA rejected the order for insufficient margin - the account doesn't have enough free margin for this position size."
    if "401" in text or "unauthorized" in lower:
        return "OANDA rejected the access token (401). Recheck keys\\oanda.json - regenerate the token in the OANDA account portal under Manage API Access."
    if "market_halted" in lower or "instrument_missing_liquidity" in lower or "no_liquidity" in lower:
        return "OANDA has no tradeable liquidity for this pair right now (market closed or halted)."
    if "invalid_instrument" in lower:
        return "OANDA does not recognize this instrument - check the symbol against OANDA's own instrument list."
    if "account_not_active" in lower or "account_not_tradeable" in lower:
        return "This OANDA account isn't active for trading - check the account status in the OANDA portal."
    return text[:240]


class LiveOandaBroker(Broker):
    """Places OANDA v20 market orders. Single-pair round trips only (open,
    then immediately close) - no multi-leg triangular chains, no positions
    left open. See the module docstring above for the tap-size/leverage
    design decision this depends on.
    """

    def __init__(
        self,
        risk: RiskManager,
        account_id: str,
        access_token: str,
        paper_fallback: PaperBroker,
        environment: str = "practice",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.risk = risk
        self.account_id = account_id
        self.access_token = access_token
        self.paper_fallback = paper_fallback
        self.base_url = LIVE_URL if str(environment).strip().lower() == "live" else PRACTICE_URL
        self.fills: list[Fill] = []
        self.pnl = 0.0
        self.balances: dict[str, float] = {}
        self.status = "idle"
        self._client = client

    @property
    def paper(self) -> bool:
        return False

    def _headers(self) -> dict[str, str]:
        return {**HTTP_HEADERS, "Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    async def refresh_balances(self, client: httpx.AsyncClient | None = None) -> dict[str, float]:
        own = client is None and self._client is None
        session = client or self._client or httpx.AsyncClient(timeout=8.0)
        try:
            response = await session.get(
                f"{self.base_url}/v3/accounts/{self.account_id}/summary", headers=self._headers()
            )
            if response.status_code != 200:
                self.status = f"auth error {response.status_code}"
                raise RuntimeError(f"OANDA HTTP {response.status_code}: {response.text[:200]}")
            account = (response.json() or {}).get("account") or {}
            currency = str(account.get("currency") or "USD").upper()
            balance = float(account.get("balance") or 0.0)
            if currency != "USD":
                # The rest of this app assumes a USD-denominated pocket. A
                # non-USD OANDA home currency would misreport here - flagged
                # rather than silently treated as USD.
                self.status = f"warning: account currency is {currency}, not USD"
            self.balances = {currency: balance}
            if currency == "USD":
                self.status = "connected"
            return self.balances
        finally:
            if own:
                await session.aclose()

    def _units_for_leg(self, base: str, notional: float, price: float) -> int:
        if base == "USD":
            # USD is the pair's base currency (e.g. USD-JPY): the dollar tap
            # amount IS the unit count directly - see markets.yaml's comment
            # on why these pairs are listed USD-first.
            units = notional
        elif price > 0:
            units = notional / price
        else:
            units = 0.0
        return int(round(units))

    def _blocked(self, opportunity: Opportunity, reason: str) -> list[Fill]:
        return [
            Fill(
                venue="oanda", symbol="-", side="blocked", qty=0, price=0, notional=0,
                ts=time.time(), paper=False, opportunity_id=opportunity.id,
                status="blocked", note=reason,
            )
        ]

    async def execute(self, opportunity: Opportunity) -> list[Fill]:
        decision = self.risk.allow(opportunity.notional)
        if not decision.allowed:
            return self._blocked(opportunity, decision.reason)
        if not opportunity.executable:
            return await self.paper_fallback.execute(opportunity)
        legs = [leg for leg in opportunity.legs if leg.venue == "oanda" and leg.executable]
        if not legs or len(legs) != len(opportunity.legs):
            return await self.paper_fallback.execute(opportunity)
        if len(legs) != 2 or legs[0].action != "buy" or legs[1].action != "sell" or legs[0].symbol != legs[1].symbol:
            # Scoped to single-pair open+close round trips only - see the
            # module docstring. Anything else (multi-leg FX triangles
            # purely on OANDA) stays paper for now.
            return self._blocked(
                opportunity,
                "OANDA live only takes a single-pair open-then-close tap right now, not multi-leg FX chains.",
            )

        symbol = legs[0].symbol
        try:
            base, _quote = split_pair(symbol)
        except ValueError:
            return self._blocked(opportunity, f"Could not read currency pair from {symbol}")
        instrument = to_native_symbol("oanda", symbol)
        price = float(legs[0].price or 0.0)
        units = self._units_for_leg(base, opportunity.notional, price)
        if abs(units) < OANDA_MIN_UNITS:
            return self._blocked(
                opportunity,
                f"{symbol}: this tap rounds to {units} units on OANDA — too small. Raise the tap size.",
            )

        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=8.0)
        self.risk.on_submit()
        reserved = False
        fills: list[Fill] = []
        try:
            try:
                await self.refresh_balances(client)
            except Exception as exc:
                return self._blocked(opportunity, f"OANDA balance check failed: {exc}"[:200])
            self.risk.reserve_live(opportunity.notional)
            reserved = True

            open_fill = await self._place_market(client, opportunity, symbol, instrument, units, price)
            fills.append(open_fill)
            if open_fill.status == "filled" and open_fill.qty > 0:
                close_fill = await self._close_position(
                    client, opportunity, symbol, instrument, open_fill.price, units
                )
                fills.append(close_fill)
                if close_fill.status == "filled":
                    realized = (close_fill.price - open_fill.price) * open_fill.qty
                    if units < 0:
                        realized = -realized
                    self.pnl += realized
                    self.risk.record_pnl(realized)
                else:
                    # Opened but couldn't confirm the close - do not guess a
                    # PnL for a position that might still be open. Flagged
                    # loudly rather than silently marked complete.
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

    async def _place_market(
        self, client: httpx.AsyncClient, opportunity: Opportunity, symbol: str, instrument: str, units: int, fallback_price: float
    ) -> Fill:
        body = {
            "order": {
                "type": "MARKET",
                "instrument": instrument,
                "units": str(units),
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
            }
        }
        try:
            response = await client.post(
                f"{self.base_url}/v3/accounts/{self.account_id}/orders", headers=self._headers(), json=body
            )
            payload = response.json() if response.content else {}
            if response.status_code >= 400:
                err = payload.get("errorCode") or payload.get("errorMessage") or str(payload)
                return self._error_fill(opportunity, symbol, fallback_price, explain_oanda_order_error(str(err)))
            fill_txn = payload.get("orderFillTransaction")
            if not fill_txn:
                reject = payload.get("orderRejectTransaction") or {}
                reason = reject.get("rejectReason") or "order not filled"
                return self._error_fill(opportunity, symbol, fallback_price, explain_oanda_order_error(str(reason)))
            price = float(fill_txn.get("price") or fallback_price)
            filled_units = abs(float(fill_txn.get("units") or units))
            return Fill(
                venue="oanda", symbol=symbol, side="buy" if units > 0 else "sell",
                qty=filled_units, price=price, notional=filled_units * price,
                ts=time.time(), paper=False, opportunity_id=opportunity.id,
                status="filled", note=f"order {fill_txn.get('id', '')}",
            )
        except Exception as exc:
            return self._error_fill(opportunity, symbol, fallback_price, explain_oanda_order_error(str(exc)))

    async def _close_position(
        self,
        client: httpx.AsyncClient,
        opportunity: Opportunity,
        symbol: str,
        instrument: str,
        fallback_price: float,
        open_units: int,
    ) -> Fill:
        """Closes only the units this tap opened on this instrument."""
        try:
            # Close only the units this tap opened — never ALL, which would
            # flatten a position the user already had on this pair.
            qty = max(1, int(round(abs(float(open_units)))))
            if float(open_units) > 0:
                body = {"longUnits": str(qty), "shortUnits": "NONE"}
            else:
                body = {"shortUnits": str(qty), "longUnits": "NONE"}
            response = await client.put(
                f"{self.base_url}/v3/accounts/{self.account_id}/positions/{instrument}/close",
                headers=self._headers(),
                json=body,
            )
            payload = response.json() if response.content else {}
            if response.status_code >= 400:
                err = payload.get("errorCode") or payload.get("errorMessage") or str(payload)
                return self._error_fill(opportunity, symbol, fallback_price, explain_oanda_order_error(str(err)))
            txn = payload.get("longOrderFillTransaction") or payload.get("shortOrderFillTransaction")
            if not txn:
                return self._error_fill(opportunity, symbol, fallback_price, "OANDA did not confirm the close - check the position manually in the OANDA portal.")
            price = float(txn.get("price") or fallback_price)
            qty = abs(float(txn.get("units") or 0))
            return Fill(
                venue="oanda", symbol=symbol, side="sell", qty=qty, price=price, notional=qty * price,
                ts=time.time(), paper=False, opportunity_id=opportunity.id,
                status="filled", note=f"close {txn.get('id', '')}",
            )
        except Exception as exc:
            return self._error_fill(opportunity, symbol, fallback_price, f"Could not confirm the close: {exc}"[:200])

    def _error_fill(self, opportunity: Opportunity, symbol: str, fallback_price: float, note: str) -> Fill:
        return Fill(
            venue="oanda", symbol=symbol, side="error", qty=0, price=fallback_price, notional=opportunity.notional,
            ts=time.time(), paper=False, opportunity_id=opportunity.id, status="error", note=note,
        )
