"""Exit 0 if this interpreter can sign a Coinbase-style JWT."""

from __future__ import annotations

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def main() -> int:
    try:
        key = ec.generate_private_key(ec.SECP256R1())
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        from pulsearb.engine.coinbase_auth import build_rest_jwt

        token = build_rest_jwt(
            "organizations/test/apiKeys/x",
            pem,
            "GET",
            "/api/v3/brokerage/accounts",
        )
        if token.count(".") != 2:
            print("cryptography is not ready: JWT did not have three parts")
            return 1
    except Exception as exc:
        print(f"cryptography is not ready: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
