from __future__ import annotations

import base64
import json
import secrets
import time
from typing import Any

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives import hashes
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


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _json_b64(value: dict[str, Any]) -> str:
    return _b64url(json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))


def _es256_signature(private_key: EllipticCurvePrivateKey, signing_input: bytes) -> bytes:
    der = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    size = (private_key.curve.key_size + 7) // 8
    return r.to_bytes(size, "big") + s.to_bytes(size, "big")


def build_rest_jwt(key_name: str, secret: str, method: str, path: str, host: str = HOST) -> str:
    """Build a Coinbase CDP JWT without PyJWT's OpenSSL backend import.

    Python 3.14 venvs can have a cryptography install that loads keys but
    is missing cryptography.hazmat.backends.openssl, which PyJWT still imports.
    """
    private_key = load_private_key(secret)
    now = int(time.time())
    header = {
        "alg": jwt_algorithm(private_key),
        "kid": key_name,
        "nonce": secrets.token_hex(16),
        "typ": "JWT",
    }
    payload = {
        "sub": key_name,
        "iss": "cdp",
        "nbf": now,
        "exp": now + 120,
        "uri": format_jwt_uri(method, path, host),
    }
    signing_input = f"{_json_b64(header)}.{_json_b64(payload)}".encode("ascii")
    if isinstance(private_key, Ed25519PrivateKey):
        signature = private_key.sign(signing_input)
    elif isinstance(private_key, EllipticCurvePrivateKey):
        signature = _es256_signature(private_key, signing_input)
    else:
        raise ValueError("Unsupported Coinbase API key type")
    return f"{signing_input.decode('ascii')}.{_b64url(signature)}"
