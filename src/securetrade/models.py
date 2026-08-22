from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from typing import Any


class Venue(str, Enum):
    BINANCE = "binance"
    COINBASE = "coinbase"
    KRAKEN = "kraken"
    GEMINI = "gemini"
    BITSTAMP = "bitstamp"
    YAHOO = "yahoo"
    SIMULATOR = "simulator"


class OpportunityKind(str, Enum):
    CROSS_VENUE = "cross_venue"
    TRIANGULAR = "triangular"
    ALERT = "alert"
    FOREX_DIRECTIONAL = "forex_directional"
    FOREX_ARBITRAGE = "forex_arbitrage"


class ExecutionMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class OperatingMode(str, Enum):
    LEARN = "learn"
    ASSIST = "assist"
    AUTO = "auto"


class HandoffState(str, Enum):
    ATOMIC_READY = "ATOMIC_READY"
    BLOCKED = "BLOCKED"
    PENDING_APPROVAL = "PENDING_APPROVAL"


class CommitDecision(str, Enum):
    COMMIT = "COMMIT"
    RESEARCH_COMMIT = "RESEARCH_COMMIT"
    CANCEL = "CANCEL"


class PaperOutcome(str, Enum):
    OPEN = "OPEN"
    CAPTURED = "CAPTURED"
    REVERSED = "REVERSED"
    MISSED = "MISSED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class KillSource(str, Enum):
    CUSTOMER = "customer"
    RISK = "risk"
    ADMIN = "admin"
    SECURITY = "security"
    HEALTH = "health"


class MarketRegime(str, Enum):
    NORMAL = "normal"
    TRENDING = "trending"
    HIGHLY_VOLATILE = "highly_volatile"
    ILLIQUID = "illiquid"
    ABNORMAL = "abnormal"


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
    bid_size: float = 0.0
    ask_size: float = 0.0
    latency_ms: float = 0.0

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
    size: float = 0.0

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
    pair: str = ""
    trust_score: int = 0
    quality_score: float = 0.0
    security_score: int = 0
    execution_confidence: float = 0.0
    expected_gross_spread_bps: float = 0.0
    estimated_fees_bps: float = 0.0
    estimated_slippage_bps: float = 0.0
    expected_net_edge_bps: float = 0.0
    max_anticipated_loss: float = 0.0
    liquidity_usd: float = 0.0
    why: list[str] = field(default_factory=list)
    why_blocked: list[str] = field(default_factory=list)
    guardian_allowed: bool = True
    regime: str = MarketRegime.NORMAL.value
    side: str = ""
    timeframe: str = ""
    entry_price: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    pattern: str = ""
    confluence: int = 0
    timeframes_aligned: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value if isinstance(self.kind, OpportunityKind) else self.kind,
            "pair": self.pair or _pair_from_summary(self.summary, self.legs),
            "edge_bps": round(self.edge_bps, 2),
            "net_edge_bps": round(self.net_edge_bps, 2),
            "expected_net_edge_bps": round(self.expected_net_edge_bps or self.net_edge_bps, 2),
            "notional": self.notional,
            "legs": [leg.to_dict() for leg in self.legs],
            "summary": self.summary,
            "executable": self.executable,
            "ts": self.ts,
            "trust_score": self.trust_score,
            "quality_score": round(self.quality_score, 4),
            "security_score": self.security_score,
            "execution_confidence": round(self.execution_confidence, 3),
            "expected_gross_spread_bps": round(self.expected_gross_spread_bps or self.edge_bps, 2),
            "estimated_fees_bps": round(self.estimated_fees_bps, 2),
            "estimated_slippage_bps": round(self.estimated_slippage_bps, 2),
            "max_anticipated_loss": round(self.max_anticipated_loss, 4),
            "liquidity_usd": round(self.liquidity_usd, 2),
            "why": list(self.why),
            "why_blocked": list(self.why_blocked),
            "guardian_allowed": self.guardian_allowed,
            "regime": self.regime,
            "side": self.side,
            "timeframe": self.timeframe,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "pattern": self.pattern,
            "confluence": self.confluence,
            "timeframes_aligned": list(self.timeframes_aligned),
        }

    def with_updates(self, **kwargs: Any) -> Opportunity:
        return replace(self, **kwargs)


def _pair_from_summary(summary: str, legs: list[Leg]) -> str:
    if legs:
        symbol = legs[0].symbol.replace("-", "").upper()
        if "BTC" in symbol:
            return "BTC/USDC" if "USDC" in symbol or "USD" in symbol else legs[0].symbol
        return legs[0].symbol.replace("-", "/")
    return summary.split(" ")[0] if summary else ""


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
    handoff_atomic_ready: int = 0
    recovery_commit_pass: int = 0
    recovery_research_pass: int = 0
    recovery_cancel: int = 0
    paper_opened: int = 0
    captured: int = 0
    reversed: int = 0
    missed: int = 0
    expired: int = 0
    guardian_blocks: int = 0
    security_score: int = 100
    account_value: float = 25000.0
    today_pnl: float = 0.0
    month_pnl: float = 0.0
    max_drawdown: float = 0.0
    peak_equity: float = 25000.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TrustBreakdown:
    score: int
    label: str
    venue_reliability: float
    asset_reputation: float
    liquidity: float
    book_quality: float
    volatility: float
    data_consistency: float
    abnormal_behavior: float
    security_indicators: float
    execution_risk: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GuardianVerdict:
    allowed: bool
    severity: str
    reasons: list[str]
    policy: str = "security_first"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SimulationResult:
    viable: bool
    fillable_notional: float
    expected_slippage_bps: float
    expected_net_edge_bps: float
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RecoveryCommitRecord:
    opportunity_id: str
    decision: str
    commit_edge_bps: float
    edge_retention: float
    confirmation_age_ms: float
    book_age_ms: float
    latency_skew_ms: float
    atomic_fill: bool
    ts: float
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PaperPosition:
    opportunity_id: str
    pair: str
    notional: float
    expected_pnl: float
    actual_pnl: float
    outcome: str
    commit_kind: str
    opened_at: float
    closed_at: float | None = None
    expected_net_edge_bps: float = 0.0
    actual_net_edge_bps: float = 0.0
    trust_score: int = 0
    notes: list[str] = field(default_factory=list)
    side: str = ""
    entry_price: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    timeframe: str = ""
    asset_class: str = ""
    timeout_seconds: float | None = None
    last_price: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JournalEntry:
    id: str
    ts: float
    action: str
    opportunity_id: str
    decision: str
    sources: list[str]
    expected_profit: float
    actual_result: float | None
    risk_score: int
    security_decision: str
    details: dict[str, Any]
    hash: str = ""
    prev_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HealthReport:
    ok: bool
    api_connectivity: str
    websocket_latency_ms: float
    clock_skew_ms: float
    memory_mb: float
    cpu_pct: float
    database: str
    stale_feeds: list[str]
    exchange_status: dict[str, str]
    execution_latency_ms: float
    issues: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
