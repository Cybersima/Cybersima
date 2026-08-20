from __future__ import annotations

import time
import uuid
from typing import Any

import httpx

from pulsearb.engine.broker import Broker, PaperBroker
from pulsearb.engine.coinbase_auth import HOST, build_rest_jwt
from pulsearb.engine.risk import RiskManager
from pulsearb.feeds.headers import HTTP_HEADERS
from pulsearb.models import Fill, Opportunity
from pulsearb.symbols import split_pair


class LiveCoinbaseBroker(Broker):
    """Places Coinbase Advanced Trade market IOC orders. Same-venue legs only."""

    def __init__(
        self,
        risk: RiskManager,
        api_key: str,
        api_secret: str,
        paper_fallback: PaperBroker,
        rest_url: str = "https://api.coinbase.com",
        client: httpx.AsyncClient | None = None,
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

    def _order_body(self, opportunity: Opportunity, action: str, symbol: str, price: float) -> dict[str, Any]:
        try:
            base, quote = split_pair(symbol)
        except ValueError:
            base, quote = symbol, "USD"
        side = "BUY" if action == "buy" else "SELL"
        config: dict[str, str] = {}
        if side == "BUY":
            config["quote_size"] = f"{opportunity.notional:.2f}"
        else:
            qty = opportunity.notional / price if price else 0.0
            config["base_size"] = f"{qty:.8f}".rstrip("0").rstrip(".")
        return {
            "client_order_id": str(uuid.uuid4()),
            "product_id": symbol,
            "side": side,
            "order_configuration": {"market_market_ioc": config},
            "_base": base,
            "_quote": quote,
        }

    def _enough_balance(self, body: dict[str, Any]) -> str | None:
        ioc = body["order_configuration"]["market_market_ioc"]
        if body["side"] == "BUY":
            need = float(ioc["quote_size"])
            have = self.balances.get(str(body["_quote"]), 0.0)
            if have + 1e-9 < need:
                return f"insufficient {body['_quote']} ({have:.4f} < {need:.2f})"
        else:
            need = float(ioc["base_size"])
            have = self.balances.get(str(body["_base"]), 0.0)
            if have + 1e-9 < need:
                return f"insufficient {body['_base']} ({have:.8f} < {need})"
        return None

    async def execute(self, opportunity: Opportunity) -> list[Fill]:
        decision = self.risk.allow(opportunity.notional)
        if not decision.allowed:
            return self._blocked(opportunity, decision.reason)
        if not opportunity.executable:
            return await self.paper_fallback.execute(opportunity)
        coinbase_legs = [leg for leg in opportunity.legs if leg.venue == "coinbase" and leg.executable]
        if not coinbase_legs or len(coinbase_legs) != len(opportunity.legs):
            return await self.paper_fallback.execute(opportunity)

        own_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=8.0)
        self.risk.on_submit()
        reserved = False
        fills: list[Fill] = []
        try:
            try:
                await self.refresh_balances(client)
            except Exception as exc:
                return self._blocked(opportunity, f"coinbase balance check failed: {exc}"[:200])
            self.risk.reserve_live(opportunity.notional)
            reserved = True
            for leg in coinbase_legs:
                body = self._order_body(opportunity, leg.action, leg.symbol, leg.price)
                short = self._enough_balance(body)
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
                    if any(item.status == "filled" for item in fills[:-1]):
                        self.risk.kill()
                    break
                order = {k: v for k, v in body.items() if not k.startswith("_")}
                try:
                    response = await self._request(client, "POST", "/api/v3/brokerage/orders", json_body=order)
                    try:
                        payload = response.json() if response.content else {}
                    except Exception:
                        payload = {"error_response": {"message": response.text[:200]}}
                except Exception as exc:
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
                            status="error",
                            note=str(exc)[:240],
                        )
                    )
                    self.risk.kill()
                    break
                ok = response.status_code == 200 and bool(payload.get("success"))
                order_id = str((payload.get("success_response") or {}).get("order_id") or "")
                qty = 0.0
                price = leg.price
                note = order_id or str(payload)[:240]
                if ok and order_id:
                    filled = await self._lookup_fill(client, order_id)
                    qty = filled[0]
                    price = filled[1] or price
                    note = f"order {order_id}"
                elif not ok:
                    err = payload.get("error_response") or payload
                    note = str(err)[:240]
                    self.risk.kill()
                fills.append(
                    Fill(
                        venue="coinbase",
                        symbol=leg.symbol,
                        side=leg.action,
                        qty=qty,
                        price=price,
                        notional=opportunity.notional,
                        ts=time.time(),
                        paper=False,
                        opportunity_id=opportunity.id,
                        status="filled" if ok else "error",
                        note=note,
                    )
                )
                if not ok:
                    break
            if fills and all(item.status == "filled" for item in fills):
                expected = opportunity.notional * (opportunity.net_edge_bps / 10_000)
                self.pnl += expected
                self.risk.record_pnl(expected)
        finally:
            if reserved and not any(item.status == "filled" for item in fills):
                self.risk.release_live(opportunity.notional)
            self.risk.on_complete()
            if own_client:
                await client.aclose()
        self.fills.extend(fills)
        return fills

    async def _lookup_fill(self, client: httpx.AsyncClient, order_id: str) -> tuple[float, float]:
        try:
            response = await self._request(client, "GET", f"/api/v3/brokerage/orders/historical/{order_id}")
            row = (response.json() or {}).get("order") or {}
            qty = float(row.get("filled_size") or 0)
            price = float(row.get("average_filled_price") or 0)
            return qty, price
        except Exception:
            return 0.0, 0.0
