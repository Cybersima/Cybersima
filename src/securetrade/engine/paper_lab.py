from __future__ import annotations

import time
from collections import deque

from securetrade.models import CommitDecision, PaperOutcome, PaperPosition


class PaperLab:
    """Original v0.3.7 Paper Lab lifecycle: CAPTURED / REVERSED / MISSED / EXPIRED.

    CANCEL never enters this lab.
    """

    def __init__(self, timeout_seconds: float = 12.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.open: dict[str, PaperPosition] = {}
        self.closed: deque[PaperPosition] = deque(maxlen=200)

    def admit(self, position: PaperPosition) -> PaperPosition | None:
        if position.commit_kind == CommitDecision.CANCEL.value:
            return None
        self.open[position.opportunity_id] = position
        return position

    def open_from_opportunity(
        self,
        opportunity_id: str,
        pair: str,
        notional: float,
        expected_pnl: float,
        commit_kind: str,
        expected_net_edge_bps: float,
        trust_score: int,
        now: float | None = None,
        timeout_seconds: float | None = None,
        side: str = "",
        entry_price: float = 0.0,
        stop_price: float = 0.0,
        target_price: float = 0.0,
        timeframe: str = "",
        asset_class: str = "",
    ) -> PaperPosition | None:
        if commit_kind == CommitDecision.CANCEL.value:
            return None
        now = now or time.time()
        position = PaperPosition(
            opportunity_id=opportunity_id,
            pair=pair,
            notional=notional,
            expected_pnl=expected_pnl,
            actual_pnl=0.0,
            outcome=PaperOutcome.OPEN.value,
            commit_kind=commit_kind,
            opened_at=now,
            expected_net_edge_bps=expected_net_edge_bps,
            trust_score=trust_score,
            side=side,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            timeframe=timeframe,
            asset_class=asset_class,
            timeout_seconds=timeout_seconds,
            last_price=entry_price,
        )
        return self.admit(position)

    def close(self, opportunity_id: str, outcome: PaperOutcome, actual_pnl: float, note: str = "") -> PaperPosition:
        position = self.open.pop(opportunity_id)
        position.outcome = outcome.value
        position.actual_pnl = actual_pnl
        position.closed_at = time.time()
        if position.notional:
            position.actual_net_edge_bps = actual_pnl / position.notional * 10_000
        if note:
            position.notes.append(note)
        self.closed.appendleft(position)
        return position

    def force(self, opportunity_id: str, outcome: PaperOutcome, actual_pnl: float, note: str = "") -> PaperPosition:
        if opportunity_id not in self.open:
            raise KeyError(opportunity_id)
        return self.close(opportunity_id, outcome, actual_pnl, note)

    def expire_open(self, now: float | None = None) -> list[PaperPosition]:
        now = now or time.time()
        expired: list[PaperPosition] = []
        for oid, position in list(self.open.items()):
            limit = self.timeout_seconds if position.timeout_seconds is None else position.timeout_seconds
            if limit <= 0:
                continue
            if now - position.opened_at >= limit:
                expired.append(self.close(oid, PaperOutcome.EXPIRED, 0.0, "timed out before capture"))
        return expired

    def resolve_against_edge(self, opportunity_id: str, live_edge_bps: float, reverse_shock: bool = False) -> PaperPosition | None:
        position = self.open.get(opportunity_id)
        if not position:
            return None
        if reverse_shock:
            pnl = -abs(position.expected_pnl or position.notional * 0.002)
            return self.close(opportunity_id, PaperOutcome.REVERSED, pnl, "adverse move after first leg")
        if live_edge_bps <= 0:
            return self.close(opportunity_id, PaperOutcome.MISSED, 0.0, "window closed before both legs filled")
        if live_edge_bps >= position.expected_net_edge_bps * 0.4:
            pnl = position.notional * (live_edge_bps / 10_000)
            return self.close(opportunity_id, PaperOutcome.CAPTURED, pnl, "both legs filled")
        return None
