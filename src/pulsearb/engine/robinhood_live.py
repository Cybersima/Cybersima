from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

import httpx

from pulsearb.engine.broker import Broker, PaperBroker
from pulsearb.engine.money import STABLE, cash_pnl
from pulsearb.engine.risk import RiskManager
from pulsearb.engine.robinhood_auth import robinhood_headers
from pulsearb.feeds.headers import HTTP_HEADERS
from pulsearb.models import Fill, Opportunity
from pulsearb.symbols import split_pair, to_native_symbol

"""
CONFIDENCE NOTE - what's confirmed vs. inferred here:

The signing scheme, base URL, endpoint paths, and order request body are
copied exactly from Robinhood's own official reference client
(docs.robinhood.com/crypto/trading) - not guessed. See engine/robinhood_auth.py
for the signing verification.

Two things that reference client shows requests for but never PARSES a
response for, so the exact field names below are reasonable, best-effort
candidates, not confirmed:
  1. Account/holdings response - which field holds spendable USD.
  2. Order response - which field holds fill state, filled quantity, and
     average price.
Both are handled defensively: several plausible field names are tried, and
if none match, the code treats that as "could not confirm" rather than
guessing a number - see _extract_usd_balance() and _parse_order_result().
An error message in that case includes a slice of the raw response, so a
real run makes the actual field names visible immediately for a one-line
fix, rather than failing silently or asserting a wrong balance/fill.

Same design choices as OANDA/Gemini/Bitstamp: single-pair open-then-close
round trips only, market orders on both legs, nothing left open. Robinhood
has no practice/sandbox environment (unlike OANDA) - every live order here
is real money from the first test.
"""

BASE_URL = "https://trading.robinhood.com"


def explain_robinhood_order_error(err: str) -> str:
    text = str(err)
    lower = text.lower()
    # Friendly guidance is prepended, but the raw server text stays attached
    # rather than being replaced outright - a real CHECK-LIVE run against a
    # live key surfaced that discarding it here removes exactly the detail
    # (Robinhood's own error message) most useful for pinning down which of
    # several possible 401 causes actually applies.
    if "401" in text or "unauthorized" in lower or "invalid signature" in lower:
        return (
            "Robinhood rejected the signed request (401) - usually a key "
            "mismatch (the public key registered in the API Credentials "
            "Portal must exactly match the private key in keys\\robinhood.json), "
            "but can also be system clock drift (Robinhood may reject a "
            "timestamp too far from its own clock) or a copy-paste issue in "
            "the private key (stray whitespace/newline/truncation). "
            f"Robinhood's own response: {text}"
        )
    if "insufficient" in lower or "not enough" in lower:
        return "Robinhood said insufficient buying power. Live starts with USD."
    if "403" in text or "forbidden" in lower:
        return f"Robinhood key is missing a required permission - recheck which API actions were enabled when the key was created. Robinhood's own response: {text}"
    return text[:240]


