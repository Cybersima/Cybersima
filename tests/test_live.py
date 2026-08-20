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
async def test_router_keeps_cross_venue_on_paper() -> None:
    risk = RiskManager(cooldown_seconds=0)
    paper = PaperBroker(risk)
    coinbase = LiveCoinbaseBroker(risk, "k", _ecdsa_pem(), paper)
    router = LiveRouter(paper, coinbase=coinbase)
    fills = await router.execute(_opp(venues=("coinbase", "kraken")))
    assert fills[0].paper is True
    assert fills[0].status == "filled"
    assert "Cross-venue" in fills[0].note or "paper:" in fills[0].note


@pytest.mark.asyncio
async def test_coinbase_market_order_uses_balances() -> None:
    pem = _ecdsa_pem()

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
            return httpx.Response(
                200,
                json={"success": True, "success_response": {"order_id": "oid-1"}},
            )
        if "historical" in path:
            return httpx.Response(
                200,
                json={"order": {"filled_size": "0.0001", "average_filled_price": "97000"}},
            )
        return httpx.Response(404, json={"message": path})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.coinbase.com")
    risk = RiskManager(cooldown_seconds=0, max_notional_usdt=25)
    paper = PaperBroker(risk)
    broker = LiveCoinbaseBroker(risk, "organizations/x/apiKeys/y", pem, paper, client=client)
    fills = await broker.execute(_opp(notional=10))
    await client.aclose()
    assert [row.status for row in fills] == ["filled", "filled"]
    assert all(row.paper is False for row in fills)
    assert broker.pnl > 0


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
async def test_paper_fill_type_still_works() -> None:
    # Keep a live Fill shape available for reports.
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
