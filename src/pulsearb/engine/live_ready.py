"""Preflight checks before real Coinbase or Kraken orders."""

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
from pulsearb.engine.keys import load_coinbase_credentials, load_coinbase_json, load_kraken_credentials, load_kraken_json
from pulsearb.engine.kraken_live import LiveKrakenBroker
from pulsearb.engine.risk import RiskManager

QUOTE_CASH = ("USD", "USDC", "USDT")
KEY_HELP = "https://portal.cdp.coinbase.com/projects/api-keys"
KRAKEN_KEY_HELP = "https://www.kraken.com/u/security/api"


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


def kraken_keys_file_path(config: AppConfig, cwd: Path | None = None) -> Path:
    if config.env.kraken_api_json:
        return Path(config.env.kraken_api_json)
    return (cwd or Path.cwd()) / "keys" / "kraken.json"


def quote_cash(balances: dict[str, float]) -> float:
    return sum(float(balances.get(asset, 0) or 0) for asset in QUOTE_CASH)


def explain_coinbase_error(err: str) -> str:
    text = str(err)
    lower = text.lower()
    if "401" in text or "unauthorized" in lower:
        return (
            "Coinbase rejected the signed request (HTTP 401). "
            "Use a Coinbase App / Advanced Trade Secret API key with View + Trade and ECDSA — "
            f"not a cloud-only CDP key. Create it at {KEY_HELP}."
        )
    if "403" in text or "missing required scopes" in lower:
        return "Coinbase key is missing View + Trade. Do not enable Transfer. Recreate the key and download again."
    if "expecting value" in lower or "empty body" in lower:
        return (
            "Coinbase returned an empty reply. "
            f"{text[:160]}"
        )
    return text[:240]


