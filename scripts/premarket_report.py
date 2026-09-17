#!/usr/bin/env python3
"""
Premarket Report — free-data scanner for 8:45 AM ET.

Sources (no paid keys):
  - Yahoo Finance via yfinance (quotes, history, news, options, screeners)
  - Nasdaq public calendar API (earnings)
  - Forex Factory weekly JSON + yfinance Calendars (economic events)

Day-trading watchlist (ALL required):
  gap > 3%, price > $3, mkt cap > $1B, premarket RVOL > 1.5,
  price breaking above yesterday's high

Swing watchlist (ALL required):
  gap >= 8%, price > $3, open/pre above yesterday's high AND above 200-DMA,
  mkt cap >= $800M, real catalyst (earnings today OR news without earnings)

Schedule (America/New_York):
  # crontab — weekdays at 8:45 AM ET
  45 8 * * 1-5 cd /path/to/Cybersima && TZ=America/New_York python3 scripts/premarket_report.py

  # Windows Task Scheduler
  Program: python
  Arguments: C:\\path\\to\\Cybersima\\scripts\\premarket_report.py
  Start in: C:\\path\\to\\Cybersima
  Trigger: weekdays 8:45 AM
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, time as dtime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Optional deps — fail with a clear install hint
# ---------------------------------------------------------------------------
try:
    import httpx
    import pandas as pd
    import yfinance as yf
    from yfinance import EquityQuery
except ImportError as exc:  # pragma: no cover
    sys.stderr.write(
        "Missing dependency. Install with:\n"
        "  pip install yfinance httpx pandas\n"
        f"Detail: {exc}\n"
    )
    raise SystemExit(1) from exc

ET = ZoneInfo("America/New_York")
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}

PREMARKET_OPEN = dtime(4, 0)
REGULAR_OPEN = dtime(9, 30)
REGULAR_CLOSE = dtime(16, 0)
REGULAR_MINUTES = 390.0  # 6.5h session

UPGRADE_RE = re.compile(
    r"\b(upgrad(?:e|es|ed)| initiat(?:e|es|ed) (?:coverage|at)|"
    r"raises? (?:pt|price target|target)|overweight|outperform|"
    r"buys? rating|raised to buy)\b",
    re.I,
)
EARNINGS_RE = re.compile(r"\b(earnings|eps|quarterly results|q[1-4] results)\b", re.I)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass
class Snapshot:
    symbol: str
    name: str = ""
    price: float = 0.0
    prev_close: float = 0.0
    yesterday_high: float = 0.0
    sma200: float = 0.0
    market_cap: float = 0.0
    pre_volume: float = 0.0
    avg_volume: float = 0.0
    gap_pct: float = 0.0
    rvol: float = 0.0
    above_yhigh: bool = False
    above_sma200: bool = False
    market_state: str = ""
    price_source: str = ""  # pre | post | regular


@dataclass
class Catalyst:
    kind: str  # earnings | news | none
    headline: str
    when: str = ""


@dataclass
class Hit:
    snap: Snapshot
    watchlists: list[str] = field(default_factory=list)
    catalyst: Catalyst = field(default_factory=lambda: Catalyst("none", "—"))


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def now_et() -> datetime:
    return datetime.now(ET)


def premarket_elapsed_minutes(now: datetime | None = None) -> float:
    """Minutes since 4:00 AM ET, capped at the premarket window length."""
    now = now or now_et()
    start = now.replace(hour=4, minute=0, second=0, microsecond=0)
    if now.time() < PREMARKET_OPEN:
        return 0.0
    end_cap = now.replace(hour=9, minute=30, second=0, microsecond=0)
    effective = min(now, end_cap)
    return max(0.0, (effective - start).total_seconds() / 60.0)


def parse_money(text: str | None) -> float:
    if not text:
        return 0.0
    cleaned = str(text).replace("$", "").replace(",", "").strip()
    mult = 1.0
    if cleaned.endswith("%"):
        return 0.0
    upper = cleaned.upper()
    if upper.endswith("T"):
        mult, cleaned = 1e12, cleaned[:-1]
    elif upper.endswith("B"):
        mult, cleaned = 1e9, cleaned[:-1]
    elif upper.endswith("M"):
        mult, cleaned = 1e6, cleaned[:-1]
    elif upper.endswith("K"):
        mult, cleaned = 1e3, cleaned[:-1]
    try:
        return float(cleaned) * mult
    except ValueError:
        return 0.0


def parse_pct(text: str | None) -> float:
    if text is None:
        return 0.0
    try:
        return float(str(text).replace("%", "").replace("+", "").replace(",", "").strip())
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def http_get_json(url: str, timeout: float = 25.0) -> Any:
    with httpx.Client(headers=UA, timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Candidate discovery
# ---------------------------------------------------------------------------
def nasdaq_mover_symbols(limit: int = 50) -> list[str]:
    url = f"https://api.nasdaq.com/api/marketmovers?assetclass=stocks&limit={limit}"
    try:
        payload = http_get_json(url)
    except Exception:
        return []
    stocks = ((payload.get("data") or {}).get("STOCKS")) or {}
    symbols: list[str] = []
    for key in ("MostAdvanced", "MostActiveByShareVolume", "MostActiveByDollarVolume", "Nasdaq100Movers"):
        rows = ((stocks.get(key) or {}).get("table") or {}).get("rows") or []
        for row in rows:
            sym = (row.get("symbol") or "").strip().upper()
            if sym and sym.isalpha() and len(sym) <= 5:
                symbols.append(sym)
    return symbols


def yahoo_screener_symbols(count: int = 50) -> list[str]:
    symbols: list[str] = []
    for name in ("day_gainers", "most_actives", "small_cap_gainers"):
        try:
            result = yf.screen(name, count=count)
            for quote in result.get("quotes") or []:
                sym = (quote.get("symbol") or "").upper()
                if sym and sym.isalpha():
                    symbols.append(sym)
        except Exception:
            continue
    try:
        query = EquityQuery(
            "and",
            [
                EquityQuery("gt", ["percentchange", 2.5]),
                EquityQuery("gt", ["intradayprice", 3]),
                EquityQuery("gt", ["intradaymarketcap", 500_000_000]),
                EquityQuery("eq", ["region", "us"]),
            ],
        )
        result = yf.screen(query, count=count, sortField="percentchange", sortAsc=False)
        for quote in result.get("quotes") or []:
            sym = (quote.get("symbol") or "").upper()
            if sym and "." not in sym and sym.isalpha():
                symbols.append(sym)
    except Exception:
        pass
    return symbols


def discover_candidates(extra: Iterable[str] | None = None) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for sym in list(nasdaq_mover_symbols()) + list(yahoo_screener_symbols()) + list(extra or []):
        sym = sym.strip().upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        ordered.append(sym)
    return ordered


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------
def _num(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def choose_trade_price(info: dict[str, Any], allow_extended: bool) -> tuple[float, str, float]:
    """
    Returns (price, source, session_volume).
    Prefers premarket when PRE; optionally uses post for dry-runs.
    """
    state = (info.get("marketState") or "").upper()
    pre_px = _num(info.get("preMarketPrice"))
    pre_vol = _num(info.get("preMarketVolume"))
    post_px = _num(info.get("postMarketPrice"))
    post_vol = _num(info.get("postMarketVolume"))
    reg_px = _num(info.get("regularMarketPrice") or info.get("currentPrice"))
    reg_vol = _num(info.get("regularMarketVolume") or info.get("volume"))

    if state == "PRE" and pre_px > 0:
        return pre_px, "pre", pre_vol
    if allow_extended and state in {"POST", "PREPRE", "POSTPOST"} and post_px > 0:
        # After-hours dry-run: treat post price as the "gap" print vs prior close.
        return post_px, "post", post_vol or reg_vol
    if allow_extended and pre_px > 0:
        return pre_px, "pre", pre_vol
    return reg_px, "regular", reg_vol


def build_snapshot(symbol: str, allow_extended: bool, now: datetime | None = None) -> Snapshot | None:
    now = now or now_et()
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
    except Exception:
        return None

    price, source, session_vol = choose_trade_price(info, allow_extended=allow_extended)
    prev_close = _num(info.get("regularMarketPreviousClose") or info.get("previousClose"))
    if price <= 0 or prev_close <= 0:
        return None

    market_cap = _num(info.get("marketCap"))
    avg_vol = _num(
        info.get("averageDailyVolume10Day")
        or info.get("averageVolume10days")
        or info.get("averageDailyVolume3Month")
        or info.get("averageVolume")
    )

    # History for yesterday high + 200-DMA
    yesterday_high = 0.0
    sma200 = 0.0
    try:
        hist = ticker.history(period="1y", auto_adjust=True)
        if hist is not None and len(hist) >= 2:
            # Last completed regular session = prior row when we are in PRE;
            # when using post/regular after the close, last row is today — use -2 for "yesterday".
            state = (info.get("marketState") or "").upper()
            if state == "PRE" or source == "pre":
                prior = hist.iloc[-1]
            else:
                prior = hist.iloc[-2] if len(hist) >= 2 else hist.iloc[-1]
            yesterday_high = float(prior["High"])
            closes = hist["Close"].dropna()
            if len(closes) >= 200:
                sma200 = float(closes.tail(200).mean())
            elif len(closes):
                sma200 = float(closes.mean())
    except Exception:
        pass

    if yesterday_high <= 0:
        yesterday_high = _num(info.get("regularMarketDayHigh"))

    gap_pct = (price / prev_close - 1.0) * 100.0

    # Premarket RVOL: session volume so far vs expected share of 10-day ADV
    elapsed = premarket_elapsed_minutes(now)
    if source == "pre":
        expected = avg_vol * (max(elapsed, 15.0) / REGULAR_MINUTES) if avg_vol else 0.0
        rvol = (session_vol / expected) if expected > 0 else 0.0
    elif source == "post":
        # After-hours dry-run: compare AH volume to a thin expected slice of ADV
        expected = avg_vol * 0.05 if avg_vol else 0.0
        rvol = (session_vol / expected) if expected > 0 and session_vol > 0 else (
            abs(gap_pct) / 3.0  # soft fallback so dry-runs still surface names
        )
    else:
        expected = avg_vol * (max(elapsed, 15.0) / REGULAR_MINUTES) if avg_vol else 0.0
        rvol = (session_vol / expected) if expected > 0 else 0.0

    return Snapshot(
        symbol=symbol.upper(),
        name=str(info.get("shortName") or info.get("longName") or symbol),
        price=price,
        prev_close=prev_close,
        yesterday_high=yesterday_high,
        sma200=sma200,
        market_cap=market_cap,
        pre_volume=session_vol,
        avg_volume=avg_vol,
        gap_pct=gap_pct,
        rvol=rvol,
        above_yhigh=price > yesterday_high > 0,
        above_sma200=price > sma200 > 0,
        market_state=str(info.get("marketState") or ""),
        price_source=source,
    )


# ---------------------------------------------------------------------------
# Catalysts: earnings + news
# ---------------------------------------------------------------------------
def nasdaq_earnings_symbols(days: int = 1) -> dict[str, str]:
    """Map SYMBOL -> 'BMO/AMC/time-not-supplied' for today..today+days-1."""
    out: dict[str, str] = {}
    today = now_et().date()
    for offset in range(max(1, days)):
        day = today + timedelta(days=offset)
        url = f"https://api.nasdaq.com/api/calendar/earnings?date={day.isoformat()}"
        try:
            payload = http_get_json(url)
        except Exception:
            continue
        rows = ((payload.get("data") or {}).get("rows")) or []
        for row in rows:
            sym = (row.get("symbol") or "").upper().strip()
            if not sym:
                continue
            timing = row.get("time") or "time-not-supplied"
            label = {
                "time-pre-market": "BMO",
                "time-after-hours": "AMC",
                "time-not-supplied": "TNS",
            }.get(timing, timing)
            out[sym] = f"Earnings {day.isoformat()} ({label})"
    return out


def latest_news_headline(symbol: str, max_age_hours: float = 36.0) -> Catalyst:
    try:
        items = yf.Ticker(symbol).news or []
    except Exception:
        return Catalyst("none", "—")

    cutoff = datetime.now(tz=ET) - timedelta(hours=max_age_hours)
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _news_title(item)
        if not title:
            continue
        when = _news_when(item)
        pub_dt: datetime | None = None
        content = item.get("content") if isinstance(item.get("content"), dict) else None
        pub_raw = (content or {}).get("pubDate") or (content or {}).get("displayTime")
        ts = item.get("providerPublishTime")
        if isinstance(pub_raw, str):
            try:
                pub_dt = datetime.fromisoformat(pub_raw.replace("Z", "+00:00")).astimezone(ET)
            except ValueError:
                pub_dt = None
        elif isinstance(ts, (int, float)) and ts > 0:
            pub_dt = datetime.fromtimestamp(ts, tz=ET)
        if pub_dt and pub_dt < cutoff:
            continue
        when = pub_dt.strftime("%Y-%m-%d %H:%M ET") if pub_dt else when
        kind = "earnings" if EARNINGS_RE.search(title) else "news"
        return Catalyst(kind=kind, headline=title[:140], when=when)
    return Catalyst("none", "—")


def resolve_catalyst(symbol: str, earnings_map: dict[str, str]) -> Catalyst:
    if symbol in earnings_map:
        return Catalyst("earnings", earnings_map[symbol], when=now_et().strftime("%Y-%m-%d"))
    news = latest_news_headline(symbol)
    if news.kind != "none":
        return news
    return Catalyst("none", "No earnings today / no fresh headline")


# ---------------------------------------------------------------------------
# Watchlist filters
# ---------------------------------------------------------------------------
def passes_day_trading(snap: Snapshot) -> bool:
    return (
        snap.gap_pct > 3.0
        and snap.price > 3.0
        and snap.market_cap > 1_000_000_000
        and snap.rvol > 1.5
        and snap.above_yhigh
    )


def passes_swing(snap: Snapshot, catalyst: Catalyst) -> bool:
    has_catalyst = catalyst.kind in {"earnings", "news"}
    return (
        snap.gap_pct >= 8.0
        and snap.price > 3.0
        and snap.above_yhigh
        and snap.above_sma200
        and snap.market_cap >= 800_000_000
        and has_catalyst
    )


# ---------------------------------------------------------------------------
# Economic calendar
# ---------------------------------------------------------------------------
def fetch_ff_events(hours_ahead: int = 18) -> list[dict[str, Any]]:
    try:
        data = http_get_json("https://nfs.faireconomy.media/ff_calendar_thisweek.json")
    except Exception:
        data = []
    now = now_et()
    end = now + timedelta(hours=hours_ahead)
    rows: list[dict[str, Any]] = []
    for event in data or []:
        try:
            when = datetime.fromisoformat(event["date"]).astimezone(ET)
        except Exception:
            continue
        if not (now - timedelta(hours=1) <= when <= end):
            continue
        country = str(event.get("country") or "").strip().upper()
        # Forex Factory tags US releases as "USD"
        if country not in {"USD", "US", "USA", "UNITED STATES"}:
            continue
        impact_raw = str(event.get("impact") or "Low").strip().lower()
        if impact_raw not in {"high", "medium", "red", "orange"}:
            continue
        impact = {"red": "High", "orange": "Medium"}.get(impact_raw, impact_raw.title())
        rows.append(
            {
                "when": when,
                "title": event.get("title") or "",
                "impact": impact,
                "forecast": event.get("forecast") or "",
                "previous": event.get("previous") or "",
            }
        )
    rows.sort(key=lambda r: r["when"])
    return rows


def fetch_nasdaq_econ_today() -> list[dict[str, Any]]:
    try:
        payload = http_get_json("https://api.nasdaq.com/api/calendar/economicevents")
    except Exception:
        return []
    rows = ((payload.get("data") or {}).get("rows")) or []
    out: list[dict[str, Any]] = []
    for row in rows:
        country = (row.get("country") or "")
        if "United States" not in country and country not in {"US", "USA", "United States"}:
            continue
        out.append(
            {
                "when_label": row.get("gmt") or "",
                "title": row.get("eventName") or "",
                "actual": row.get("actual") or "",
                "consensus": row.get("consensus") or "",
                "previous": row.get("previous") or "",
            }
        )
    return out


# ---------------------------------------------------------------------------
# Analyst upgrades (Yahoo news search)
# ---------------------------------------------------------------------------
def _news_title(item: dict[str, Any]) -> str:
    content = item.get("content") if isinstance(item.get("content"), dict) else None
    return str(
        (content or {}).get("title")
        or item.get("title")
        or ""
    ).strip()


def _news_publisher(item: dict[str, Any]) -> str:
    content = item.get("content") if isinstance(item.get("content"), dict) else None
    provider = (content or {}).get("provider") if content else None
    if isinstance(provider, dict) and provider.get("displayName"):
        return str(provider["displayName"])
    return str(item.get("publisher") or "")


def _news_when(item: dict[str, Any]) -> str:
    content = item.get("content") if isinstance(item.get("content"), dict) else None
    pub = (content or {}).get("pubDate") or (content or {}).get("displayTime")
    if pub:
        return str(pub)[:19].replace("T", " ")
    ts = item.get("providerPublishTime")
    if isinstance(ts, (int, float)) and ts > 0:
        return datetime.fromtimestamp(ts, tz=ET).strftime("%Y-%m-%d %H:%M")
    return ""


def fetch_analyst_upgrades(limit: int = 12, max_age_days: int = 7) -> list[dict[str, str]]:
    upgrades: list[dict[str, str]] = []
    queries = (
        "analyst upgrade",
        "price target raised",
        "initiates coverage overweight",
        "upgraded to buy",
    )
    seen: set[str] = set()
    cutoff = now_et() - timedelta(days=max_age_days)
    for query in queries:
        try:
            search = yf.Search(query, max_results=10, news_count=15)
            items = list(search.news or [])
        except Exception:
            items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = _news_title(item)
            if not title or title in seen:
                continue
            if not UPGRADE_RE.search(title):
                continue
            when = _news_when(item)
            # Drop stale headlines when we can parse a timestamp
            ts = item.get("providerPublishTime")
            if isinstance(ts, (int, float)) and ts > 0:
                if datetime.fromtimestamp(ts, tz=ET) < cutoff:
                    continue
            seen.add(title)
            upgrades.append(
                {
                    "title": title[:140],
                    "when": when,
                    "source": _news_publisher(item),
                }
            )
            if len(upgrades) >= limit:
                return upgrades
    return upgrades


# ---------------------------------------------------------------------------
# Options flow (Yahoo chains — free / delayed)
# ---------------------------------------------------------------------------
def unusual_options(symbol: str, max_expiries: int = 3) -> list[str]:
    """Flag contracts where volume > 1.5x open interest and volume is meaningful."""
    lines: list[str] = []
    try:
        ticker = yf.Ticker(symbol)
        expiries = list(ticker.options or [])[:max_expiries]
    except Exception:
        return lines
    for exp in expiries:
        try:
            chain = ticker.option_chain(exp)
        except Exception:
            continue
        for side, frame in (("C", chain.calls), ("P", chain.puts)):
            if frame is None or frame.empty:
                continue
            df = frame.copy()
            df["volume"] = df["volume"].fillna(0)
            df["openInterest"] = df["openInterest"].fillna(0)
            df = df[(df["volume"] >= 200) & (df["openInterest"] > 0)]
            if df.empty:
                continue
            df["ratio"] = df["volume"] / df["openInterest"]
            df = df[df["ratio"] >= 1.5].sort_values("volume", ascending=False).head(2)
            for _, row in df.iterrows():
                lines.append(
                    f"{symbol} {exp} {side}{row['strike']:g}  "
                    f"vol={int(row['volume'])} OI={int(row['openInterest'])}  "
                    f"vol/OI={row['ratio']:.1f}"
                )
    return lines[:4]


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------
def fmt_cap(value: float) -> str:
    if value >= 1e12:
        return f"${value/1e12:.1f}T"
    if value >= 1e9:
        return f"${value/1e9:.1f}B"
    if value >= 1e6:
        return f"${value/1e6:.0f}M"
    return f"${value:,.0f}"


def fmt_row(hit: Hit) -> str:
    lists = "+".join(hit.watchlists)
    cat = hit.catalyst.headline
    if hit.catalyst.when:
        cat = f"{cat} [{hit.catalyst.when}]"
    return (
        f"  {hit.snap.symbol:<6}  gap {hit.snap.gap_pct:+6.1f}%  "
        f"${hit.snap.price:<8.2f}  {lists:<16}  {cat}"
    )


def render_report(
    *,
    now: datetime,
    snaps_note: str,
    econ_ff: list[dict[str, Any]],
    econ_nq: list[dict[str, Any]],
    upgrades: list[dict[str, str]],
    hits: list[Hit],
    options_lines: list[str],
    scanned: int,
) -> str:
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append(f"  PREMARKET REPORT  ·  {now.strftime('%A %Y-%m-%d %H:%M %Z')}")
    lines.append(f"  {snaps_note}")
    lines.append("=" * 78)

    lines.append("")
    lines.append("ECONOMIC CALENDAR (US, next ~18h)")
    lines.append("-" * 78)
    if econ_ff:
        for ev in econ_ff[:12]:
            lines.append(
                f"  {ev['when'].strftime('%a %H:%M')}  "
                f"[{ev['impact']:<6}]  {ev['title']}"
                + (f"  (f:{ev['forecast']} p:{ev['previous']})" if ev["forecast"] or ev["previous"] else "")
            )
    elif econ_nq:
        for ev in econ_nq[:12]:
            lines.append(
                f"  {ev['when_label']:<6}  {ev['title']}"
                + (f"  a:{ev['actual']} c:{ev['consensus']} p:{ev['previous']}" if ev["consensus"] else "")
            )
    else:
        lines.append("  (no US high/medium events pulled — check FF/Nasdaq manually)")

    lines.append("")
    lines.append("ANALYST UPGRADES / INITIATIONS (Yahoo news)")
    lines.append("-" * 78)
    if upgrades:
        for u in upgrades[:10]:
            src = f" — {u['source']}" if u.get("source") else ""
            when = f"{u['when']}  " if u.get("when") else ""
            lines.append(f"  • {when}{u['title']}{src}")
    else:
        lines.append("  (none matched upgrade/initiation keywords)")

    day_hits = [h for h in hits if "DAY" in h.watchlists]
    swing_hits = [h for h in hits if "SWING" in h.watchlists]

    lines.append("")
    lines.append(f"DAY TRADING WATCHLIST  ({len(day_hits)} hits)  "
                 f"[gap>3% · >$3 · mcap>$1B · pm RVOL>1.5 · > yday high]")
    lines.append("-" * 78)
    if day_hits:
        lines.append(f"  {'TKR':<6}  {'GAP':>10}  {'PRICE':<9}  {'LIST':<16}  CATALYST")
        for h in day_hits:
            lines.append(fmt_row(h))
    else:
        lines.append("  (no names cleared all day-trading filters)")

    lines.append("")
    lines.append(f"SWING WATCHLIST  ({len(swing_hits)} hits)  "
                 f"[gap≥8% · >$3 · >yday high · >200DMA · mcap≥$800M · catalyst]")
    lines.append("-" * 78)
    if swing_hits:
        lines.append(f"  {'TKR':<6}  {'GAP':>10}  {'PRICE':<9}  {'LIST':<16}  CATALYST")
        for h in swing_hits:
            lines.append(fmt_row(h))
    else:
        lines.append("  (no names cleared all swing filters)")

    lines.append("")
    lines.append("QUALIFIED NAMES — DETAIL")
    lines.append("-" * 78)
    if hits:
        for h in hits:
            s = h.snap
            lines.append(
                f"  {s.symbol}  {s.name}"
                f"\n      gap {s.gap_pct:+.1f}% · ${s.price:.2f} · {fmt_cap(s.market_cap)}"
                f" · RVOL {s.rvol:.2f} · src={s.price_source}"
                f"\n      yday high ${s.yesterday_high:.2f} ({'ABOVE' if s.above_yhigh else 'below'})"
                f" · 200DMA ${s.sma200:.2f} ({'ABOVE' if s.above_sma200 else 'below'})"
                f"\n      watchlist: {', '.join(h.watchlists)}"
                f"\n      catalyst ({h.catalyst.kind}): {h.catalyst.headline}"
            )
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("OPTIONS FLOW (Yahoo delayed · vol ≥ 1.5× OI, vol ≥ 200)")
    lines.append("-" * 78)
    if options_lines:
        for line in options_lines:
            lines.append(f"  {line}")
    else:
        lines.append("  (no unusual contracts on qualified names)")

    lines.append("")
    lines.append(f"Scanned {scanned} unique symbols · free sources only · not trading advice")
    lines.append("=" * 78)
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run(args: argparse.Namespace) -> int:
    now = now_et()
    allow_extended = bool(args.allow_extended)
    # Auto-enable extended dry-run outside the premarket window unless forced off
    outside_premarket = now.time() < PREMARKET_OPEN or now.time() >= REGULAR_OPEN
    if args.auto_extended and outside_premarket and not args.strict_premarket:
        allow_extended = True

    extras = [s.strip().upper() for s in (args.symbols or "").split(",") if s.strip()]
    candidates = discover_candidates(extra=extras)
    if args.max_candidates:
        candidates = candidates[: args.max_candidates]

    earnings_map = nasdaq_earnings_symbols(days=1)

    hits: list[Hit] = []
    options_lines: list[str] = []
    for i, symbol in enumerate(candidates):
        snap = build_snapshot(symbol, allow_extended=allow_extended, now=now)
        if snap is None:
            continue
        # Cheap pre-filter before news/options calls
        if snap.price <= 3 or snap.gap_pct < 3 or snap.market_cap < 800_000_000:
            continue
        catalyst = resolve_catalyst(symbol, earnings_map)
        lists: list[str] = []
        if passes_day_trading(snap):
            lists.append("DAY")
        if passes_swing(snap, catalyst):
            lists.append("SWING")
        if not lists:
            continue
        hits.append(Hit(snap=snap, watchlists=lists, catalyst=catalyst))
        if not args.skip_options:
            options_lines.extend(unusual_options(symbol))
        if args.sleep:
            time.sleep(args.sleep)
        if args.verbose:
            print(f"[{i+1}/{len(candidates)}] {symbol} gap={snap.gap_pct:+.1f}% lists={lists}", file=sys.stderr)

    hits.sort(key=lambda h: (-len(h.watchlists), -h.snap.gap_pct))

    econ_ff = fetch_ff_events(hours_ahead=18)
    econ_nq = fetch_nasdaq_econ_today() if not econ_ff else []
    upgrades = fetch_analyst_upgrades()

    state_note = (
        f"Price source prefers PREMARKET"
        + ("; extended-hours fallback ON (dry-run)" if allow_extended else "; strict premarket only")
    )
    report = render_report(
        now=now,
        snaps_note=state_note,
        econ_ff=econ_ff,
        econ_nq=econ_nq,
        upgrades=upgrades,
        hits=hits,
        options_lines=options_lines,
        scanned=len(candidates),
    )

    print(report)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        stamp = now.strftime("%Y%m%d")
        if out_path.is_dir() or str(out_path).endswith("/"):
            out_path = out_path / f"premarket_{stamp}.txt"
        out_path.write_text(report, encoding="utf-8")
        print(f"Wrote {out_path}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Automated 8:45 AM ET premarket report (free sources)")
    p.add_argument("--out", help="Write report to file or directory")
    p.add_argument("--symbols", default="", help="Extra comma-separated tickers to force-scan")
    p.add_argument("--max-candidates", type=int, default=80, help="Cap symbols enriched via Yahoo")
    p.add_argument("--allow-extended", action="store_true", help="Use postmarket prices when not in PRE")
    p.add_argument(
        "--auto-extended",
        action="store_true",
        default=True,
        help="Outside 4:00–9:30 ET, auto-use extended prices (default on)",
    )
    p.add_argument(
        "--strict-premarket",
        action="store_true",
        help="Never fall back to post/regular prices (for true 8:45 AM runs)",
    )
    p.add_argument("--skip-options", action="store_true", help="Skip options-flow section (faster)")
    p.add_argument("--sleep", type=float, default=0.05, help="Pause between Yahoo detail calls")
    p.add_argument("--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
