"""Preflight checks before real Coinbase orders."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from pulsearb.branding import PRODUCT
from pulsearb.config import AppConfig
from pulsearb.engine.broker import PaperBroker
from pulsearb.engine.coinbase_auth import build_rest_jwt
from pulsearb.engine.coinbase_live import LiveCoinbaseBroker
from pulsearb.engine.keys import load_coinbase_credentials, load_coinbase_json
from pulsearb.engine.risk import RiskManager

QUOTE_CASH = ("USD", "USDC", "USDT")
KEY_HELP = "https://portal.cdp.coinbase.com/projects/api-keys"


def _check(
    check_id: str,
    label: str,
    ok: bool,
    detail: str,
    *,
    required: bool = True,
    status: str | None = None,
) -> dict[str, Any]:
    if status is None:
        status = "ok" if ok else "fail"
    return {
        "id": check_id,
        "label": label,
        "ok": bool(ok),
        "status": status,
        "detail": detail,
        "required": required,
    }


def _wait(check_id: str, label: str, detail: str) -> dict[str, Any]:
    return _check(check_id, label, True, detail, required=False, status="wait")


def keys_file_path(config: AppConfig, cwd: Path | None = None) -> Path:
    if config.env.coinbase_api_json:
        return Path(config.env.coinbase_api_json)
    return (cwd or Path.cwd()) / "keys" / "coinbase.json"


def quote_cash(balances: dict[str, float]) -> float:
    return sum(float(balances.get(asset, 0) or 0) for asset in QUOTE_CASH)


async def ping_coinbase_accounts(
    api_key: str,
    api_secret: str,
    *,
    rest_url: str = "https://api.coinbase.com",
    client: httpx.AsyncClient | None = None,
) -> tuple[dict[str, float], str | None]:
    broker = LiveCoinbaseBroker(
        risk=RiskManager(),
        api_key=api_key,
        api_secret=api_secret,
        paper_fallback=PaperBroker(RiskManager()),
        rest_url=rest_url,
        client=client,
    )
    try:
        balances = await broker.refresh_balances(client)
        return balances, None
    except Exception as exc:
        return {}, str(exc)[:240]


async def assess_live_ready(
    config: AppConfig | None = None,
    *,
    cwd: Path | None = None,
    client: httpx.AsyncClient | None = None,
    ping: bool = True,
    killed: bool = False,
) -> dict[str, Any]:
    config = config or AppConfig()
    root = cwd or Path.cwd()
    path = keys_file_path(config, root)
    cap = float(config.risk.get("live_max_notional_usdt", 25))
    checks: list[dict[str, Any]] = []
    balances: dict[str, float] = {}
    env_creds = bool(config.env.coinbase_api_key and config.env.coinbase_api_secret)
    exists = path.is_file()
    file_ok = exists or env_creds
    if exists:
        file_detail = f"Found {path}"
    elif env_creds:
        file_detail = "Using COINBASE_API_KEY from the environment."
    else:
        file_detail = (
            f"No file yet. Create a Secret API key at {KEY_HELP} "
            f"(View + Trade, ECDSA), click Download API key, and save it as {path}"
        )
    checks.append(_check("keys_file", "Coinbase key file", file_ok, file_detail))

    creds = None
    parse_ok = False
    parse_detail = "Need a Coinbase Advanced Trade JSON with name and privateKey."
    if exists:
        try:
            creds = load_coinbase_json(path)
            if creds:
                parse_ok = True
                parse_detail = "JSON has an API name and private key."
            else:
                parse_detail = "File is JSON but missing name / privateKey (the Coinbase export fields)."
        except json.JSONDecodeError:
            parse_detail = "File is not valid JSON. Use the Download API key file from Coinbase."
        except OSError as exc:
            parse_detail = f"Could not read the key file: {exc}"[:200]
    elif env_creds:
        creds = load_coinbase_credentials(
            cwd=root,
            api_key=config.env.coinbase_api_key,
            api_secret=config.env.coinbase_api_secret,
        )
        parse_ok = creds is not None
        parse_detail = "Loaded name and secret from the environment." if parse_ok else parse_detail

    if not file_ok:
        checks.append(_wait("keys_parse", "API name and private key", "Waiting until the key file is in place."))
        checks.append(_wait("key_sign", "Key can sign", "Waiting until the key file is in place."))
        checks.append(_wait("coinbase_ping", "Coinbase accepts the key", "Waiting until the key file is in place."))
        checks.append(_wait("usd_cash", f"At least ${cap:.0f} USD cash", "Waiting until the key file is in place."))
    else:
        checks.append(_check("keys_parse", "API name and private key", parse_ok, parse_detail))
        sign_ok = False
        sign_detail = "Cannot sign until the key file is valid."
        if creds:
            try:
                token = build_rest_jwt(creds[0], creds[1], "GET", "/api/v3/brokerage/accounts")
                sign_ok = token.count(".") == 2
                sign_detail = "Key can sign Coinbase requests."
            except Exception as exc:
                text = str(exc)
                if "cryptography" in text.lower() or "backends.openssl" in text:
                    sign_detail = (
                        "This folder's cryptography install cannot sign yet. "
                        "Close other SecureTrade windows, double-click INSTALL.bat, "
                        f"then CHECK-LIVE.bat again. ({text[:160]})"
                    )
                else:
                    sign_detail = f"Key cannot sign: {text}"[:200]
        if not parse_ok:
            checks.append(_wait("key_sign", "Key can sign", "Waiting until the JSON has name and privateKey."))
            checks.append(_wait("coinbase_ping", "Coinbase accepts the key", "Waiting until the key can sign."))
            checks.append(_wait("usd_cash", f"At least ${cap:.0f} USD cash", "Waiting until Coinbase answers."))
        else:
            checks.append(_check("key_sign", "Key can sign", sign_ok, sign_detail))
            ping_ok = False
            ping_detail = "Cannot ping Coinbase until the key signs."
            if ping and creds and sign_ok:
                coinbase_cfg = config.markets.get("coinbase") or {}
                rest_url = str(coinbase_cfg.get("brokerage_url") or "https://api.coinbase.com")
                balances, err = await ping_coinbase_accounts(creds[0], creds[1], rest_url=rest_url, client=client)
                if err:
                    ping_detail = f"Coinbase did not accept the key: {err}"
                else:
                    ping_ok = True
                    shown = ", ".join(
                        f"{asset} {amount:.4g}" for asset, amount in list(balances.items())[:8] if amount > 0
                    )
                    ping_detail = f"Coinbase accounts reachable. {shown or 'no positive balances'}"
            elif not ping:
                ping_ok = True
                ping_detail = "Ping skipped."
            if not sign_ok:
                checks.append(_wait("coinbase_ping", "Coinbase accepts the key", "Waiting until the key can sign."))
                checks.append(_wait("usd_cash", f"At least ${cap:.0f} USD cash", "Waiting until Coinbase answers."))
            else:
                checks.append(
                    _check("coinbase_ping", "Coinbase accepts the key", ping_ok, ping_detail, required=ping)
                )
                cash = quote_cash(balances)
                if ping and ping_ok:
                    cash_ok = cash + 1e-9 >= cap
                    cash_detail = (
                        f"${cash:.2f} USD/USDC/USDT available. Live cap is ${cap:.0f} per trade."
                        if cash_ok
                        else f"Only ${cash:.2f} cash. Leave at least ${cap:.0f} USD in Coinbase."
                    )
                elif ping:
                    cash_ok = False
                    cash_detail = "Cannot check cash until Coinbase answers."
                else:
                    cash_ok = True
                    cash = 0.0
                    cash_detail = "Cash check skipped."
                checks.append(
                    _check("usd_cash", f"At least ${cap:.0f} USD cash", cash_ok, cash_detail, required=ping)
                )

    cash = quote_cash(balances)
    checks.append(
        _check(
            "live_cap",
            "Live size cap",
            True,
            f"Each live Coinbase order is capped at ${cap:.0f}. Cross-venue stays paper.",
            required=False,
        )
    )
    checks.append(
        _check(
            "auto_off",
            "Auto stays off while live",
            True,
            "Every real Coinbase order is a tap. Auto-invest cannot fire live orders.",
            required=False,
        )
    )
    if killed:
        checks.append(
            _check(
                "kill_switch",
                "Kill switch",
                False,
                "Kill switch is on. Resume on the dashboard before new live orders.",
            )
        )

    ready = all(row["ok"] for row in checks if row["required"])
    armed = config.live_enabled()
    if armed and ready:
        note = "Live Coinbase is armed. Every real order is a tap."
    elif ready:
        note = "Ready. Double-click GO-LIVE.bat when you want real Coinbase orders."
    elif not file_ok:
        note = (
            "Not ready. The key file is missing — that is the only problem so far. "
            f"Create it at {KEY_HELP}, save as keys\\coinbase.json in this folder, "
            "then run CHECK-LIVE.bat again."
        )
    else:
        note = "Not ready. Fix the failed checks, then run CHECK-LIVE.bat again."
    return {
        "ok": True,
        "ready": ready,
        "armed": armed,
        "cap": cap,
        "cash": round(cash, 4),
        "balances": {str(key): round(float(value), 8) for key, value in balances.items() if float(value) > 0},
        "keys_path": str(path),
        "checks": checks,
        "note": note,
    }


def _mark(row: dict[str, Any]) -> str:
    status = str(row.get("status") or ("ok" if row.get("ok") else "fail"))
    return {"ok": "OK  ", "fail": "FAIL", "wait": "WAIT"}.get(status, "FAIL")


def print_live_ready(config: AppConfig | None = None) -> int:
    report = asyncio.run(assess_live_ready(config))
    print(f"{PRODUCT} — live ready check")
    print("This does not send orders.")
    print()
    for row in report["checks"]:
        print(f"  {_mark(row)}  {row['label']}")
        print(f"        {row['detail']}")
    print()
    print(report["note"])
    return 0 if report["ready"] else 1
