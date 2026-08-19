from securetrade.engine.market_colors import latest_tones, outcome_tone, pair_key
from securetrade.models import PaperPosition


def test_pair_key_normalizes_usd_stables() -> None:
    assert pair_key("BTC/USDC") == "BTC-USD"
    assert pair_key("BTC-USD") == "BTC-USD"


def test_outcome_colors() -> None:
    assert outcome_tone("CAPTURED", 0.31) == "profit"
    assert outcome_tone("CAPTURED", -0.20) == "loss"
    assert outcome_tone("MISSED", 0) == "missed"
    assert outcome_tone("EXPIRED", 0) == "missed"
    assert outcome_tone("REVERSED", -0.20) == "reversal"


def test_latest_tone_wins() -> None:
    older = PaperPosition("a", "BTC/USDC", 100, 1, 0.3, "CAPTURED", "COMMIT", 1)
    newer = PaperPosition("b", "BTC-USD", 100, 1, -0.2, "REVERSED", "COMMIT", 2)
    tones = latest_tones([newer, older])
    assert tones["BTC-USD"] == "reversal"
