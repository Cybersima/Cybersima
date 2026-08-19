from __future__ import annotations

import csv
import io
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pulsearb.models import Fill, Opportunity

# Spreadsheet columns, in export order.
REPORT_HEADERS = [
    "ID",
    "Detected Time",
    "Strategy",
    "Market",
    "Route",
    "Financial",
    "Execution",
    "Guardian",
    "Guardian",
    "Expected P&L",
    "Realized P&L",
    "Edge Lifetime",
    "Close Reason",
    "Buy Venue",
    "Sell Venue",
    "Raw Edge",
    "Net Edge (bps)",
    "Fee (bps)",
    "Slippage (bps)",
    "Fill Ratio",
    "Paper Notional",
]

STRATEGY_LABEL = {
    "cross_venue": "Cross-venue",
    "triangular": "Triangular",
    "alert": "Alert",
}


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _market(opportunity: Opportunity) -> str:
    from pulsearb.symbols import canonical_from_pair, comparison_key

    for leg in opportunity.legs:
        try:
            return comparison_key(canonical_from_pair(leg.symbol))
        except ValueError:
            continue
    return ""


def _venues(opportunity: Opportunity) -> tuple[str, str]:
    buy = next((leg.venue for leg in opportunity.legs if leg.action == "buy"), "")
    sell = next((leg.venue for leg in opportunity.legs if leg.action == "sell"), "")
    if not buy and opportunity.legs:
        buy = opportunity.legs[0].venue
    if not sell and len(opportunity.legs) > 1:
        sell = opportunity.legs[-1].venue
    return buy, sell


def _route(opportunity: Opportunity) -> str:
    if not opportunity.legs:
        return opportunity.summary
    return " → ".join(f"{leg.action} {leg.symbol} @{leg.venue}" for leg in opportunity.legs)


def _fee_bps(opportunity: Opportunity, fee_map: dict[str, float]) -> float:
    return sum(float(fee_map.get(leg.venue, 0.0)) for leg in opportunity.legs)


def build_report_row(
    opportunity: Opportunity,
    fills: Iterable[Fill],
    *,
    paper: bool,
    killed: bool,
    fee_map: dict[str, float],
    slippage_bps: float,
    closed_at: float | None = None,
) -> dict[str, Any]:
    fill_list = list(fills)
    closed_at = closed_at or time.time()
    expected = opportunity.notional * (opportunity.net_edge_bps / 10_000)
    primary = fill_list[0] if fill_list else None
    status = primary.status if primary else ("alert_only" if not opportunity.executable else "open")
    filled = status == "filled"
    blocked = status == "blocked"
    buy_venue, sell_venue = _venues(opportunity)
    if killed:
        guardian_status, guardian_detail = "block", "kill switch is on"
    elif blocked:
        guardian_status, guardian_detail = "block", primary.note if primary and primary.note else "blocked"
    elif not opportunity.executable:
        guardian_status, guardian_detail = "watch", "data-only alert"
    else:
        guardian_status, guardian_detail = "pass", "ok"
    if filled:
        close_reason = "paper_fill" if paper else "live_fill"
        realized = expected
        fill_ratio = 1.0
        execution = "paper" if paper else "live"
    elif blocked:
        close_reason = primary.note if primary and primary.note else "blocked"
        realized = 0.0
        fill_ratio = 0.0
        execution = "blocked"
    else:
        close_reason = "alert_only"
        realized = 0.0
        fill_ratio = 0.0
        execution = "alert"
    return {
        "ID": opportunity.id,
        "Detected Time": _iso(opportunity.ts),
        "Strategy": STRATEGY_LABEL.get(opportunity.kind.value, opportunity.kind.value),
        "Market": _market(opportunity),
        "Route": _route(opportunity),
        "Financial": "paper USD" if paper else "live USD",
        "Execution": execution,
        "Guardian Status": guardian_status,
        "Guardian Detail": guardian_detail,
        "Expected P&L": round(expected, 6),
        "Realized P&L": round(realized, 6),
        "Edge Lifetime": round(max(0.0, closed_at - opportunity.ts), 3),
        "Close Reason": close_reason,
        "Buy Venue": buy_venue,
        "Sell Venue": sell_venue,
        "Raw Edge": round(opportunity.edge_bps, 4),
        "Net Edge (bps)": round(opportunity.net_edge_bps, 4),
        "Fee (bps)": round(_fee_bps(opportunity, fee_map), 4),
        "Slippage (bps)": round(slippage_bps, 4),
        "Fill Ratio": round(fill_ratio, 4),
        "Paper Notional": round(opportunity.notional, 4),
    }


def ordered_values(row: dict[str, Any]) -> list[Any]:
    return [
        row.get("ID", ""),
        row.get("Detected Time", ""),
        row.get("Strategy", ""),
        row.get("Market", ""),
        row.get("Route", ""),
        row.get("Financial", ""),
        row.get("Execution", ""),
        row.get("Guardian Status", ""),
        row.get("Guardian Detail", ""),
        row.get("Expected P&L", ""),
        row.get("Realized P&L", ""),
        row.get("Edge Lifetime", ""),
        row.get("Close Reason", ""),
        row.get("Buy Venue", ""),
        row.get("Sell Venue", ""),
        row.get("Raw Edge", ""),
        row.get("Net Edge (bps)", ""),
        row.get("Fee (bps)", ""),
        row.get("Slippage (bps)", ""),
        row.get("Fill Ratio", ""),
        row.get("Paper Notional", ""),
    ]


class ProfitLedger:
    """In-memory profit report that also writes an Excel-friendly CSV."""

    def __init__(self, csv_path: Path | None = None, max_rows: int = 5000) -> None:
        self.rows: deque[dict[str, Any]] = deque(maxlen=max_rows)
        self.csv_path = csv_path.resolve() if csv_path else None
        self.total_rows = 0
        if self.csv_path:
            self.csv_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, row: dict[str, Any]) -> None:
        self.rows.append(row)
        self.total_rows += 1
        if self.csv_path:
            try:
                self._append_csv(row)
            except OSError:
                # Excel or another program may have the file open on Windows.
                pass

    def record_opportunity(
        self,
        opportunity: Opportunity,
        fills: Iterable[Fill],
        *,
        paper: bool,
        killed: bool,
        fee_map: dict[str, float],
        slippage_bps: float,
    ) -> dict[str, Any]:
        row = build_report_row(
            opportunity,
            fills,
            paper=paper,
            killed=killed,
            fee_map=fee_map,
            slippage_bps=slippage_bps,
        )
        self.record(row)
        return row

    def as_dicts(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.rows]

    def to_csv_bytes(self) -> bytes:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(REPORT_HEADERS)
        for row in self.rows:
            writer.writerow(ordered_values(row))
        return buffer.getvalue().encode("utf-8-sig")

    def export_csv_bytes(self) -> bytes:
        """Prefer the on-disk log (full session) over the in-memory window."""
        if self.csv_path and self.csv_path.exists() and self.csv_path.stat().st_size > 32:
            try:
                return self.csv_path.read_bytes()
            except OSError:
                pass
        return self.to_csv_bytes()

    def _append_csv(self, row: dict[str, Any]) -> None:
        assert self.csv_path is not None
        new_file = not self.csv_path.exists() or self.csv_path.stat().st_size == 0
        with self.csv_path.open("a", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            if new_file:
                writer.writerow(REPORT_HEADERS)
            writer.writerow(ordered_values(row))