async def ping_kraken_accounts(
    api_key: str,
    api_secret: str,
    *,
    rest_url: str = "https://api.kraken.com",
    client: httpx.AsyncClient | None = None,
) -> tuple[dict[str, float], str | None]:
    broker = LiveKrakenBroker(
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


def explain_kraken_error(err: str) -> str:
    text = str(err)
    lower = text.lower()
    if "invalid key" in lower or "invalid signature" in lower or "401" in text:
        return (
            "Kraken rejected the signed request. Use a nonce-enabled API key with Query+Funds "
            f"and Create & Modify Orders (no Withdraw). Create it at {KRAKEN_KEY_HELP}."
        )
    if "permission" in lower:
        return "Kraken key is missing Query Funds or Create & Modify Orders. Do not enable Withdraw."
    return text[:240]


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
    armed: bool | None = None,
    venue: str | None = None,
) -> dict[str, Any]:
    config = config or AppConfig()
    root = cwd or Path.cwd()
    wanted = str(venue or "").strip().lower()
    coinbase_path = keys_file_path(config, root)
    kraken_path = kraken_keys_file_path(config, root)
    has_coinbase = coinbase_path.is_file() or bool(config.env.coinbase_api_key and config.env.coinbase_api_secret)
    has_kraken = kraken_path.is_file() or bool(config.env.kraken_api_key and config.env.kraken_api_secret)
    if wanted not in {"coinbase", "kraken"}:
        if has_kraken and not has_coinbase:
            wanted = "kraken"
        else:
            wanted = "coinbase"
    path = kraken_path if wanted == "kraken" else coinbase_path
    cap = float(config.risk.get("live_max_notional_usdt", 25))
    checks: list[dict[str, Any]] = []
    balances: dict[str, float] = {}
    is_kraken = wanted == "kraken"
    venue_label = "Kraken" if is_kraken else "Coinbase"
    ping_id = "kraken_ping" if is_kraken else "coinbase_ping"
    ping_label = f"{venue_label} accepts the key"
    env_creds = (
        bool(config.env.kraken_api_key and config.env.kraken_api_secret)
        if is_kraken
        else bool(config.env.coinbase_api_key and config.env.coinbase_api_secret)
    )
    exists = path.is_file()
    file_ok = exists or env_creds
    if exists:
        file_detail = f"Found {path}"
    elif env_creds:
        file_detail = f"Using {venue_label} API keys from the environment."
    elif is_kraken:
        file_detail = (
            f"No file yet. Create a Kraken API key at {KRAKEN_KEY_HELP} "
            f"(Query Funds + Create & Modify Orders, no Withdraw) and save it as {path}"
        )
    else:
        file_detail = (
            f"No file yet. Create a Secret API key at {KEY_HELP} "
            f"(View + Trade, ECDSA), click Download API key, and save it as {path}"
        )
    checks.append(_check("keys_file", f"{venue_label} key file", file_ok, file_detail))

    creds = None
    parse_ok = False
    parse_detail = (
        "Need a Kraken JSON with key and secret."
        if is_kraken
        else "Need a Coinbase Advanced Trade JSON with name and privateKey."
    )
    if exists:
        try:
            creds = load_kraken_json(path) if is_kraken else load_coinbase_json(path)
            if creds:
                parse_ok = True
                parse_detail = "JSON has an API key and secret." if is_kraken else "JSON has an API name and private key."
            else:
                parse_detail = (
                    "File is JSON but missing key / secret."
                    if is_kraken
                    else "File is JSON but missing name / privateKey (the Coinbase export fields)."
                )
        except json.JSONDecodeError:
            parse_detail = (
                "File is not valid JSON. Use {\"key\":\"...\",\"secret\":\"...\"}."
                if is_kraken
                else "File is not valid JSON. Use the Download API key file from Coinbase."
            )
        except OSError as exc:
            parse_detail = f"Could not read the key file: {exc}"[:200]
    elif env_creds:
        if is_kraken:
            creds = load_kraken_credentials(
                cwd=root,
                api_key=config.env.kraken_api_key,
                api_secret=config.env.kraken_api_secret,
            )
        else:
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
        checks.append(_wait(ping_id, ping_label, "Waiting until the key file is in place."))
        checks.append(_wait("usd_cash", f"At least ${cap:.0f} USD cash", "Waiting until the key file is in place."))
    else:
        checks.append(_check("keys_parse", "API name and private key", parse_ok, parse_detail))
        sign_ok = False
        sign_detail = "Cannot sign until the key file is valid."
        if creds:
            try:
                if is_kraken:
                    from pulsearb.engine.kraken_auth import kraken_signature

                    token = kraken_signature(creds[1], "/0/private/Balance", "1", "nonce=1")
                    sign_ok = bool(token)
                    sign_detail = "Key can sign Kraken requests."
                else:
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
            checks.append(
                _wait(
                    "key_sign",
                    "Key can sign",
                    "Waiting until the JSON has key and secret." if is_kraken else "Waiting until the JSON has name and privateKey.",
                )
            )
            checks.append(_wait(ping_id, ping_label, "Waiting until the key can sign."))
            checks.append(_wait("usd_cash", f"At least ${cap:.0f} USD cash", f"Waiting until {venue_label} answers."))
        else:
            checks.append(_check("key_sign", "Key can sign", sign_ok, sign_detail))
            ping_ok = False
            ping_detail = f"Cannot ping {venue_label} until the key signs."
            if ping and creds and sign_ok:
                err = None
                if is_kraken:
                    kraken_cfg = config.markets.get("kraken") or {}
                    rest_url = str(kraken_cfg.get("rest_url") or "https://api.kraken.com")
                    balances, err = await ping_kraken_accounts(creds[0], creds[1], rest_url=rest_url, client=client)
                    ping_detail = explain_kraken_error(err) if err else ping_detail
                else:
                    coinbase_cfg = config.markets.get("coinbase") or {}
                    rest_url = str(coinbase_cfg.get("brokerage_url") or "https://api.coinbase.com")
                    balances, err = await ping_coinbase_accounts(creds[0], creds[1], rest_url=rest_url, client=client)
                    ping_detail = explain_coinbase_error(err) if err else ping_detail
                if not err:
                    ping_ok = True
                    shown = ", ".join(
                        f"{asset} {amount:.4g}" for asset, amount in list(balances.items())[:8] if amount > 0
                    )
                    ping_detail = f"{venue_label} accounts reachable. {shown or 'no positive balances'}"
            elif not ping:
                ping_ok = True
                ping_detail = "Ping skipped."
            if not sign_ok:
                checks.append(_wait(ping_id, ping_label, "Waiting until the key can sign."))
                checks.append(_wait("usd_cash", f"At least ${cap:.0f} USD cash", f"Waiting until {venue_label} answers."))
            else:
                checks.append(_check(ping_id, ping_label, ping_ok, ping_detail, required=ping))
                cash = quote_cash(balances)
                if ping and ping_ok:
                    cash_ok = cash + 1e-9 >= cap
                    cash_detail = (
                        f"${cash:.2f} USD/USDC/USDT available. Session budget is ${cap:.0f}; each tap can be $1–${cap:.0f}."
                        if cash_ok
                        else f"Only ${cash:.2f} cash. Leave at least ${cap:.0f} USD in {venue_label}."
                    )
                    checks.append(
                        _check("usd_cash", f"At least ${cap:.0f} USD cash", cash_ok, cash_detail, required=ping)
                    )
                elif ping:
                    checks.append(
                        _wait("usd_cash", f"At least ${cap:.0f} USD cash", f"Waiting until {venue_label} answers.")
                    )
                else:
                    checks.append(
                        _check(
                            "usd_cash",
                            f"At least ${cap:.0f} USD cash",
                            True,
                            "Cash check skipped.",
                            required=False,
                            status="wait",
                        )
                    )

    cash = quote_cash(balances)
    checks.append(
        _check(
            "live_cap",
            "Live size cap",
            True,
            f"Each tap is $1–${cap:.0f}. Session budget ${cap:.0f}. Live is {venue_label} USD round-trips "
            "(USD vs USDC dislocations and same-exchange triangles). Cross-venue stays paper.",
            required=False,
        )
    )
    checks.append(
        _check(
            "auto_off",
            "Live Auto needs a time window",
            True,
            "While live, automatic taps only run inside the Auto window you set (for example 10:00 PM to 6:00 AM). Pick each trade if the window is off.",
            required=False,
        )
    )
    if killed:
        checks.append(
            _check(
                "kill_switch",
                "Kill switch",
                False,
                "New orders are paused. Click Resume on the dashboard. Paper/Live did not change.",
            )
        )

    ready = all(row["ok"] for row in checks if row["required"])
    live_on = config.live_enabled() if armed is None else bool(armed)
    if live_on and killed:
        note = (
            "LIVE is still on. The kill switch paused new orders. "
            "Click Resume. You are not back on paper."
        )
    elif live_on and ready:
        note = (
            f"Live {venue_label} round-trips are on (USD vs USDC books, plus triangles). "
            "Switch back to Paper any time. Every real order is a tap."
        )
    elif ready:
        note = (
            f"Ready. Stay on Paper to practice, then switch to Live when you want real {venue_label} orders. "
            "Pick Coinbase or Kraken on the dashboard if you have both keys."
        )
    elif not file_ok:
        other = "keys\\kraken.json" if is_kraken else "keys\\coinbase.json"
        note = (
            "Not ready. The key file is missing — that is the only problem so far. "
            f"Save {other} in this folder "
            f"({'Kraken key+secret JSON' if is_kraken else f'from {KEY_HELP}'}), "
            "then run CHECK-LIVE.bat again. You can live-trade Coinbase or Kraken — you do not need both."
        )
    else:
        note = "Not ready. Fix the failed checks, then run CHECK-LIVE.bat again."
    return {
        "ok": True,
        "ready": ready,
        "armed": live_on,
        "cap": cap,
        "cash": round(cash, 4),
        "balances": {str(key): round(float(value), 8) for key, value in balances.items() if float(value) > 0},
        "keys_path": str(path),
        "venue": wanted,
        "venues_with_keys": [name for name, present in (("coinbase", has_coinbase), ("kraken", has_kraken)) if present],
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
