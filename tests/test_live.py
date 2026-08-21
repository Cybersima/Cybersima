import base64
import json

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import ECDSA
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from pulsearb.config import AppConfig
from pulsearb.engine.broker import LiveRouter, PaperBroker
from pulsearb.engine.coinbase_auth import build_rest_jwt
from pulsearb.engine.coinbase_live import LiveCoinbaseBroker
from pulsearb.engine.keys import load_coinbase_credentials
from pulsearb.engine.risk import RiskManager
from pulsearb.engine.runner import Engine
from pulsearb.models import Fill, Leg, Opportunity, OpportunityKind


def _b64url_decode(part: str) -> bytes:
    pad = "=" * ((4 - len(part) % 4) % 4)
    return base64.urlsafe_b64decode(part + pad)


def test_jwt_es256_verifies_with_public_key() -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    token = build_rest_jwt("organizations/test/apiKeys/abc", pem, "GET", "/api/v3/brokerage/accounts")
    header_b64, payload_b64, sig_b64 = token.split(".")
    header = json.loads(_b64url_decode(header_b64))
    payload = json.loads(_b64url_decode(payload_b64))
    assert header["alg"] == "ES256"
    assert header["kid"] == "organizations/test/apiKeys/abc"
    assert payload["iss"] == "cdp"
    assert payload["uri"].endswith("/api/v3/brokerage/accounts")
    sig = _b64url_decode(sig_b64)
    size = 32
    der = encode_dss_signature(int.from_bytes(sig[:size], "big"), int.from_bytes(sig[size:], "big"))
    key.public_key().verify(der, f"{header_b64}.{payload_b64}".encode(), ECDSA(hashes.SHA256()))


def test_jwt_ed25519_has_three_parts() -> None:
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    token = build_rest_jwt("organizations/test/apiKeys/ed", pem, "GET", "/api/v3/brokerage/accounts")
    assert token.count(".") == 2
    header = json.loads(_b64url_decode(token.split(".")[0]))
    assert header["alg"] == "EdDSA"


def _ecdsa_pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def _tri_opp(*, notional: float = 10) -> Opportunity:
    return Opportunity(
        kind=OpportunityKind.TRIANGULAR,
        edge_bps=40,
        net_edge_bps=28,
        notional=notional,
        legs=[
            Leg("buy", "coinbase", "BTC-USD", 97000, True),
            Leg("buy", "coinbase", "ETH-BTC", 0.019, True),
            Leg("sell", "coinbase", "ETH-USD", 2000, True),
        ],
        summary="USD → BTC → ETH → USD on coinbase",
        executable=True,
        ts=0,
        id="live-tri-1",
    )


def _opp(*, venues: tuple[str, str] = ("coinbase", "coinbase"), notional: float = 10) -> Opportunity:
    return Opportunity(
        kind=OpportunityKind.TRIANGULAR if venues[0] == venues[1] else OpportunityKind.CROSS_VENUE,
        edge_bps=40,
        net_edge_bps=28,
        notional=notional,
        legs=[
            Leg("buy", venues[0], "BTC-USD", 97000, True),
            Leg("sell", venues[1], "ETH-USD" if venues[0] == venues[1] else "BTC-USD", 2000 if venues[0] == venues[1] else 98100, True),
        ],
        summary="test",
        executable=True,
        ts=0,
        id="live-1",
    )


def _disloc_opp(*, notional: float = 10) -> Opportunity:
    return Opportunity(
        kind=OpportunityKind.DISLOCATION,
        edge_bps=110,
        net_edge_bps=40,
        notional=notional,
        legs=[
            Leg("buy", "coinbase", "BTC-USD", 97000, True),
            Leg("sell", "coinbase", "BTC-USDC", 98100, True),
        ],
        summary="BTC-USD vs BTC-USDC on coinbase",
        executable=True,
        ts=0,
        id="live-disloc-1",
    )


