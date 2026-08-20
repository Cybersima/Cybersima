from __future__ import annotations

from typing import Any, Iterable

from pulsearb.models import Fill
from pulsearb.symbols import split_pair

STABLE = {"USD", "USDT", "USDC"}


def _quote(symbol: str) -> str:
    try:
        _, quote = split_pair(symbol)
        return quote
    except ValueError:
        return ""


def _leg_view(fill: Fill) -> dict[str, Any]:
    note = fill.note or ""
    flatten = "flatten" in note.lower() or "leftover" in note.lower()
    return {
        "venue": fill.venue,
        "symbol": fill.symbol,
        "side": fill.side,
        "qty": round(float(fill.qty or 0), 8),
        "price": round(float(fill.price or 0), 8),
        "notional": round(float(fill.notional or 0), 4),
        "status": fill.status,
        "note": note,
        "ts": fill.ts,
        "flatten": flatten,
        "paper": bool(fill.paper),
    }


def group_trades(fills: Iterable[Fill]) -> list[dict[str, Any]]:
    """Group raw fills into round-trips: opened, each leg, closed back to USD."""
    buckets: dict[str, list[Fill]] = {}
    order: list[str] = []
    for fill in fills:
        key = fill.opportunity_id or f"{fill.ts:.6f}:{fill.venue}:{fill.symbol}:{fill.side}"
        if key not in buckets:
            order.append(key)
            buckets[key] = []
        buckets[key].append(fill)
    trades: list[dict[str, Any]] = []
    for key in order:
        legs = sorted(buckets[key], key=lambda item: item.ts)
        filled = [item for item in legs if item.status == "filled" and item.qty > 0]
        blocked = [item for item in legs if item.status in {"blocked", "error"}]
        flatten_fills = [
            item
            for item in legs
            if "flatten" in (item.note or "").lower() or "leftover" in (item.note or "").lower()
        ]
        live = any(not item.paper for item in legs)
        spent = 0.0
        received = 0.0
        for item in filled:
            quote = _quote(item.symbol)
            usd = item.qty * item.price if item.qty and item.price else float(item.notional or 0)
            if quote not in STABLE:
                continue
            if item.side == "buy":
                spent += usd
            elif item.side == "sell":
                received += usd
        sold_to_usd = any(
            item.status == "filled" and item.side == "sell" and _quote(item.symbol) in STABLE for item in legs
        )
        flatten_failed = any(item.status != "filled" for item in flatten_fills)
        if flatten_failed or (filled and blocked and not sold_to_usd):
            status = "open"
            close_label = "Not fully closed — leftover from this tap may still be on Coinbase"
        elif all(item.status in {"blocked", "error"} for item in legs):
            status = "blocked"
            close_label = next((item.note for item in blocked if item.note), "Did not fill")
        elif sold_to_usd:
            status = "closed"
            close_label = (
                "Closed — sold leftover back to USD" if flatten_fills else "Closed — sold back to USD"
            )
        elif filled:
            status = "closed"
            close_label = "Filled"
        else:
            status = "blocked"
            close_label = next((item.note for item in blocked if item.note), "Did not fill")
        trades.append(
            {
                "id": key,
                "execution": "live" if live else "paper",
                "venue": next((item.venue for item in filled or legs), ""),
                "opened_at": legs[0].ts,
                "closed_at": legs[-1].ts,
                "status": status,
                "close_label": close_label,
                "spent_usd": round(spent, 4),
                "received_usd": round(received, 4),
                "legs": [_leg_view(item) for item in legs],
            }
        )
    return trades
