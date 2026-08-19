from __future__ import annotations

import base64
import secrets
import time
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

HOST = "api.coinbase.com"


def normalize_secret(secret: str) -> str:
    text = secret.strip().replace("\\n", "\n")
    if "BEGIN" in text:
        return text if text.endswith("\n") else text + "\n"
    return text


def load_private_key(secret: str) -> Any:
    raw = normalize_secret(secret)
    if "BEGIN" in raw:
        return load_pem_private_key(raw.encode("utf-8"), password=None)
    decoded = base64.b64decode(raw)
    if len(decoded) in {32, 64}:
        return Ed25519PrivateKey.from_private_bytes(decoded[:32])
    raise ValueError("Coinbase API secret is not a PEM or Ed25519 key")


def jwt_algorithm(private_key: Any) -> str:
    if isinstance(private_key, Ed25519PrivateKey):
        return "EdDSA"
    if isinstance(private_key, EllipticCurvePrivateKey):
        return "ES256"
    raise ValueError("Unsupported Coinbase API key type")


def format_jwt_uri(method: str, path: str, host: str = HOST) -> str:
    return f"{method.upper()} {host}{path}"


def build_rest_jwt(key_name: str, secret: str, method: str, path: str, host: str = HOST) -> str:
    private_key = load_private_key(secret)
    now = int(time.time())
    payload = {
        "sub": key_name,
        "iss": "cdp",
        "nbf": now,
        "exp": now + 120,
        "uri": format_jwt_uri(method, path, host),
    }
    headers = {"kid": key_name, "nonce": secrets.token_hex(16)}
    token = jwt.encode(payload, private_key, algorithm=jwt_algorithm(private_key), headers=headers)
    return token if isinstance(token, str) else token.decode("utf-8")