def test_jwt_is_three_part_token() -> None:
    token = build_rest_jwt("organizations/test/apiKeys/abc", _ecdsa_pem(), "GET", "/api/v3/brokerage/accounts")
    assert token.count(".") == 2


def test_load_coinbase_json_file(tmp_path) -> None:
    path = tmp_path / "coinbase.json"
    path.write_text(json.dumps({"name": "organizations/x/apiKeys/y", "privateKey": _ecdsa_pem()}), encoding="utf-8")
    creds = load_coinbase_credentials(cwd=tmp_path, json_path=path)
    assert creds is not None
    assert creds[0].endswith("/y")


def test_live_disabled_by_default() -> None:
    assert AppConfig().live_enabled() is False
    assert AppConfig().live_notional() == 250


def test_live_notional_caps_when_armed(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys" / "coinbase.json").write_text(
        json.dumps({"name": "organizations/x/apiKeys/y", "privateKey": _ecdsa_pem()}),
        encoding="utf-8",
    )
    monkeypatch.setenv("PULSEARB_EXECUTION_MODE", "live")
    monkeypatch.setenv("PULSEARB_LIVE_CONFIRM", "I_UNDERSTAND_THE_RISK")
    config = AppConfig()
    assert config.live_enabled() is True
    assert config.live_notional() == 25
    assert config.live_venue_names() == ["coinbase"]
    engine = Engine(config)
    assert isinstance(engine.broker, LiveRouter)
    assert engine.broker.coinbase is not None


@pytest.mark.asyncio
async def test_router_blocks_cross_venue_while_live() -> None:
    risk = RiskManager(cooldown_seconds=0)
    paper = PaperBroker(risk)
    coinbase = LiveCoinbaseBroker(risk, "k", _ecdsa_pem(), paper)
    router = LiveRouter(paper, coinbase=coinbase)
    fills = await router.execute(_opp(venues=("coinbase", "kraken")))
    assert fills[0].paper is False
    assert fills[0].status == "blocked"
    assert "holding" in fills[0].note.lower() or "two exchanges" in fills[0].note.lower()


def _fill_from_order(body: dict) -> tuple[str, str]:
    prices = {
        "BTC-USD": 97000.0,
        "ETH-BTC": 0.019,
        "ETH-USD": 2000.0,
        "BTC-USDC": 98100.0,
        "USDC-USD": 1.0,
    }
    product = body["product_id"]
    side = body["side"]
    ioc = body["order_configuration"]["market_market_ioc"]
    px = prices[product]
    if side == "BUY":
        qty = float(ioc["quote_size"]) / px
    else:
        qty = float(ioc["base_size"])
    return f"{qty:.8f}", f"{px:.8f}"


@pytest.mark.asyncio
async def test_coinbase_round_trip_uses_usd_and_sells_back() -> None:
    pem = _ecdsa_pem()
    posted: list[dict] = []
    orders: dict[str, dict] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/accounts"):
            return httpx.Response(
                200,
                json={"accounts": [{"currency": "USD", "available_balance": {"value": "100.00"}}]},
            )
        if path.endswith("/orders") and request.method == "POST":
            body = json.loads(request.content)
            oid = f"oid-{len(orders) + 1}"
            orders[oid] = body
            posted.append(body)
            return httpx.Response(200, json={"success": True, "success_response": {"order_id": oid}})
        if "historical" in path:
            oid = path.rstrip("/").split("/")[-1]
            qty, px = _fill_from_order(orders[oid])
            return httpx.Response(200, json={"order": {"filled_size": qty, "average_filled_price": px}})
        return httpx.Response(404, json={"message": path})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.coinbase.com")
    risk = RiskManager(cooldown_seconds=0, max_notional_usdt=25)
    paper = PaperBroker(risk)
    broker = LiveCoinbaseBroker(risk, "organizations/x/apiKeys/y", pem, paper, client=client)
    fills = await broker.execute(_tri_opp(notional=10))
    await client.aclose()
    assert [row.status for row in fills] == ["filled", "filled", "filled"]
    assert [row.side for row in fills] == ["buy", "buy", "sell"]
    assert [row.symbol for row in fills] == ["BTC-USD", "ETH-BTC", "ETH-USD"]
    assert posted[0]["order_configuration"]["market_market_ioc"]["quote_size"] == "10.00"
    assert "base_size" in posted[1]["order_configuration"]["market_market_ioc"] or posted[1]["side"] == "BUY"
    assert posted[2]["side"] == "SELL"
    assert all(row.paper is False for row in fills)
    assert broker.pnl > 0
    assert risk.killed is False


