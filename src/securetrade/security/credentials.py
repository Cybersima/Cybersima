from __future__ import annotations

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class CredentialVault:
    """Encrypted credential store. Keys are withdrawal-disabled by policy, never logged."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or Path.home() / ".cybersym" / "securetrade"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.key_path = self.directory / "master.key"
        self.store_path = self.directory / "credentials.enc"

    def _fernet(self) -> Fernet:
        if self.key_path.exists():
            key = self.key_path.read_bytes()
        else:
            key = Fernet.generate_key()
            self.key_path.write_bytes(key)
            try:
                os.chmod(self.key_path, 0o600)
            except OSError:
                pass
        return Fernet(key)

    def save(self, payload: dict) -> None:
        token = self._fernet().encrypt(json.dumps(payload).encode())
        self.store_path.write_bytes(token)
        try:
            os.chmod(self.store_path, 0o600)
        except OSError:
            pass

    def load(self) -> dict:
        if not self.store_path.exists():
            return {}
        try:
            return json.loads(self._fernet().decrypt(self.store_path.read_bytes()).decode())
        except InvalidToken:
            return {}

    def store_exchange_key(self, venue: str, api_key: str, api_secret: str, permissions: list[str] | None = None) -> None:
        data = self.load()
        data[venue] = {
            "api_key": api_key,
            "api_secret": api_secret,
            "permissions": permissions or ["spot_trade"],
            "withdrawal_enabled": False,
        }
        self.save(data)
