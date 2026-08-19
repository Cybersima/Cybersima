from securetrade.config import AppConfig
from securetrade.engine.runner import Engine
from securetrade.engine.starter import expected_dollars
from securetrade.engine.why import customer_details
from securetrade.models import OperatingMode


def test_expected_dollars_on_one_hundred() -> None:
    assert expected_dollars(100, 31) == 0.31


def test_learn_ten_is_paper_only() -> None:
    engine = Engine(AppConfig())
    engine.apply_starter("learn_10")
    assert engine.stats.account_value == 10
    assert engine.capital.max_trade_size == 10
    assert engine.config.execution_mode == "paper"
    auto = engine.set_mode(OperatingMode.AUTO)
    assert auto["ok"] is False
    assert engine.pipeline.mode is OperatingMode.LEARN


def test_live_hundred_keeps_auto_off_and_caps_ticket() -> None:
    engine = Engine(AppConfig())
    result = engine.apply_starter("live_100")
    assert result["max_ticket"] == 100
    assert engine.risk.daily_loss_limit_usdt == 5
    auto = engine.set_mode(OperatingMode.AUTO)
    assert auto["ok"] is False
    assert engine.pipeline.mode is OperatingMode.ASSIST


def test_why_details_are_plain_language() -> None:
    from securetrade.engine.forced import make_forced_opportunity

    engine = Engine(AppConfig())
    opp = make_forced_opportunity(engine.book, "captured")
    details = customer_details(opp)
    assert details["headline"] == "Why this trade?"
    assert details["expected_profit_usd"] == expected_dollars(100, 28)
    assert "not a guarantee" in details["honest_note"].lower()
    blob = " ".join(str(v) for v in details.values())
    assert "def " not in blob
    assert "{" not in details["honest_note"]
