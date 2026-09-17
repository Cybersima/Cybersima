"""Unit tests for premarket report watchlist filters (no network)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "premarket_report.py"


def _load():
    name = "premarket_report"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # required before dataclasses process the module
    spec.loader.exec_module(mod)
    return mod


pm = _load()


def _snap(**kwargs):
    base = dict(
        symbol="TEST",
        price=25.0,
        prev_close=20.0,
        yesterday_high=24.0,
        sma200=22.0,
        market_cap=2_000_000_000,
        gap_pct=10.0,
        rvol=2.0,
        above_yhigh=True,
        above_sma200=True,
    )
    base.update(kwargs)
    return pm.Snapshot(**base)


def test_day_trading_requires_all_filters():
    assert pm.passes_day_trading(_snap())
    assert not pm.passes_day_trading(_snap(gap_pct=2.9))
    assert not pm.passes_day_trading(_snap(price=2.5, gap_pct=10))
    assert not pm.passes_day_trading(_snap(market_cap=900_000_000))
    assert not pm.passes_day_trading(_snap(rvol=1.4))
    assert not pm.passes_day_trading(_snap(above_yhigh=False))


def test_swing_requires_catalyst_and_200dma():
    cat = pm.Catalyst("news", "Company announces AI partnership")
    assert pm.passes_swing(_snap(gap_pct=8.0), cat)
    assert not pm.passes_swing(_snap(gap_pct=7.9), cat)
    assert not pm.passes_swing(_snap(above_sma200=False), cat)
    assert not pm.passes_swing(_snap(market_cap=700_000_000), cat)
    assert not pm.passes_swing(_snap(), pm.Catalyst("none", "—"))


def test_gap_math_helpers():
    assert pm.parse_money("$1.2B") == pytest.approx(1.2e9)
    assert pm.parse_pct("+12.5%") == pytest.approx(12.5)
