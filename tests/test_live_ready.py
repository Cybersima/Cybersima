import json

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from pulsearb.cli import main
from pulsearb.config import AppConfig
from pulsearb.engine.live_ready import assess_live_ready
from pulsearb.engine.runner import Engine


def _ecdsa_pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def _write_keys(tmp_path, pem: str | None = None) -> None:
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys" / "coinbase.json").write_text(
        json.dumps({"name": "organizations/x/apiKeys/y", "privateKey": pem or _ecdsa_pem()}),
        encoding="utf-8",
    )


def _ids(report: dict) -> dict[str, dict]:
    return {row["id"]: row for row in report["checks"]}


@pytest.mark.asyncio
async def test_live_ready_missing_keys(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    report = await assess_live_ready(AppConfig(), cwd=tmp_path, ping=False)
    by_id = _ids(report)
    assert report["ready"] is False
    assert by_id["keys_file"]["ok"] is False
    assert by_id["keys_file"]["status"] == "fail"
    assert by_id["keys_parse"]["status"] == "wait"
    assert by_id["coinbase_ping"]["status"] == "wait"
    assert by_id["usd_cash"]["status"] == "wait"
    assert "key file is missing" in report["note"]
    assert by_id["auto_off"]["ok"] is True


@pytest.mark.asyncio
async def test_live_ready_bad_json(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys" / "coinbase.json").write_text("{not-json", encoding="utf-8")
    report = await assess_live_ready(AppConfig(), cwd=tmp_path, ping=False)
    assert report["ready"] is False
    assert _ids(report)["keys_parse"]["ok"] is False
    assert _ids(report)["key_sign"]["status"] == "wait"


@pytest.mark.asyncio
async def test_live_ready_ping_and_cash(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_keys(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"accounts": [{"currency": "USD", "available_balance": {"value": "40.00"}}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.coinbase.com")
    report = await assess_live_ready(AppConfig(), cwd=tmp_path, client=client, ping=True)
    await client.aclose()
    by_id = _ids(report)
    assert by_id["keys_file"]["ok"] is True
    assert by_id["keys_parse"]["ok"] is True
    assert by_id["key_sign"]["ok"] is True
    assert by_id["coinbase_ping"]["ok"] is True
    assert by_id["usd_cash"]["ok"] is True
    assert report["ready"] is True
    assert report["cash"] == 40


@pytest.mark.asyncio
async def test_live_ready_short_cash(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_keys(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"accounts": [{"currency": "USD", "available_balance": {"value": "1.00"}}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.coinbase.com")
    report = await assess_live_ready(AppConfig(), cwd=tmp_path, client=client, ping=True)
    await client.aclose()
    assert report["ready"] is False
    assert _ids(report)["usd_cash"]["ok"] is False


@pytest.mark.asyncio
async def test_live_ready_ping_401_waits_on_cash(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_keys(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, content=b"")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.coinbase.com")
    report = await assess_live_ready(AppConfig(), cwd=tmp_path, client=client, ping=True)
    await client.aclose()
    by_id = _ids(report)
    assert report["ready"] is False
    assert by_id["key_sign"]["ok"] is True
    assert by_id["coinbase_ping"]["ok"] is False
    assert "401" in by_id["coinbase_ping"]["detail"]
    assert by_id["usd_cash"]["status"] == "wait"


def test_check_live_cli_exits_not_ready(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as caught:
        main(["--check-live"])
    assert caught.value.code == 1


def test_live_engine_rejects_auto(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_keys(tmp_path)
    monkeypatch.setenv("PULSEARB_EXECUTION_MODE", "live")
    monkeypatch.setenv("PULSEARB_LIVE_CONFIRM", "I_UNDERSTAND_THE_RISK")
    engine = Engine(AppConfig())
    assert engine.desk.live is True
    desk = engine.apply_desk({"auto_invest": True, "notional": 10})
    assert desk["auto_invest"] is False
    assert desk["auto_allowed"] is False
    assert engine.desk.auto_invest is False
