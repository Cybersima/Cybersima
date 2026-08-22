from __future__ import annotations

import asyncio
import math
import time
import uuid
from typing import Any

import httpx

from pulsearb.engine.broker import Broker, PaperBroker
from pulsearb.engine.coinbase_auth import HOST, build_rest_jwt
from pulsearb.engine.money import CONVERT_TO_USD, STABLE, cash_pnl
from pulsearb.engine.risk import RiskManager
from pulsearb.feeds.headers import HTTP_HEADERS
from pulsearb.models import Fill, Opportunity
from pulsearb.symbols import split_pair


def _floor_qty(qty: float, digits: int = 8) -> float:
    if qty <= 0:
        return 0.0
    scale = 10 ** digits
    return math.floor((qty + 1e-15) * scale) / scale


class LiveCoinbaseBroker(Broker):
    """Places Coinbase Advanced Trade market IOC orders. Same-venue legs only.

    Each tap is a round-trip: buy, convert, sell back toward USD. It does not
    buy-to-hold, and it will not sell coins the customer already had.
    """

    def __init__(
        self,
        risk: RiskManager,
        api_key: str,
        api_secret: str,
        paper_fallback: PaperBroker,
        rest_url: str = "https://api.coinbase.com",
        client: httpx.AsyncClient | None = None,
        *,
        maker_exits: bool = True,
        maker_wait_seconds: float = 8.0,
    ) -> None:
        self.risk = risk
        self.api_key = api_key
        self.api_secret = api_secret
        self.paper_fallback = paper_fallback
        self.rest_url = rest_url.rstrip("/")
        self.host = HOST
        self.fills: list[Fill] = []
        self.pnl = 0.0
        self.balances: dict[str, float] = {}
        self.status = "idle"
        self._client = client
        self.maker_exits = bool(maker_exits)
        self.maker_wait_seconds = max(0.0, float(maker_wait_seconds))

    @property
    def paper(self) -> bool:
        return False

    def _auth_headers(self, method: str, path: str) -> dict[str, str]:
        # Coinbase JWTs must use the path only. Query strings in the uri claim
        # are rejected (often as HTTP 401 with an empty body).
        token = build_rest_jwt(self.api_key, self.api_secret, method, path, host=self.host)
        return {
            **HTTP_HEADERS,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        return await client.request(
            method,
            f"{self.rest_url}{path}",
            params=params,
            json=json_body,
            headers=self._auth_headers(method, path),
        )

    def _payload_or_error(self, response: httpx.Response) -> dict[str, Any]:
        text = (response.text or "").strip()
        payload: dict[str, Any] = {}
        if text:
            try:
                data = response.json()
                if isinstance(data, dict):
                    payload = data
                else:
                    payload = {"message": text[:200]}
            except Exception:
                payload = {"message": text[:200]}
        if response.status_code != 200:
            self.status = f"auth error {response.status_code}"
            detail = (
                str(payload.get("error_response") or payload.get("message") or payload.get("error") or "").strip()
                or text
                or "empty body"
            )
            raise RuntimeError(f"Coinbase HTTP {response.status_code}: {detail}"[:240])
        return payload

    async def refresh_balances(self, client: httpx.AsyncClient | None = None) -> dict[str, float]:
        own = client is None and self._client is None
        session = client or self._client or httpx.AsyncClient(timeout=8.0)
        try:
            response = await self._request(session, "GET", "/api/v3/brokerage/accounts", params={"limit": 250})
            payload = self._payload_or_error(response)
            balances: dict[str, float] = {}
            for row in payload.get("accounts") or []:
                currency = str(row.get("currency") or "").upper()
                available = row.get("available_balance") or {}
                value = float(available.get("value") or 0)
                if currency:
                    balances[currency] = balances.get(currency, 0.0) + value
            self.balances = balances
            self.status = "connected"
            return balances
        finally:
            if own:
                await session.aclose()

    def _blocked(self, opportunity: Opportunity, reason: str) -> list[Fill]:
        return [
            Fill(
                venue="coinbase",
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

    def _fmt_size(self, amount: float, asset: str) -> str:
        digits = 2 if asset in STABLE else 8
        text = f"{_floor_qty(amount, digits):.{digits}f}"
        if asset in STABLE:
            return text
        return text.rstrip("0").rstrip(".") or "0"

    def _order_body(
        self,
        opportunity: Opportunity,
        action: str,
        symbol: str,
        price: float,
        *,
        quote_size: float | None = None,
        base_size: float | None = None,
    ) -> dict[str, Any]:
        base, quote = self._pair(symbol)
        side = "BUY" if action == "buy" else "SELL"
        config: dict[str, str] = {}
        if side == "BUY":
            spend = opportunity.notional if quote_size is None else quote_size
            config["quote_size"] = self._fmt_size(spend, quote)
            return {
                "client_order_id": str(uuid.uuid4()),
                "product_id": symbol,
                "side": side,
                "order_configuration": {"market_market_ioc": config},
                "_base": base,
                "_quote": quote,
            }
        qty = (opportunity.notional / price if price else 0.0) if base_size is None else base_size
        config["base_size"] = self._fmt_size(qty, base)
        return {
            "client_order_id": str(uuid.uuid4()),
            "product_id": symbol,
            "side": side,
            "order_configuration": {"market_market_ioc": config},
            "_base": base,
            "_quote": quote,
        }

    def _cfg(self, body: dict[str, Any]) -> dict[str, str]:
        cfg = body.get("order_configuration") or {}
        return cfg.get("market_market_ioc") or cfg.get("limit_limit_gtc") or {}

    def _enough_balance(self, body: dict[str, Any], pocket: dict[str, float] | None = None) -> str | None:
        ioc = self._cfg(body)
        pocket = pocket or {}
        if body["side"] == "BUY":
            need = float(ioc.get("quote_size") or 0)
            asset = str(body["_quote"])
            have_acct = self.balances.get(asset, 0.0)
            have_pocket = pocket.get(asset, 0.0)
            have = have_pocket if asset != "USD" or have_pocket > 0 else have_acct
            if have + 1e-9 < need:
                return f"insufficient {asset} ({have:.8f} < {need})"
        else:
            need = float(ioc.get("base_size") or 0)
            asset = str(body["_base"])
            have = pocket.get(asset, 0.0)
            if have + 1e-9 < need:
                return f"insufficient {asset} ({have:.8f} < {need})"
        return None

    def _credit_pocket(
        self,
        pocket: dict[str, float],
        last_px: dict[str, float],
        body: dict[str, Any],
        qty: float,
        price: float,
    ) -> None:
        base = str(body["_base"])
        quote = str(body["_quote"])
        if qty <= 0:
            return
        if body["side"] == "BUY":
            spent = qty * price if price else float(self._cfg(body).get("quote_size") or 0)
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
            if spend <= 0:
                return f"no {quote} from this tap to buy {symbol}"
            return self._order_body(opportunity, action, symbol, price, quote_size=spend)
        qty = _floor_qty(pocket.get(base, 0.0))
        if qty <= 0:
            return f"no {base} from this tap to sell — this tap does not sell coins you already hold"
        return self._order_body(opportunity, action, symbol, price, base_size=qty)

    async def execute(self, opportunity: Opportunity) -> list[Fill]:
        decision = self.risk.allow(opportunity.notional)
        if not decision.allowed:
            return self._blocked(opportunity, decision.reason)
        if not opportunity.executable:
            return await self.paper_fallback.execute(opportunity)
        coinbase_legs = [leg for leg in opportunity.legs if leg.venue == "coinbase" and leg.executable]
        if not coinbase_legs or len(coinbase_legs) != len(opportunity.legs):
            return await self.paper_fallback.execute(opportunity)
        _, first_quote = self._pair(coinbase_legs[0].symbol)
        if coinbase_legs[0].action != "buy" or first_quote != "USD":
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
        failed = False
        try:
            try:
                await self.refresh_balances(client)
            except Exception as exc:
                return self._blocked(opportunity, f"coinbase balance check failed: {exc}"[:200])
            self.risk.reserve_live(opportunity.notional)
            reserved = True
            first_cash = True
            for leg in coinbase_legs:
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
                            venue="coinbase",
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
                    failed = True
                    break
                short = self._enough_balance(sized, pocket)
                if short:
                    fills.append(
                        Fill(
                            venue="coinbase",
                            symbol=leg.symbol,
                            side=leg.action,
                            qty=0,
                            price=leg.price,
                            notional=opportunity.notional,
                            ts=time.time(),
                            paper=False,
                            opportunity_id=opportunity.id,
                            status="blocked",
                            note=short,
                        )
                    )
                    failed = True
                    break
                fill = await self._place_order(
                    client,
                    opportunity,
                    sized,
                    fallback_price=leg.price,
                    maker=self.maker_exits and sized["side"] == "SELL",
                )
                fills.append(fill)
                if fill.status != "filled" or fill.qty <= 0:
                    failed = True
                    break
                self._credit_pocket(pocket, last_px, sized, fill.qty, fill.price)
                if sized["side"] == "BUY" and str(sized["_quote"]) in STABLE:
                    first_cash = False
            leftover = await self._flatten_pocket(client, opportunity, pocket, last_px)
            fills.extend(leftover)
            realized = cash_pnl(fills)
            if any(item.status == "filled" and item.qty > 0 for item in fills):
                self.pnl += realized
                self.risk.record_pnl(realized)
            # Stay LIVE after a recovered tap. Kill only if this tap still holds
            # coins we could not sell back to USD — that is leftover risk, not paper mode.
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
        """True when this tap still holds sellable leftover crypto or USDC."""
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

    def _maker_limit_body(self, body: dict[str, Any], fallback_price: float) -> dict[str, Any]:
        ioc = self._cfg(body)
        limit_px = max(fallback_price, 0.0) * 1.0001
        order = {k: v for k, v in body.items() if not k.startswith("_")}
        order["order_configuration"] = {
            "limit_limit_gtc": {
                "base_size": str(ioc.get("base_size") or ""),
                "limit_price": f"{limit_px:.8f}".rstrip("0").rstrip("."),
                "post_only": True,
            }
        }
        return order

    async def _place_order(
        self,
        client: httpx.AsyncClient,
        opportunity: Opportunity,
        body: dict[str, Any],
        *,
        fallback_price: float,
        maker: bool = False,
    ) -> Fill:
        if maker and body.get("side") == "SELL" and fallback_price > 0:
            fill = await self._place_maker_then_market(client, opportunity, body, fallback_price)
            if fill is not None:
                return fill
        return await self._submit_order(client, opportunity, body, fallback_price)

    async def _place_maker_then_market(
        self,
        client: httpx.AsyncClient,
        opportunity: Opportunity,
        body: dict[str, Any],
        fallback_price: float,
    ) -> Fill | None:
        limit_body = dict(body)
        limit_body["order_configuration"] = self._maker_limit_body(body, fallback_price)["order_configuration"]
        fill = await self._submit_order(client, opportunity, limit_body, fallback_price, wait=True)
        expected = float(self._cfg(body).get("base_size") or 0)
        if fill.status == "filled" and fill.qty > 0 and (expected <= 0 or fill.qty + 1e-12 >= expected):
            if "maker" not in (fill.note or ""):
                fill.note = f"maker {fill.note}"
            return fill
        leftover = max(0.0, expected - (fill.qty if fill.status == "filled" else 0.0))
        if leftover > 1e-12:
            rest = dict(body)
            rest["order_configuration"] = {
                "market_market_ioc": {"base_size": self._fmt_size(leftover, str(body["_base"]))}
            }
            market = await self._submit_order(client, opportunity, rest, fallback_price)
            made = fill.qty if fill.status == "filled" else 0.0
            extra = market.qty if market.status == "filled" else 0.0
            combined = made + extra
            px = fallback_price
            if combined > 0:
                px = (
                    made * (fill.price or fallback_price) + extra * (market.price or fallback_price)
                ) / combined
            return Fill(
                venue="coinbase",
                symbol=body["product_id"],
                side="sell",
                qty=combined,
                price=px,
                notional=combined * px if combined else opportunity.notional,
                ts=time.time(),
                paper=False,
                opportunity_id=opportunity.id,
                status="filled" if combined > 0 else "error",
                note=f"{fill.note} · leftover market · {market.note}",
            )
        market = await self._submit_order(client, opportunity, body, fallback_price)
        market.note = f"maker wait expired · {market.note}"
        return market

    async def _submit_order(
        self,
        client: httpx.AsyncClient,
        opportunity: Opportunity,
        body: dict[str, Any],
        fallback_price: float,
        *,
        wait: bool = False,
    ) -> Fill:
        order = {k: v for k, v in body.items() if not k.startswith("_")}
        try:
            response = await self._request(client, "POST", "/api/v3/brokerage/orders", json_body=order)
            try:
                payload = response.json() if response.content else {}
            except Exception:
                payload = {"error_response": {"message": response.text[:200]}}
        except Exception as exc:
            return Fill(
                venue="coinbase",
                symbol=body["product_id"],
                side="buy" if body["side"] == "BUY" else "sell",
                qty=0,
                price=fallback_price,
                notional=opportunity.notional,
                ts=time.time(),
                paper=False,
                opportunity_id=opportunity.id,
                status="error",
                note=str(exc)[:240],
            )
        ok = response.status_code == 200 and bool(payload.get("success"))
        order_id = str((payload.get("success_response") or {}).get("order_id") or "")
        qty = 0.0
        price = fallback_price
        note = order_id or str(payload)[:240]
        if ok and order_id:
            expected = float(self._cfg(body).get("base_size") or self._cfg(body).get("quote_size") or 0)
            qty, price, status = await self._wait_fill(client, order_id, fallback_price, expected if wait else 0.0)
            price = price or fallback_price
            note = f"order {order_id}"
            if wait:
                note = f"maker {note}"
            if qty <= 0:
                ok = False
                note = f"order {order_id} returned no fill"
            elif wait and expected > 0 and qty + 1e-12 < expected and status not in {"FILLED", "CANCELLED", "EXPIRED"}:
                try:
                    await self._request(
                        client,
                        "POST",
                        "/api/v3/brokerage/orders/batch_cancel",
                        json_body={"order_ids": [order_id]},
                    )
                except Exception:
                    pass
                qty, price, _status = await self._lookup_order(client, order_id)
                price = price or fallback_price
        elif not ok:
            err = payload.get("error_response") or payload
            note = str(err)[:240]
        notional = qty * price if qty and price else opportunity.notional
        return Fill(
            venue="coinbase",
            symbol=body["product_id"],
            side="buy" if body["side"] == "BUY" else "sell",
            qty=qty,
            price=price,
            notional=notional,
            ts=time.time(),
            paper=False,
            opportunity_id=opportunity.id,
            status="filled" if ok else "error",
            note=note,
        )

    async def _wait_fill(
        self,
        client: httpx.AsyncClient,
        order_id: str,
        fallback_price: float,
        expected: float,
    ) -> tuple[float, float, str]:
        deadline = time.time() + (self.maker_wait_seconds if expected else 0.0)
        qty, price, status = await self._lookup_order(client, order_id)
        price = price or fallback_price
        while expected > 0 and time.time() < deadline:
            if status in {"FILLED", "CANCELLED", "EXPIRED", "FAILED"}:
                break
            if qty + 1e-12 >= expected:
                break
            await asyncio.sleep(0.35)
            qty, price, status = await self._lookup_order(client, order_id)
            price = price or fallback_price
        return qty, price, status

    async def _flatten_pocket(
        self,
        client: httpx.AsyncClient,
        opportunity: Opportunity,
        pocket: dict[str, float],
        last_px: dict[str, float],
    ) -> list[Fill]:
        """Sell leftover coins and USDC from this tap back to USD. Never sells the customer's bag."""
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
            body = self._order_body(opportunity, "sell", symbol, px or 0.0, base_size=qty)
            fill = await self._place_order(
                client, opportunity, body, fallback_price=px, maker=self.maker_exits
            )
            fill.note = f"flatten to USD · {fill.note}".strip(" ·")
            out.append(fill)
            if fill.status == "filled" and fill.qty > 0:
                self._credit_pocket(pocket, last_px, body, fill.qty, fill.price)
            else:
                fill.note = f"could not sell leftover {asset} back to USD · {fill.note}"
        return out

    async def _lookup_order(self, client: httpx.AsyncClient, order_id: str) -> tuple[float, float, str]:
        try:
            response = await self._request(client, "GET", f"/api/v3/brokerage/orders/historical/{order_id}")
            row = (response.json() or {}).get("order") or {}
            qty = float(row.get("filled_size") or 0)
            price = float(row.get("average_filled_price") or 0)
            status = str(row.get("status") or "")
            return qty, price, status
        except Exception:
            return 0.0, 0.0, ""

    async def _lookup_fill(self, client: httpx.AsyncClient, order_id: str) -> tuple[float, float]:
        qty, price, _status = await self._lookup_order(client, order_id)
        return qty, price