@pytest.mark.asyncio
async def test_coinbase_does_not_sell_coins_already_held() -> None:
    pem = _ecdsa_pem()
    posted: list[dict] = []
    orders: dict[str, dict] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/accounts"):
            return httpx.Response(
                200,
                json={
                    "accounts": [
                        {"currency": "USD", "available_balance": {"value": "100.00"}},
                        {"currency": "ETH", "available_balance": {"value": "2.0"}},
                    ]
                },
            )
        if path.endswith("/orders") and request.method == "POST":
            body = json.loads(request.content)
            oid = f"oid-{len(orders) + 1}"
            orders[oid] = body
            posted.append(body)
            return httpx.Response(200, json={"success": True, "success_response": {"order_id": oid}})
        if "historical" in path:
            oid = path.rstrip("/").split("/")[-1]
            qty, px = _fill_from_order(orders[oid])
            return httpx.Response(200, json={"order": {"filled_size": qty, "average_filled_price": px}})
        return httpx.Response(404, json={"message": path})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.coinbase.com")
    risk = RiskManager(cooldown_seconds=0, max_notional_usdt=25)
    paper = PaperBroker(risk)
    broker = LiveCoinbaseBroker(risk, "organizations/x/apiKeys/y", pem, paper, client=client)
    fills = await broker.execute(_opp(notional=10))
    await client.aclose()
    assert fills[0].status == "filled"
    assert fills[0].side == "buy"
    assert any("already hold" in (row.note or "") for row in fills) or any(row.status == "blocked" for row in fills)
    eth_sells = [row for row in posted if row.get("product_id") == "ETH-USD" and row.get("side") == "SELL"]
    assert eth_sells == []
    btc_flatten = [row for row in posted if row.get("product_id") == "BTC-USD" and row.get("side") == "SELL"]
    assert btc_flatten
    assert risk.killed is False


