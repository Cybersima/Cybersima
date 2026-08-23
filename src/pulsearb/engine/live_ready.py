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


def usd_spendable(balances: dict[str, float]) -> float:
    """USD only. USDC/USDT do not start a live tap."""
    return float(balances.get("USD", 0) or 0)


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


def oanda_keys_file_path(config: AppConfig, cwd: Path | None = None) -> Path:
    if config.env.oanda_api_json:
        return Path(config.env.oanda_api_json)
    return (cwd or Path.cwd()) / "keys" / "oanda.json"


async def assess_oanda_ready(
    config: AppConfig,
    *,
    cwd: Path | None = None,
    client: httpx.AsyncClient | None = None,
    ping: bool = True,
    killed: bool = False,
    armed: bool | None = None,
) -> dict[str, Any]:
    """Separate from assess_live_ready's coinbase/kraken checks on purpose -
    that function is a tested, hardcoded two-venue ternary ladder, and OANDA
    is different enough (Bearer token not signing, one home-currency balance
    not USD/USDC/USDT, margin not spot) that forcing it into the same shape
    risked bugs in the working Coinbase/Kraken path for no real benefit.
    Same checklist shape and spirit, adapted to OANDA."""
    from pulsearb.engine.oanda_live import LiveOandaBroker, explain_oanda_order_error

    root = cwd or Path.cwd()
    path = oanda_keys_file_path(config, root)
    cap = float(config.risk.get("live_max_notional_usdt", 25))
    checks: list[dict[str, Any]] = []

    creds = config.oanda_credentials()
    file_ok = creds is not None
    if path.is_file():
        file_detail = f"Found {path}" if file_ok else f"{path} exists but is missing account_id / access_token."
    elif bool(config.env.oanda_account_id and config.env.oanda_access_token):
        file_detail = "Using OANDA credentials from the environment."
    else:
        file_detail = (
            "No file yet. Generate a personal access token in the OANDA account portal "
            "(My Account -> My Services -> Manage API Access) and save it as "
            f"{path} with account_id, access_token, and environment (practice or live)."
        )
    checks.append(_check("oanda_keys_file", "OANDA key file", file_ok, file_detail))

    if not file_ok:
        checks.append(_wait("oanda_ping", "OANDA accepts the token", "Waiting until the key file is in place."))
        checks.append(_wait("oanda_cash", f"At least ${cap:.0f} account balance", "Waiting until the key file is in place."))
        balances: dict[str, float] = {}
        environment = "practice"
    else:
        account_id, access_token, environment = creds
        ping_ok = False
        ping_detail = "Cannot ping OANDA until credentials are present."
        balances = {}
        if ping:
            broker = LiveOandaBroker(
                risk=RiskManager(),
                account_id=account_id,
                access_token=access_token,
                paper_fallback=PaperBroker(RiskManager()),
                environment=environment,
                client=client,
            )
            try:
                balances = await broker.refresh_balances(client)
                ping_ok = True
                shown = ", ".join(f"{asset} {amount:.2f}" for asset, amount in balances.items() if amount > 0)
                ping_detail = f"OANDA account reachable ({environment}). {shown or 'zero balance'}"
                if broker.status.startswith("warning"):
                    ping_detail = f"{ping_detail} - {broker.status}"
            except Exception as exc:
                ping_detail = explain_oanda_order_error(str(exc))
        else:
            ping_ok = True
            ping_detail = "Ping skipped."
        checks.append(_check("oanda_ping", "OANDA accepts the token", ping_ok, ping_detail, required=ping))

        balance = float(balances.get("USD", 0.0) or 0.0)
        if ping and ping_ok:
            cash_ok = balance + 1e-9 >= cap
            cash_detail = (
                f"${balance:.2f} in the account. Each tap can be $0.10-${cap:.0f}; leave at least ${cap:.0f} "
                "so a full-size tap has room."
                if cash_ok
                else f"Only ${balance:.2f} in the account. Leave at least ${cap:.0f} for a full-size tap."
            )
            checks.append(_check("oanda_cash", f"At least ${cap:.0f} account balance", cash_ok, cash_detail, required=ping))
        elif ping:
            checks.append(_wait("oanda_cash", f"At least ${cap:.0f} account balance", "Waiting until OANDA answers."))
        else:
            checks.append(_check("oanda_cash", f"At least ${cap:.0f} account balance", True, "Cash check skipped.", required=False, status="wait"))

    checks.append(
        _check(
            "oanda_leverage_note",
            "Margin, not spot",
            True,
            "A tap opens a position worth the tap size in currency exposure, then immediately closes it - "
            "leverage only reduces the margin held against that position, it never makes the position bigger. "
            "No position is left open.",
            required=False,
        )
    )
    if killed:
        checks.append(_check("kill_switch", "Kill switch", False, "New orders are paused. Click Resume on the dashboard."))

    ready = all(row["ok"] for row in checks if row["required"])
    live_on = config.live_enabled() if armed is None else bool(armed)
    if live_on and killed:
        note = "LIVE is still on. The kill switch paused new orders. Click Resume."
    elif live_on and ready:
        note = "Live OANDA round-trips are on. Switch back to Paper any time. Every real order is a tap."
    elif ready:
        note = "Ready. Stay on Paper to practice, then switch to Live when you want real OANDA orders."
    elif not file_ok:
        note = f"Not ready. Save {path} with your OANDA account_id and access_token, then check again."
    else:
        note = "Not ready. Fix the failed checks above, then check again."
    return {
        "ok": True,
        "ready": ready,
        "armed": live_on,
        "cap": cap,
        "cash": round(float(balances.get("USD", 0.0) or 0.0), 4),
        "usd": round(float(balances.get("USD", 0.0) or 0.0), 4),
        "balances": {str(key): round(float(value), 8) for key, value in balances.items() if float(value) > 0},
        "keys_path": str(path),
        "venue": "oanda",
        "venues_with_keys": ["oanda"] if file_ok else [],
        "checks": checks,
        "note": note,
    }


