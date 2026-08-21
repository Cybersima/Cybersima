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