@pytest.mark.asyncio
async def test_coinbase_blocks_without_cash() -> None:
    pem = _ecdsa_pem()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"accounts": [{"currency": "USD", "available_balance": {"value": "0.01"}}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.coinbase.com")
    risk = RiskManager(cooldown_seconds=0, max_notional_usdt=25)
    paper = PaperBroker(risk)
    broker = LiveCoinbaseBroker(risk, "organizations/x/apiKeys/y", pem, paper, client=client)
    fills = await broker.execute(_opp(notional=10))
    await client.aclose()
    assert fills[0].status == "blocked"
    assert "insufficient" in fills[0].note


@pytest.mark.asyncio
async def test_accounts_jwt_omits_query_string() -> None:
    pem = _ecdsa_pem()
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        seen["query"] = request.url.query.decode() if isinstance(request.url.query, bytes) else str(request.url.query)
        return httpx.Response(200, json={"accounts": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.coinbase.com")
    risk = RiskManager(cooldown_seconds=0)
    broker = LiveCoinbaseBroker(risk, "organizations/x/apiKeys/y", pem, PaperBroker(risk), client=client)
    await broker.refresh_balances(client)
    await client.aclose()
    token = seen["auth"].split(" ", 1)[1]
    payload = json.loads(_b64url_decode(token.split(".")[1]))
    assert payload["uri"] == "GET api.coinbase.com/api/v3/brokerage/accounts"
    assert "limit=250" in seen["query"]


@pytest.mark.asyncio
async def test_refresh_balances_empty_401() -> None:
    pem = _ecdsa_pem()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, content=b"")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.coinbase.com")
    risk = RiskManager(cooldown_seconds=0)
    broker = LiveCoinbaseBroker(risk, "organizations/x/apiKeys/y", pem, PaperBroker(risk), client=client)
    with pytest.raises(RuntimeError, match="HTTP 401"):
        await broker.refresh_balances(client)
    await client.aclose()


@pytest.mark.asyncio
async def test_paper_fill_type_still_works() -> None:
    fill = Fill(
        venue="coinbase",
        symbol="BTC-USD",
        side="buy",
        qty=0.001,
        price=1,
        notional=10,
        ts=0,
        paper=False,
        opportunity_id="x",
        status="filled",
    )
    assert fill.paper is False


@pytest.mark.asyncio
async def test_unarmed_router_stays_on_paper() -> None:
    risk = RiskManager(cooldown_seconds=0)
    paper = PaperBroker(risk)
    coinbase = LiveCoinbaseBroker(risk, "k", _ecdsa_pem(), paper)
    router = LiveRouter(paper, coinbase=coinbase, armed=False)
    fills = await router.execute(_tri_opp(notional=10))
    assert fills[0].paper is True
    assert fills[0].status == "filled"
    assert router.paper is True


@pytest.mark.asyncio
async def test_engine_toggles_paper_and_live(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys" / "coinbase.json").write_text(
        json.dumps({"name": "organizations/x/apiKeys/y", "privateKey": _ecdsa_pem()}),
        encoding="utf-8",
    )

    async def fake_ready(*_args, **_kwargs):
        return {"ok": True, "ready": True, "note": "Ready", "checks": []}

    monkeypatch.setattr("pulsearb.engine.live_ready.assess_live_ready", fake_ready)
    engine = Engine(AppConfig())
    assert engine.live_active() is False
    denied = await engine.set_execution("live")
    assert denied["ok"] is False
    armed = await engine.set_execution("live", confirm=engine.config.live_confirm_phrase)
    assert armed["ok"] is True
    assert engine.live_active() is True
    assert engine.desk.live is True
    assert engine.desk.auto_invest is False
    assert isinstance(engine.broker, LiveRouter)
    assert engine.broker.armed is True
    paper = await engine.set_execution("paper")
    assert paper["ok"] is True
    assert engine.live_active() is False
    assert engine.desk.live is False
    assert engine.broker.armed is False


@pytest.mark.asyncio
async def test_recovered_flatten_does_not_kill_or_disarm() -> None:
    pem = _ecdsa_pem()
    orders: dict[str, dict] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/accounts"):
            return httpx.Response(
                200,
                json={"accounts": [{"currency": "USD", "available_balance": {"value": "80.00"}}]},
            )
        if path.endswith("/orders") and request.method == "POST":
            body = json.loads(request.content)
            oid = f"oid-{len(orders) + 1}"
            orders[oid] = body
            return httpx.Response(200, json={"success": True, "success_response": {"order_id": oid}})
        if "historical" in path:
            oid = path.rstrip("/").split("/")[-1]
            qty, px = _fill_from_order(orders[oid])
            return httpx.Response(200, json={"order": {"filled_size": qty, "average_filled_price": px}})
        return httpx.Response(404, json={"message": path})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.coinbase.com")
    risk = RiskManager(cooldown_seconds=0, max_notional_usdt=25)
    paper = PaperBroker(risk)
    broker = LiveCoinbaseBroker(risk, "organizations/x/apiKeys/y", pem, paper, client=client)
    fills = await broker.execute(_opp(notional=10))
    await client.aclose()
    assert any(row.status == "filled" and row.side == "buy" for row in fills)
    assert any("already hold" in (row.note or "") or row.status == "blocked" for row in fills)
    assert any("flatten" in (row.note or "") for row in fills)
    assert risk.killed is False


@pytest.mark.asyncio
async def test_stuck_leftover_still_kills() -> None:
    pem = _ecdsa_pem()
    orders: dict[str, dict] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/accounts"):
            return httpx.Response(
                200,
                json={"accounts": [{"currency": "USD", "available_balance": {"value": "80.00"}}]},
            )
        if path.endswith("/orders") and request.method == "POST":
            body = json.loads(request.content)
            if body.get("product_id") == "BTC-USD" and body.get("side") == "SELL":
                return httpx.Response(200, json={"success": False, "error_response": {"message": "could not flatten"}})
            oid = f"oid-{len(orders) + 1}"
            orders[oid] = body
            return httpx.Response(200, json={"success": True, "success_response": {"order_id": oid}})
        if "historical" in path:
            oid = path.rstrip("/").split("/")[-1]
            qty, px = _fill_from_order(orders[oid])
            return httpx.Response(200, json={"order": {"filled_size": qty, "average_filled_price": px}})
        return httpx.Response(404, json={"message": path})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.coinbase.com")
    risk = RiskManager(cooldown_seconds=0, max_notional_usdt=25)
    paper = PaperBroker(risk)
    broker = LiveCoinbaseBroker(risk, "organizations/x/apiKeys/y", pem, paper, client=client)
    await broker.execute(_opp(notional=10))
    await client.aclose()
    assert risk.killed is True


def test_snapshot_shows_cash_and_trades_on_paper() -> None:
    engine = Engine(AppConfig())
    engine.paper.fills = []
    snap = engine.snapshot()
    assert "cash_usd" in snap["stats"]
    assert "trades" in snap
    assert snap["stats"]["live_armed"] is False
    assert snap["stats"]["execution"] == "paper"


@pytest.mark.asyncio
async def test_coinbase_dislocation_buys_usd_sells_usdc_flattens() -> None:
    pem = _ecdsa_pem()
    posted: list[dict] = []
    orders: dict[str, dict] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/accounts"):
            return httpx.Response(
                200,
                json={"accounts": [{"currency": "USD", "available_balance": {"value": "100.00"}}]},
            )
        if path.endswith("/orders") and request.method == "POST":
            body = json.loads(request.content)
            oid = f"oid-{len(orders) + 1}"
            orders[oid] = body
            posted.append(body)
            return httpx.Response(200, json={"success": True, "success_response": {"order_id": oid}})
        if "historical" in path:
            oid = path.rstrip("/").split("/")[-1]
            qty, px = _fill_from_order(orders[oid])
            return httpx.Response(200, json={"order": {"filled_size": qty, "average_filled_price": px}})
        return httpx.Response(404, json={"message": path})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.coinbase.com")
    risk = RiskManager(cooldown_seconds=0, max_notional_usdt=25)
    paper = PaperBroker(risk)
    broker = LiveCoinbaseBroker(risk, "organizations/x/apiKeys/y", pem, paper, client=client)
    fills = await broker.execute(_disloc_opp(notional=10))
    await client.aclose()
    assert [row.symbol for row in fills if row.status == "filled"][:2] == ["BTC-USD", "BTC-USDC"]
    assert any(row.symbol == "USDC-USD" for row in fills)
    assert all(row.paper is False for row in fills if row.status == "filled")
    assert posted[0]["side"] == "BUY"
    assert posted[1]["side"] == "SELL"
    assert risk.killed is False


@pytest.mark.asyncio
async def test_live_invest_rejects_cross_venue(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys" / "coinbase.json").write_text(
        json.dumps({"name": "organizations/x/apiKeys/y", "privateKey": _ecdsa_pem()}),
        encoding="utf-8",
    )

    async def fake_ready(*_args, **_kwargs):
        return {"ok": True, "ready": True, "note": "Ready", "checks": []}

    monkeypatch.setattr("pulsearb.engine.live_ready.assess_live_ready", fake_ready)
    engine = Engine(AppConfig())
    armed = await engine.set_execution("live", confirm=engine.config.live_confirm_phrase)
    assert armed["ok"] is True
    opp = _opp(venues=("coinbase", "kraken"))
    engine.by_id[opp.id] = opp
    result = await engine.invest(opp.id)
    assert result["ok"] is False
    assert "coinbase" in result["error"].lower()


def _kraken_secret() -> str:
    return base64.b64encode(b"kraken-secret-bytes-32!!!!!!!!").decode()


def _kraken_tri(*, notional: float = 10) -> Opportunity:
    return Opportunity(
        kind=OpportunityKind.TRIANGULAR,
        edge_bps=40,
        net_edge_bps=28,
        notional=notional,
        legs=[
            Leg("buy", "kraken", "XBTUSD", 97000, True),
            Leg("buy", "kraken", "ETHXBT", 0.019, True),
            Leg("sell", "kraken", "ETHUSD", 2000, True),
        ],
        summary="USD → BTC → ETH → USD on kraken",
        executable=True,
        ts=0,
        id="live-kraken-1",
    )


@pytest.mark.asyncio
async def test_kraken_round_trip_uses_usd(tmp_path) -> None:
    from pulsearb.engine.kraken_live import LiveKrakenBroker

    secret = _kraken_secret()
    orders: dict[str, dict] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/Balance"):
            return httpx.Response(200, json={"error": [], "result": {"ZUSD": "80.00"}})
        if path.endswith("/AddOrder"):
            oid = f"TX-{len(orders) + 1}"
            orders[oid] = {"path": path}
            return httpx.Response(200, json={"error": [], "result": {"txid": [oid]}})
        if path.endswith("/QueryOrders"):
            oid = list(orders)[-1]
            prices = {"TX-1": ("0.00010309", "97000"), "TX-2": ("0.005425", "0.019"), "TX-3": ("0.005425", "2000")}
            vol, px = prices.get(oid, ("0.0001", "97000"))
            return httpx.Response(200, json={"error": [], "result": {oid: {"vol_exec": vol, "avg_price": px}}})
        return httpx.Response(200, json={"error": ["unknown"], "result": {}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.kraken.com")
    risk = RiskManager(cooldown_seconds=0, max_notional_usdt=25)
    paper = PaperBroker(risk)
    broker = LiveKrakenBroker(risk, "kraken-key", secret, paper, client=client)
    fills = await broker.execute(_kraken_tri(notional=10))
    await client.aclose()
    assert any(row.status == "filled" and row.side == "buy" for row in fills)
    assert all(row.venue == "kraken" for row in fills if row.status == "filled")
    assert risk.killed is False


def test_load_kraken_json_file(tmp_path) -> None:
    from pulsearb.engine.keys import load_kraken_credentials

    path = tmp_path / "kraken.json"
    path.write_text(json.dumps({"key": "abc", "secret": _kraken_secret()}), encoding="utf-8")
    creds = load_kraken_credentials(cwd=tmp_path, json_path=path)
    assert creds is not None
    assert creds[0] == "abc"


def test_live_notional_caps_when_kraken_armed(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys" / "kraken.json").write_text(
        json.dumps({"key": "abc", "secret": _kraken_secret()}),
        encoding="utf-8",
    )
    monkeypatch.setenv("PULSEARB_EXECUTION_MODE", "live")
    monkeypatch.setenv("PULSEARB_LIVE_CONFIRM", "I_UNDERSTAND_THE_RISK")
    config = AppConfig()
    assert config.live_enabled() is True
    assert config.live_venue_names() == ["kraken"]
    engine = Engine(config)
    assert isinstance(engine.broker, LiveRouter)
    assert engine.broker.kraken is not None
    assert engine.desk.live_venue == "kraken"

