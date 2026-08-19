from __future__ import annotations

from dataclasses import dataclass

from securetrade.models import OperatingMode


@dataclass(frozen=True)
class StarterRung:
    id: str
    title: str
    summary: str
    equity: float
    max_ticket: float
    daily_loss: float
    max_drawdown_pct: float
    allow_live: bool
    allow_auto: bool
    default_mode: OperatingMode


# Learn at any size. Paper and first live floor are $100.
# $10 live is intentionally omitted: fees dominate a $10 ticket.
RUNGS: dict[str, StarterRung] = {
    "learn_10": StarterRung(
        id="learn_10",
        title="Learn · $10 practice",
        summary="Simulated $10 so anyone can start. See expected dollars (often a few cents). Not live trading.",
        equity=10.0,
        max_ticket=10.0,
        daily_loss=1.0,
        max_drawdown_pct=20.0,
        allow_live=False,
        allow_auto=False,
        default_mode=OperatingMode.LEARN,
    ),
    "learn_100": StarterRung(
        id="learn_100",
        title="Learn · $100 practice",
        summary="Recommended first step. Simulated $100. A 0.31% capture is about $0.31 — shown before every trade.",
        equity=100.0,
        max_ticket=100.0,
        daily_loss=5.0,
        max_drawdown_pct=10.0,
        allow_live=False,
        allow_auto=False,
        default_mode=OperatingMode.LEARN,
    ),
    "paper_100": StarterRung(
        id="paper_100",
        title="Paper · $100",
        summary="Same $100 ticket with the full Paper Lab path. Still simulated money. Assist can require your approval.",
        equity=100.0,
        max_ticket=100.0,
        daily_loss=5.0,
        max_drawdown_pct=10.0,
        allow_live=False,
        allow_auto=False,
        default_mode=OperatingMode.ASSIST,
    ),
    "live_100": StarterRung(
        id="live_100",
        title="Micro live · $100",
        summary="First live floor after paper. Max ticket $100, daily loss $5, Auto off. Not a profit plan — a 0.31% win is about 31 cents.",
        equity=100.0,
        max_ticket=100.0,
        daily_loss=5.0,
        max_drawdown_pct=10.0,
        allow_live=True,
        allow_auto=False,
        default_mode=OperatingMode.ASSIST,
    ),
}

DEFAULT_RUNG = "learn_100"
LADDER_ORDER = ("learn_10", "learn_100", "paper_100", "live_100")


def get_rung(rung_id: str) -> StarterRung:
    return RUNGS.get(rung_id, RUNGS[DEFAULT_RUNG])


def ladder_public() -> list[dict]:
    return [
        {
            "id": RUNGS[key].id,
            "title": RUNGS[key].title,
            "summary": RUNGS[key].summary,
            "equity": RUNGS[key].equity,
            "max_ticket": RUNGS[key].max_ticket,
            "daily_loss": RUNGS[key].daily_loss,
            "allow_live": RUNGS[key].allow_live,
            "allow_auto": RUNGS[key].allow_auto,
            "default_mode": RUNGS[key].default_mode.value,
        }
        for key in LADDER_ORDER
    ]


def expected_dollars(notional: float, net_edge_bps: float) -> float:
    return round(notional * (net_edge_bps / 10_000), 4)
