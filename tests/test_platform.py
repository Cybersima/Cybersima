from securetrade.academy import LESSONS, explain_rejection, lesson
from securetrade.engine.takeover import TakeoverGuard
from securetrade.licensing import mode_allowed
from securetrade.models import OperatingMode
from securetrade.security.credentials import CredentialVault


def test_academy_covers_core_topics() -> None:
    ids = {item["id"] for item in LESSONS}
    for needed in ("arbitrage", "slippage", "phishing", "why-rejected", "learn-assist-auto", "starter-ladder"):
        assert needed in ids
    assert lesson("limit-orders") is not None
    explained = explain_rejection(["Unusual liquidity behavior"])
    assert "blocked" in explained["body"].lower()


def test_takeover_suspends_on_new_device() -> None:
    guard = TakeoverGuard()
    assert guard.observe("laptop", "1.1.1.1", "us") is False
    assert guard.observe("phone", "8.8.8.8", "ru") is True
    assert guard.suspended is True
    guard.reauthenticate("phone", "8.8.8.8", "ru")
    assert guard.suspended is False


def test_personal_edition_blocks_auto() -> None:
    assert mode_allowed("personal", OperatingMode.AUTO) is False
    assert mode_allowed("professional", OperatingMode.AUTO) is True


def test_credential_vault_round_trip(tmp_path) -> None:
    vault = CredentialVault(tmp_path)
    vault.store_exchange_key("coinbase", "key", "secret")
    loaded = vault.load()
    assert loaded["coinbase"]["api_key"] == "key"
    assert loaded["coinbase"]["withdrawal_enabled"] is False
