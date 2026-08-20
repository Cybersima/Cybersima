"""Local dashboard lock — PIN in the console, cookie after unlock."""

from __future__ import annotations

import hmac
import secrets
import time


COOKIE = "st_session"


class DashboardGuard:
    def __init__(self) -> None:
        self.pin = f"{secrets.randbelow(1_000_000):06d}"
        self.cookie = secrets.token_urlsafe(32)
        self.unlock_token = secrets.token_urlsafe(24)
        self.failures = 0
        self.lock_until = 0.0

    def cookie_ok(self, value: str | None) -> bool:
        return hmac.compare_digest(value or "", self.cookie)

    def token_ok(self, value: str | None) -> bool:
        return hmac.compare_digest(value or "", self.unlock_token)

    def pin_ok(self, value: str | None) -> bool:
        now = time.time()
        if now < self.lock_until:
            return False
        ok = hmac.compare_digest((value or "").strip(), self.pin)
        if ok:
            self.failures = 0
            return True
        self.failures += 1
        if self.failures >= 8:
            self.lock_until = now + 20
            self.failures = 0
        return False

    def locked_out(self) -> bool:
        return time.time() < self.lock_until