async def assess_gemini_ready(
    config: AppConfig,
    *,
    cwd: Path | None = None,
    client: httpx.AsyncClient | None = None,
    ping: bool = True,
    killed: bool = False,
    armed: bool | None = None,
) -> dict[str, Any]:
    """Additive, same reasoning as assess_oanda_ready above: kept separate
    from the coinbase/kraken ternary ladder rather than trying to fold in
    a third auth scheme (Gemini's base64-payload HMAC-SHA384) there."""
    from pulsearb.engine.gemini_live import LiveGeminiBroker, explain_gemini_order_error

    root = cwd or Path.cwd()
    path = (root / "keys" / "gemini.json") if not config.env.gemini_api_json else Path(config.env.gemini_api_json)
    cap = float(config.risk.get("live_max_notional_usdt", 25))
    checks: list[dict[str, Any]] = []

    creds = config.gemini_credentials()
    file_ok = creds is not None
    if path.is_file():
        file_detail = f"Found {path}" if file_ok else f"{path} exists but is missing key / secret."
    elif bool(config.env.gemini_api_key and config.env.gemini_api_secret):
        file_detail = "Using Gemini credentials from the environment."
    else:
        file_detail = (
            "No file yet. Create an API key at https://exchange.gemini.com/settings/api "
            "with Trading permission and save it as "
            f"{path} with \"key\" and \"secret\"."
        )
    checks.append(_check("gemini_keys_file", "Gemini key file", file_ok, file_detail))

    balances: dict[str, float] = {}
    if not file_ok:
        checks.append(_wait("gemini_ping", "Gemini accepts the key", "Waiting until the key file is in place."))
        checks.append(_wait("gemini_cash", f"At least ${cap:.0f} USD cash", "Waiting until the key file is in place."))
    else:
        api_key, api_secret = creds
        ping_ok = False
        ping_detail = "Cannot ping Gemini until credentials are present."
        if ping:
            broker = LiveGeminiBroker(risk=RiskManager(), api_key=api_key, api_secret=api_secret, paper_fallback=PaperBroker(RiskManager()), client=client)
            try:
                balances = await broker.refresh_balances(client)
                ping_ok = True
                shown = ", ".join(f"{asset} {amount:.4g}" for asset, amount in balances.items() if amount > 0)
                ping_detail = f"Gemini accounts reachable. {shown or 'no positive balances'}"
            except Exception as exc:
                ping_detail = explain_gemini_order_error(str(exc))
        else:
            ping_ok = True
            ping_detail = "Ping skipped."
        checks.append(_check("gemini_ping", "Gemini accepts the key", ping_ok, ping_detail, required=ping))

        cash = quote_cash(balances)
        usd = usd_spendable(balances)
        if ping and ping_ok:
            floor = max(0.10, float(config.risk.get("min_notional_usdt", 0.10)))
            usd_ok = usd + 1e-9 >= floor
            cash_ok = cash + 1e-9 >= cap
            if not usd_ok:
                cash_detail = f"${usd:.2f} USD and ${cash:.2f} USD+USDC+USDT. A live tap starts by spending USD, not USDC. Move at least ${floor:.2f} into USD on Gemini."
            elif not cash_ok:
                cash_detail = f"Only ${cash:.2f} cash. Leave at least ${cap:.0f} USD in Gemini."
            else:
                cash_detail = f"${usd:.2f} USD (${cash:.2f} including USDC/USDT). Session budget is ${cap:.0f}."
            checks.append(_check("gemini_cash", f"USD to start a tap (${cap:.0f} cash)", usd_ok and cash_ok, cash_detail, required=ping))
        elif ping:
            checks.append(_wait("gemini_cash", f"At least ${cap:.0f} USD cash", "Waiting until Gemini answers."))
        else:
            checks.append(_check("gemini_cash", f"At least ${cap:.0f} USD cash", True, "Cash check skipped.", required=False, status="wait"))

    if killed:
        checks.append(_check("kill_switch", "Kill switch", False, "New orders are paused. Click Resume on the dashboard."))

    ready = all(row["ok"] for row in checks if row["required"])
    live_on = config.live_enabled() if armed is None else bool(armed)
    if live_on and killed:
        note = "LIVE is still on. The kill switch paused new orders. Click Resume."
    elif live_on and ready:
        note = "Live Gemini round-trips are on. Switch back to Paper any time."
    elif ready:
        note = "Ready. Stay on Paper to practice, then switch to Live when you want real Gemini orders."
    elif not file_ok:
        note = f"Not ready. Save {path} with your Gemini key and secret, then check again."
    else:
        note = "Not ready. Fix the failed checks above, then check again."
    return {
        "ok": True, "ready": ready, "armed": live_on, "cap": cap,
        "cash": round(quote_cash(balances), 4), "usd": round(usd_spendable(balances), 4),
        "balances": {str(k): round(float(v), 8) for k, v in balances.items() if float(v) > 0},
        "keys_path": str(path), "venue": "gemini",
        "venues_with_keys": ["gemini"] if file_ok else [],
        "checks": checks, "note": note,
    }