class LiveRobinhoodBroker(Broker):
    def __init__(
        self,
        risk: RiskManager,
        api_key: str,
        private_key_base64: str,
        paper_fallback: PaperBroker,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.risk = risk
        self.api_key = api_key
        self.private_key_base64 = private_key_base64
        self.paper_fallback = paper_fallback
        self.fills: list[Fill] = []
        self.pnl = 0.0
        self.balances: dict[str, float] = {}
        self.status = "idle"
        self._client = client
        self._account_number: str | None = None

    @property
    def paper(self) -> bool:
        return False

    async def _request(self, client: httpx.AsyncClient, method: str, path: str, body: str = "") -> Any:
        headers = {**HTTP_HEADERS, **robinhood_headers(self.api_key, self.private_key_base64, method, path, body)}
        if body:
            headers["Content-Type"] = "application/json"
        url = f"{BASE_URL}{path}"
        response = await client.request(method, url, content=body if body else None, headers=headers)
        try:
            data = response.json()
        except Exception:
            data = {}
        if response.status_code >= 400:
            detail = data.get("detail") if isinstance(data, dict) else None
            self.status = f"auth error {response.status_code}"
            raise RuntimeError(f"Robinhood HTTP {response.status_code}: {detail or str(data)[:200]}")
        return data

    async def _ensure_account_number(self, client: httpx.AsyncClient) -> str:
        if self._account_number:
            return self._account_number
        result = await self._request(client, "GET", "/api/v2/crypto/trading/accounts/")
        rows = result.get("results") if isinstance(result, dict) else result
        if not rows:
            raise RuntimeError("Robinhood returned no accounts for this key")
        account_number = rows[0].get("account_number")
        if not account_number:
            raise RuntimeError(f"Robinhood account response had no account_number field: {str(rows[0])[:200]}")
        self._account_number = str(account_number)
        return self._account_number

    def _extract_usd_balance(self, account_row: dict) -> float:
        for field in ("buying_power", "cash", "cash_available_for_withdrawal", "usd_balance", "available_balance"):
            value = account_row.get(field)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return 0.0

    async def refresh_balances(self, client: httpx.AsyncClient | None = None) -> dict[str, float]:
        own = client is None and self._client is None
        session = client or self._client or httpx.AsyncClient(timeout=8.0)
        try:
            account_result = await self._request(session, "GET", "/api/v2/crypto/trading/accounts/")
            rows = account_result.get("results") if isinstance(account_result, dict) else account_result
            if not rows:
                raise RuntimeError("Robinhood returned no accounts for this key")
            account_row = rows[0]
            account_number = account_row.get("account_number")
            if account_number:
                self._account_number = str(account_number)
            usd = self._extract_usd_balance(account_row)
            balances = {"USD": usd}

            if self._account_number:
                holdings_result = await self._request(
                    session, "GET", f"/api/v2/crypto/trading/holdings/?account_number={self._account_number}"
                )
                holding_rows = holdings_result.get("results") if isinstance(holdings_result, dict) else holdings_result
                for row in holding_rows or []:
                    asset = str(row.get("asset_code") or "").upper()
                    qty = row.get("total_quantity") or row.get("quantity") or 0
                    if asset:
                        try:
                            balances[asset] = float(qty)
                        except (TypeError, ValueError):
                            continue
            self.balances = balances
            self.status = "connected"
            return balances
        finally:
            if own:
                await session.aclose()

    def _blocked(self, opportunity: Opportunity, reason: str) -> list[Fill]:
        return [
            Fill(
                venue="robinhood", symbol="-", side="blocked", qty=0, price=0, notional=0,
                ts=time.time(), paper=False, opportunity_id=opportunity.id,
                status="blocked", note=reason,
            )
        ]

    def _fmt(self, amount: float) -> str:
        text = f"{amount:.8f}"
        return text.rstrip("0").rstrip(".") or "0"

    async def execute(self, opportunity: Opportunity) -> list[Fill]:
        decision = self.risk.allow(opportunity.notional)
        if not decision.allowed:
            return self._blocked(opportunity, decision.reason)
        if not opportunity.executable:
            return await self.paper_fallback.execute(opportunity)
        legs = [leg for leg in opportunity.legs if leg.venue == "robinhood" and leg.executable]
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
                return self._blocked(opportunity, f"robinhood balance check failed: {exc}"[:200])
            floor = max(0.01, float(self.risk.min_notional_usdt))
            if self.balances.get("USD", 0.0) + 1e-9 < floor:
                return self._blocked(opportunity, f"insufficient USD ({self.balances.get('USD', 0.0):.4f} < {floor:.2f})")
            self.risk.reserve_live(opportunity.notional)
            reserved = True

            first_cash = True
            for leg in legs:
                try:
                    base, quote = split_pair(leg.symbol)
                except ValueError:
                    fills.append(self._error_fill(opportunity, leg.symbol, leg.price, f"Could not read {leg.symbol}"))
                    break
                if leg.action == "buy":
                    spend = (
                        min(opportunity.notional, self.balances.get("USD", 0.0))
                        if first_cash and quote == "USD" and pocket.get(quote, 0.0) <= 0
                        else pocket.get(quote, 0.0)
                    )
                    if quote in STABLE and spend + 1e-9 < floor:
                        fills.append(self._error_fill(opportunity, leg.symbol, leg.price, f"insufficient {quote} ({spend:.4f} < {floor:.2f})"))
                        break
                    fill = await self._place_market(
                        client, opportunity, leg.symbol, "buy", usd_amount=spend, price_hint=leg.price
                    )
                    fills.append(fill)
                    if fill.status != "filled" or fill.qty <= 0:
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
                        break
                    fill = await self._place_market(
                        client, opportunity, leg.symbol, "sell", base_qty=qty, price_hint=leg.price
                    )
                    fills.append(fill)
                    if fill.status != "filled" or fill.qty <= 0:
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
            fill = await self._place_market(
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

    def _parse_order_result(self, result: dict) -> tuple[str, float, float, str]:
        """Returns (state, filled_qty, avg_price, order_id). Tries several
        plausible field names - see the module docstring's confidence note."""
        order_id = str(result.get("id") or result.get("order_id") or "")
        state = str(result.get("state") or result.get("status") or "").lower()
        filled_qty = 0.0
        # Official fill fields only — never treat requested asset_quantity as a fill.
        for field in ("filled_asset_quantity", "executed_asset_quantity"):
            value = result.get(field)
            if value is not None:
                try:
                    filled_qty = float(value)
                    break
                except (TypeError, ValueError):
                    continue
        avg_price = 0.0
        for field in ("average_price", "executed_price"):
            value = result.get(field)
            if value is not None:
                try:
                    avg_price = float(value)
                    break
                except (TypeError, ValueError):
                    continue
        return state, filled_qty, avg_price, order_id

    async def _place_market(
        self,
        client: httpx.AsyncClient,
        opportunity: Opportunity,
        symbol: str,
        side: str,
        price_hint: float,
        usd_amount: float | None = None,
        base_qty: float | None = None,
    ) -> Fill:
        native = to_native_symbol("robinhood", symbol)
        if side == "buy":
            quantity = (usd_amount or 0.0) / price_hint if price_hint else 0.0
        else:
            quantity = base_qty or 0.0
        if quantity <= 0:
            return self._error_fill(opportunity, symbol, price_hint, f"{symbol}: nothing to {side}")

        try:
            account_number = await self._ensure_account_number(client)
        except Exception as exc:
            return self._error_fill(opportunity, symbol, price_hint, explain_robinhood_order_error(str(exc)))

        body = json.dumps({
            "client_order_id": str(uuid.uuid4()),
            "side": side,
            "type": "market",
            "symbol": native,
            "market_order_config": {"asset_quantity": self._fmt(quantity)},
        })
        path = f"/api/v2/crypto/trading/orders/?account_number={account_number}"
        try:
            result = await self._request(client, "POST", path, body)
        except Exception as exc:
            return self._error_fill(opportunity, symbol, price_hint, explain_robinhood_order_error(str(exc)))
        if not isinstance(result, dict):
            return self._error_fill(opportunity, symbol, price_hint, "Robinhood returned an unexpected response")

        state, filled_qty, avg_price, order_id = self._parse_order_result(result)
        # Market orders on a major brokerage typically fill in well under a
        # second - poll briefly for a terminal state if the initial response
        # doesn't already show one, rather than assuming instant success.
        deadline = time.time() + 8.0
        while order_id and state not in ("filled", "canceled", "cancelled", "rejected", "failed") and time.time() < deadline:
            await asyncio.sleep(0.4)
            try:
                lookup = await self._request(client, "GET", f"/api/v2/crypto/trading/orders/{order_id}/?account_number={account_number}")
                if isinstance(lookup, dict):
                    state, filled_qty, avg_price, order_id = self._parse_order_result(lookup)
            except Exception:
                break

        if filled_qty <= 0 or state not in ("filled", "partially_filled"):
            note = (
                f"order {order_id} state={state or 'unknown'} - could not confirm a fill. "
                f"Raw response: {str(result)[:160]}"
            )
            return self._error_fill(opportunity, symbol, price_hint, note)
        price = avg_price or price_hint
        return Fill(
            venue="robinhood", symbol=symbol, side=side, qty=filled_qty, price=price,
            notional=filled_qty * price, ts=time.time(), paper=False,
            opportunity_id=opportunity.id, status="filled", note=f"order {order_id}",
        )

    def _error_fill(self, opportunity: Opportunity, symbol: str, fallback_price: float, note: str) -> Fill:
        return Fill(
            venue="robinhood", symbol=symbol, side="error", qty=0, price=fallback_price, notional=opportunity.notional,
            ts=time.time(), paper=False, opportunity_id=opportunity.id, status="error", note=note,
        )
