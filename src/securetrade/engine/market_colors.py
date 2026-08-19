from __future__ import annotations

from securetrade.models import PaperPosition


def pair_key(text: str) -> str:
    raw = (text or "").upper().replace("/", "-").replace(" ", "")
    for token in ("USDT", "USDC", "FDUSD"):
        if raw.endswith(f"-{token}") or raw.endswith(token):
            raw = raw.replace(token, "USD")
    return raw


def fill_ratio_for(outcome: str) -> float:
    flag = (outcome or "").upper()
    if flag == "CAPTURED":
        return 1.0
    if flag == "REVERSED":
        return 0.5
    return 0.0


def outcome_tone(outcome: str, actual_pnl: float = 0.0) -> str:
    """green=profit, red=loss, blue=missed, orange=reversal."""
    flag = (outcome or "").upper()
    if flag == "REVERSED":
        return "reversal"
    if flag in {"MISSED", "EXPIRED", "CANCELLED", "CANCEL", "BLOCKED"}:
        return "missed"
    if flag == "CAPTURED" and actual_pnl < 0:
        return "loss"
    if flag == "CAPTURED" or actual_pnl > 0:
        return "profit"
    if actual_pnl < 0:
        return "loss"
    return ""


def latest_tones(positions: list[PaperPosition]) -> dict[str, str]:
    tones: dict[str, str] = {}
    for position in positions:
        key = pair_key(position.pair)
        if key and key not in tones:
            tones[key] = outcome_tone(position.outcome, position.actual_pnl)
    return tones
