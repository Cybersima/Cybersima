"""Lightweight API smoke test for Lockwell."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

os.environ["DATABASE_URL"] = "sqlite:///" + tempfile.mktemp(suffix=".db")
os.environ["SECRET_KEY"] = "test-secret"
os.environ["MONITOR_PEPPER"] = "test-pepper"

from app import app, db  # noqa: E402


class LockwellSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = app.test_client()
        with app.app_context():
            db.drop_all()
            db.create_all()

    def test_register_dashboard_vault_flow(self) -> None:
        reg = self.client.post(
            "/api/auth/register",
            data=json.dumps(
                {
                    "email": "demo@lockwell.test",
                    "password": "correct-horse",
                    "displayName": "Demo",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(reg.status_code, 201)
        token = reg.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        dash = self.client.get("/api/dashboard", headers=headers)
        self.assertEqual(dash.status_code, 200)
        body = dash.get_json()
        self.assertGreaterEqual(body["summary"]["monitoredItems"], 1)
        self.assertEqual(body["summary"]["vaultMode"], "zero-knowledge")

        vault = self.client.post(
            "/api/vault",
            data=json.dumps({"ciphertext": "abc", "iv": "def"}),
            content_type="application/json",
            headers=headers,
        )
        self.assertEqual(vault.status_code, 200)

        audit = self.client.get("/api/audit", headers=headers)
        self.assertEqual(audit.status_code, 200)
        actions = {event["action"] for event in audit.get_json()["events"]}
        self.assertIn("auth.register", actions)
        self.assertIn("vault.create", actions)


if __name__ == "__main__":
    unittest.main()
