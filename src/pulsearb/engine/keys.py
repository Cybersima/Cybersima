from __future__ import annotations

import json
from pathlib import Path


def _from_mapping(data: dict) -> tuple[str, str] | None:
    name = data.get("name") or data.get("id") or data.get("apiKey") or data.get("api_key")
    secret = data.get("privateKey") or data.get("secret") or data.get("apiSecret") or data.get("api_secret")
    if name and secret:
        return str(name).strip(), str(secret).strip()
    return None


def load_coinbase_json(path: Path) -> tuple[str, str] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    return _from_mapping(data)


def load_coinbase_credentials(
    *,
    cwd: Path | None = None,
    json_path: str | Path | None = None,
    api_key: str = "",
    api_secret: str = "",
) -> tuple[str, str] | None:
    """Load Coinbase Advanced Trade CDP key name + private key.

    Prefers a downloaded JSON file (the usual Coinbase export), then env vars.
    """
    root = cwd or Path.cwd()
    candidates: list[Path] = []
    if json_path:
        candidates.append(Path(json_path))
    candidates.append(root / "keys" / "coinbase.json")
    for path in candidates:
        creds = load_coinbase_json(path)
        if creds:
            return creds
    if api_key.strip() and api_secret.strip():
        return api_key.strip(), api_secret.strip()
    return None


def load_kraken_json(path: Path) -> tuple[str, str] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    key = data.get("key") or data.get("apiKey") or data.get("api_key")
    secret = data.get("secret") or data.get("privateKey") or data.get("apiSecret") or data.get("api_secret")
    if key and secret:
        return str(key).strip(), str(secret).strip()
    return None


def load_kraken_credentials(
    *,
    cwd: Path | None = None,
    json_path: str | Path | None = None,
    api_key: str = "",
    api_secret: str = "",
) -> tuple[str, str] | None:
    """Load Kraken REST API key + secret (base64 private key from Kraken)."""
    root = cwd or Path.cwd()
    candidates: list[Path] = []
    if json_path:
        candidates.append(Path(json_path))
    candidates.append(root / "keys" / "kraken.json")
    for path in candidates:
        creds = load_kraken_json(path)
        if creds:
            return creds
    if api_key.strip() and api_secret.strip():
        return api_key.strip(), api_secret.strip()
    return None


def load_oanda_json(path: Path) -> tuple[str, str, str] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    account_id = data.get("account_id") or data.get("accountID") or data.get("accountId")
    token = data.get("access_token") or data.get("accessToken") or data.get("token")
    environment = str(data.get("environment") or "practice").strip().lower()
    if account_id and token:
        return str(account_id).strip(), str(token).strip(), environment
    return None


def load_oanda_credentials(
    *,
    cwd: Path | None = None,
    json_path: str | Path | None = None,
    account_id: str = "",
    access_token: str = "",
    environment: str = "",
) -> tuple[str, str, str] | None:
    root = cwd or Path.cwd()
    candidates: list[Path] = []
    if json_path:
        candidates.append(Path(json_path))
    candidates.append(root / "keys" / "oanda.json")
    for path in candidates:
        creds = load_oanda_json(path)
        if creds:
            return creds
    if account_id.strip() and access_token.strip():
        env = (environment or "practice").strip().lower()
        return account_id.strip(), access_token.strip(), env
    return None


def load_gemini_json(path: Path) -> tuple[str, str] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    key = data.get("key") or data.get("api_key") or data.get("apiKey")
    secret = data.get("secret") or data.get("api_secret") or data.get("apiSecret")
    if key and secret:
        return str(key).strip(), str(secret).strip()
    return None


def load_gemini_credentials(
    *,
    cwd: Path | None = None,
    json_path: str | Path | None = None,
    api_key: str = "",
    api_secret: str = "",
) -> tuple[str, str] | None:
    root = cwd or Path.cwd()
    candidates: list[Path] = []
    if json_path:
        candidates.append(Path(json_path))
    candidates.append(root / "keys" / "gemini.json")
    for path in candidates:
        creds = load_gemini_json(path)
        if creds:
            return creds
    if api_key.strip() and api_secret.strip():
        return api_key.strip(), api_secret.strip()
    return None


def load_robinhood_json(path: Path) -> tuple[str, str] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    api_key = data.get("api_key") or data.get("apiKey") or data.get("key")
    private_key = data.get("private_key") or data.get("privateKey") or data.get("secret")
    if api_key and private_key:
        return str(api_key).strip(), str(private_key).strip()
    return None


def load_robinhood_credentials(
    *,
    cwd: Path | None = None,
    json_path: str | Path | None = None,
    api_key: str = "",
    private_key: str = "",
) -> tuple[str, str] | None:
    root = cwd or Path.cwd()
    candidates: list[Path] = []
    if json_path:
        candidates.append(Path(json_path))
    candidates.append(root / "keys" / "robinhood.json")
    for path in candidates:
        creds = load_robinhood_json(path)
        if creds:
            return creds
    if api_key.strip() and private_key.strip():
        return api_key.strip(), private_key.strip()
    return None
