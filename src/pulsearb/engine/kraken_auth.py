from __future__ import annotations

import base64
import hashlib
import hmac
from urllib.parse import urlencode


def kraken_signature(secret: str, path: str, nonce: str, postdata: str) -> str:
    """Kraken API-Sign: HMAC-SHA512(path + SHA256(nonce + post), b64decode(secret))."""
    message = path.encode() + hashlib.sha256((nonce + postdata).encode()).digest()
    digest = hmac.new(base64.b64decode(secret), message, hashlib.sha512).digest()
    return base64.b64encode(digest).decode()


def kraken_body(params: dict[str, str]) -> str:
    return urlencode(params)
