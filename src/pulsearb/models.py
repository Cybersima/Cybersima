from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class Venue(str, Enum):
    BINANCE = "binance"
    YAHOO = "yahoo"
    SIMULATOR = "simulator"


class OpportunityKind(str, Enum):
    CROSS_VENUE = "cross_venue"
    TRIANGULAR = "triangular"
    ALERT = "alert"


class ExecutionMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


@dataclass(slots=True)
class Quote:
    venue: str
    native_symbol: str
    canonical: str
    bid: float
    ask: float
    ts: float
    asset_class: str = "crypto"
    executable: bool = False

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0 if self.bid and self.ask else 0.0

    @property
    def spread_bps(self) -> float:
        if not self.mid:
            return 0.0
        return (self.ask - self.bid) / self.mid * 10_000

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mid"] = round(self.mid, 8)
        data["spread_bps"] = round(self.spread_bps, 2)
        return data


@dataclass(slots=True)
class Leg:
    action: str  # buy | sell
    venue: str
    symbol: str
    price: float
    executable: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Opportunity:
    kind: OpportunityKind
    edge_bps: float
    net_edge_bps: float
    notional: float
    legs: list[Leg]
    summary: str
    executable: bool
    ts: float
    id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "edge_bps": round(self.edge_bps, 2),
            "net_edge_bps": round(self.net_edge_bps, 2),
            "notional": self.notional,
            "legs": [leg.to_dict() for leg in self.legs],
            "summary": self.summary,
            "executable": self.executable,
            "ts": self.ts,
        }


@dataclass(slots=True)
class Fill:
    venue: str
    symbol: str
    side: str
    qty: float
    price: float
    notional: float
    ts: float
    paper: bool
    opportunity_id: str
    status: str = "filled"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EngineStats:
    quotes: int = 0
    markets_live: int = 0
    scans: int = 0
    opportunities: int = 0
    paper_pnl: float = 0.0
    live_blocked: int = 0
    last_scan_ms: float = 0.0
    started_at: float = 0.0
    feed_status: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