async def assess_robinhood_ready(
    config: AppConfig,
    *,
    cwd: Path | None = None,
    client: httpx.AsyncClient | None = None,
    ping: bool = True,
    killed: bool = False,
    armed: bool | None = None,
) -> dict[str, Any]:
    """Same additive pattern as the other assess_*_ready functions - kept
    separate from the coinbase/kraken ternary ladder. Extra note worth
    surfacing here specifically: Robinhood has no practice/sandbox
    environment (unlike OANDA), so a passing ping here means the key is
    live-capable immediately - there's no "safe" environment to test
    against first the way there is for OANDA."""
    from pulsearb.engine.robinhood_live import LiveRobinhoodBroker, explain_robinhood_order_error

    root = cwd or Path.cwd()
    path = (root / "keys" / "robinhood.json") if not config.env.robinhood_api_json else Path(config.env.robinhood_api_json)
    cap = float(config.risk.get("live_max_notional_usdt", 25))
    checks: list[dict[str, Any]] = []

    creds = config.robinhood_credentials()
    file_ok = creds is not None
    if path.is_file():
        file_detail = f"Found {path}" if file_ok else f"{path} exists but is missing api_key / private_key."
    elif bool(config.env.robinhood_api_key and config.env.robinhood_private_key):
        file_detail = "Using Robinhood credentials from the environment."
    else:
        file_detail = (
            "No file yet. Generate an Ed25519 keypair (see the Python script "
            "in Robinhood's API docs), register the public key at your "
            "Robinhood crypto account's API Credentials page, and save the "
            f"API key + base64 private key as {path} with \"api_key\" and \"private_key\"."
        )
    checks.append(_check("robinhood_keys_file", "Robinhood key file", file_ok, file_detail))

    balances: dict[str, float] = {}
    if not file_ok:
        checks.append(_wait("robinhood_ping", "Robinhood accepts the key", "Waiting until the key file is in place."))
        checks.append(_wait("robinhood_cash", f"At least ${cap:.0f} buying power", "Waiting until the key file is in place."))
    else:
        api_key, private_key = creds
        ping_ok = False
        ping_detail = "Cannot ping Robinhood until credentials are present."
        if ping:
            broker = LiveRobinhoodBroker(risk=RiskManager(), api_key=api_key, private_key_base64=private_key, paper_fallback=PaperBroker(RiskManager()), client=client)
            try:
                balances = await broker.refresh_balances(client)
                ping_ok = True
                shown = ", ".join(f"{asset} {amount:.4g}" for asset, amount in balances.items() if amount > 0)
                ping_detail = f"Robinhood account reachable (#{broker._account_number}). {shown or 'zero balance'}"
            except Exception as exc:
                ping_detail = explain_robinhood_order_error(str(exc))
        else:
            ping_ok = True
            ping_detail = "Ping skipped."
        checks.append(_check("robinhood_ping", "Robinhood accepts the key", ping_ok, ping_detail, required=ping))

        balance = float(balances.get("USD", 0.0) or 0.0)
        if ping and ping_ok:
            cash_ok = balance + 1e-9 >= cap
            cash_detail = (
                f"${balance:.2f} buying power. Each tap can be $0.10-${cap:.0f}; leave at least ${cap:.0f} "
                "so a full-size tap has room."
                if cash_ok
                else f"Only ${balance:.2f} buying power. Leave at least ${cap:.0f} for a full-size tap."
            )
            checks.append(_check("robinhood_cash", f"At least ${cap:.0f} buying power", cash_ok, cash_detail, required=ping))
        elif ping:
            checks.append(_wait("robinhood_cash", f"At least ${cap:.0f} buying power", "Waiting until Robinhood answers."))
        else:
            checks.append(_check("robinhood_cash", f"At least ${cap:.0f} buying power", True, "Cash check skipped.", required=False, status="wait"))

    checks.append(
        _check(
            "robinhood_no_sandbox",
            "No practice environment",
            True,
            "Robinhood has no paper/sandbox API - this key is real-money-capable the moment it works. "
            "Unlike OANDA, there's no safer environment to test against first.",
            required=False,
        )
    )
    if killed:
        checks.append(_check("kill_switch", "Kill switch", False, "New orders are paused. Click Resume on the dashboard."))

    ready = all(row["ok"] for row in checks if row["required"])
    live_on = config.live_enabled() if armed is None else bool(armed)
    if live_on and killed:
        note = "LIVE is still on. The kill switch paused new orders. Click Resume."
    elif live_on and ready:
        note = "Live Robinhood round-trips are on. Switch back to Paper any time."
    elif ready:
        note = "Ready. Stay on Paper to practice, then switch to Live when you want real Robinhood orders."
    elif not file_ok:
        note = f"Not ready. Save {path} with your Robinhood API key and private key, then check again."
    else:
        note = "Not ready. Fix the failed checks above, then check again."
    return {
        "ok": True, "ready": ready, "armed": live_on, "cap": cap,
        "cash": round(float(balances.get("USD", 0.0) or 0.0), 4), "usd": round(float(balances.get("USD", 0.0) or 0.0), 4),
        "balances": {str(k): round(float(v), 8) for k, v in balances.items() if float(v) > 0},
        "keys_path": str(path), "venue": "robinhood",
        "venues_with_keys": ["robinhood"] if file_ok else [],
        "checks": checks, "note": note,
    }




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
    if wanted == "oanda":
        return await assess_oanda_ready(config, cwd=root, client=client, ping=ping, killed=killed, armed=armed)
    if wanted == "gemini":
        return await assess_gemini_ready(config, cwd=root, client=client, ping=ping, killed=killed, armed=armed)
    if wanted == "robinhood":
        return await assess_robinhood_ready(config, cwd=root, client=client, ping=ping, killed=killed, armed=armed)
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
                usd = usd_spendable(balances)
                if ping and ping_ok:
                    floor = max(0.10, float(config.risk.get("min_notional_usdt", 0.10)))
                    usd_ok = usd + 1e-9 >= floor
                    cash_ok = cash + 1e-9 >= cap
                    if not usd_ok:
                        cash_detail = (
                            f"${usd:.2f} USD and ${cash:.2f} USD+USDC+USDT. "
                            f"A live tap starts by spending USD, not USDC. "
                            f"Move at least ${floor:.2f} into USD on {venue_label}."
                        )
                    elif not cash_ok:
                        cash_detail = f"Only ${cash:.2f} cash. Leave at least ${cap:.0f} USD in {venue_label}."
                    else:
                        cash_detail = (
                            f"${usd:.2f} USD (${cash:.2f} including USDC/USDT). "
                            f"Session budget is ${cap:.0f}; each tap can be $0.10–${cap:.0f}. "
                            "Live first legs spend USD."
                        )
                    checks.append(
                        _check(
                            "usd_cash",
                            f"USD to start a tap (${cap:.0f} cash)",
                            usd_ok and cash_ok,
                            cash_detail,
                            required=ping,
                        )
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
    usd = usd_spendable(balances)
    checks.append(
        _check(
            "live_cap",
            "Live size cap",
            True,
            f"Each tap is $0.10–${cap:.0f}. Session budget ${cap:.0f}. Live is {venue_label} USD round-trips "
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
        "usd": round(usd, 4),
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
