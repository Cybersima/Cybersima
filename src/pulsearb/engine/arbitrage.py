from __future__ import annotations

import hashlib
import itertools
import time
from collections import defaultdict

from pulsearb.engine.book import MarketBook
from pulsearb.engine.money import route_fee_bps
from pulsearb.models import Leg, Opportunity, OpportunityKind, Quote
from pulsearb.symbols import comparison_key, split_pair


def _oid(*parts: str) -> str:
    raw = "|".join(parts)
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def detect_cross_venue(
    book: MarketBook,
    pairs: list[dict],
    min_edge_bps: float,
    fee_bps_by_venue: dict[str, float],
    extra_slippage_bps: float,
    notional: float,
    max_raw_edge_bps: float = 300.0,
    max_quote_age: float | None = None,
    max_quote_skew: float = 1.5,
) -> list[Opportunity]:
    found: list[Opportunity] = []
    now = time.time()
    for pair in pairs:
        left_spec = pair["left"]
        right_spec = pair["right"]
        left = book.get(left_spec["venue"], left_spec["symbol"])
        right = book.get(right_spec["venue"], right_spec["symbol"])
        if left is None:
            left = book.get("simulator", left_spec["symbol"])
        if right is None:
            right = book.get("simulator", right_spec["symbol"])
        if not left or not right:
            continue
        found.extend(
            _cross_from_quotes(
                left,
                right,
                pair.get("id", left.canonical),
                min_edge_bps,
                fee_bps_by_venue,
                extra_slippage_bps,
                notional,
                now,
                max_raw_edge_bps=max_raw_edge_bps,
                max_quote_age=max_quote_age,
                max_quote_skew=max_quote_skew,
            )
        )
    return found


def detect_auto_cross(
    book: MarketBook,
    usd_equivalents: set[str],
    min_edge_bps: float,
    fee_bps_by_venue: dict[str, float],
    extra_slippage_bps: float,
    notional: float,
    stale_seconds: float = 8.0,
    max_raw_edge_bps: float = 300.0,
    max_quote_skew: float = 1.5,
) -> list[Opportunity]:
    groups: dict[str, list[Quote]] = {}
    now = time.time()
    for quote in book.snapshot():
        if now - quote.ts > stale_seconds:
            continue
        key = comparison_key(quote.canonical, usd_equivalents)
        groups.setdefault(key, []).append(quote)
    found: list[Opportunity] = []
    for key, quotes in groups.items():
        unique_venues: dict[str, Quote] = {}
        for quote in quotes:
            unique_venues.setdefault(quote.venue, quote)
        venue_quotes = list(unique_venues.values())
        for left, right in itertools.combinations(venue_quotes, 2):
            found.extend(
                _cross_from_quotes(
                    left,
                    right,
                    key,
                    min_edge_bps,
                    fee_bps_by_venue,
                    extra_slippage_bps,
                    notional,
                    now,
                    max_raw_edge_bps=max_raw_edge_bps,
                    max_quote_age=stale_seconds,
                    max_quote_skew=max_quote_skew,
                )
            )
    return found


def _cross_from_quotes(
    a: Quote,
    b: Quote,
    pair_id: str,
    min_edge_bps: float,
    fee_bps_by_venue: dict[str, float],
    extra_slippage_bps: float,
    notional: float,
    now: float,
    max_raw_edge_bps: float = 300.0,
    max_quote_age: float | None = None,
    max_quote_skew: float = 1.5,
) -> list[Opportunity]:
    out: list[Opportunity] = []
    for cheap, rich in ((a, b), (b, a)):
        if cheap.ask <= 0 or rich.bid <= 0:
            continue
        raw_bps = (rich.bid / cheap.ask - 1.0) * 10_000
        if raw_bps > max_raw_edge_bps:
            continue
        fees = (
            fee_bps_by_venue.get(cheap.venue, 0.0)
            + fee_bps_by_venue.get(rich.venue, 0.0)
            + extra_slippage_bps
        )
        net = raw_bps - fees
        if net < min_edge_bps:
            continue
        aligned = True
        if max_quote_age is not None:
            aligned = _quotes_aligned(
                [cheap, rich], now, max_age=max_quote_age, max_skew=max_quote_skew
            )
        executable = bool(cheap.executable and rich.executable and aligned)
        kind = OpportunityKind.CROSS_VENUE if executable else OpportunityKind.ALERT
        summary = (
            f"Buy {cheap.native_symbol} on {cheap.venue} @ {cheap.ask:.6g} / "
            f"sell {rich.native_symbol} on {rich.venue} @ {rich.bid:.6g}"
        )
        out.append(
            Opportunity(
                kind=kind,
                edge_bps=raw_bps,
                net_edge_bps=net,
                notional=notional,
                legs=[
                    Leg("buy", cheap.venue, cheap.native_symbol, cheap.ask, cheap.executable),
                    Leg("sell", rich.venue, rich.native_symbol, rich.bid, rich.executable),
                ],
                summary=summary,
                executable=executable,
                ts=now,
                id=_oid("x", pair_id, cheap.venue, rich.venue, cheap.native_symbol, rich.native_symbol),
            )
        )
    return out


def discover_triangles(symbols: list[str]) -> list[tuple[str, str, str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for symbol in symbols:
        try:
            base, quote = split_pair(symbol)
        except ValueError:
            continue
        graph[base].add(quote)
        graph[quote].add(base)
    triangles: list[tuple[str, str, str]] = []
    nodes = sorted(graph)
    for a, b, c in itertools.combinations(nodes, 3):
        if b in graph[a] and c in graph[b] and a in graph[c]:
            triangles.append((a, b, c))
    return triangles


CASH_START = {"USD", "USDC", "USDT"}


def _quotes_aligned(quotes: list[Quote], now: float, *, max_age: float, max_skew: float) -> bool:
    if not quotes:
        return False
    stamps = [float(item.ts or 0.0) for item in quotes]
    if any(now - ts > max_age for ts in stamps):
        return False
    return (max(stamps) - min(stamps)) <= max_skew


def detect_triangles(
    book: MarketBook,
    triangles: list[tuple[str, str, str]],
    min_edge_bps: float,
    taker_bps: float,
    extra_slippage_bps: float,
    notional: float,
    venue: str | None = None,
    min_executable_edge_bps: float | None = None,
    max_raw_edge_bps: float = 300.0,
    max_quote_age: float = 8.0,
    max_quote_skew: float = 1.5,
    maker_bps: float | None = None,
) -> list[Opportunity]:
    found: list[Opportunity] = []
    now = time.time()
    sell_fee = taker_bps if maker_bps is None else float(maker_bps)
    min_exec = min_edge_bps if min_executable_edge_bps is None else min_executable_edge_bps
    for a, b, c in triangles:
        for start, x, y in (
            (a, b, c),
            (a, c, b),
            (b, a, c),
            (b, c, a),
            (c, a, b),
            (c, b, a),
        ):
            if start not in CASH_START:
                continue
            amount = 1.0
            legs_assets = [(start, x), (x, y), (y, start)]
            ok = True
            prices: list[tuple[str, str, float]] = []
            used: list[Quote] = []
            for src, dst in legs_assets:
                converted = book.convert(src, dst, amount, venue=venue)
                quote = _quote_for_leg(book, src, dst, venue=venue)
                if converted is None or quote is None:
                    ok = False
                    break
                prices.append((src, dst, converted / amount if amount else 0.0))
                used.append(quote)
                amount = converted
            if not ok:
                continue
            raw_bps = (amount - 1.0) * 10_000
            if raw_bps > max_raw_edge_bps:
                continue
            fresh = _quotes_aligned(used, now, max_age=max_quote_age, max_skew=max_quote_skew)
            legs = []
            cursor = 1.0
            for src, dst, _ratio in prices:
                quote = _quote_for_leg(book, src, dst, venue=venue)
                assert quote is not None
                try:
                    base, _q = split_pair(quote.canonical)
                except ValueError:
                    base = src
                if base == src:
                    action = "sell"
                    price = quote.bid
                else:
                    action = "buy"
                    price = quote.ask
                legs.append(Leg(action, quote.venue, quote.native_symbol, price, quote.executable))
                nxt = book.convert(src, dst, cursor, venue=venue)
                cursor = nxt if nxt is not None else cursor
            if not legs or legs[0].action != "buy":
                continue
            fee = extra_slippage_bps
            for leg in legs:
                fee += sell_fee if leg.action == "sell" else taker_bps
            net = raw_bps - fee
            if net < min_edge_bps:
                continue
            summary = (
                f"{start} → {x} → {y} → {start} on {used[-1].venue}  "
                f"{amount:.6f} per 1 {start}  net {net:.1f} bps"
            )
            found.append(
                Opportunity(
                    kind=OpportunityKind.TRIANGULAR,
                    edge_bps=raw_bps,
                    net_edge_bps=net,
                    notional=notional,
                    legs=legs,
                    summary=summary,
                    executable=bool(
                        fresh
                        and all(leg.executable for leg in legs)
                        and net >= min_exec - 1e-9
                    ),
                    ts=now,
                    id=_oid("tri", venue or "any", start, x, y),
                )
            )
    return found


QUOTE_BOOKS = ("USD", "USDC", "USDT", "EUR")


def _usd_price(book: MarketBook, price: float, quote: str, venue: str) -> float | None:
    if quote == "USD":
        return price
    fx = book.find_pair(quote, "USD", venue=venue)
    if fx and fx.mid > 0:
        return price * fx.mid
    if quote in {"USDC", "USDT"}:
        return price
    return None


def detect_quote_dislocations(
    book: MarketBook,
    *,
    venue: str,
    min_edge_bps: float,
    fee_map: dict[str, float],
    extra_slippage_bps: float,
    notional: float,
    min_executable_edge_bps: float | None = None,
    max_raw_edge_bps: float = 300.0,
    max_quote_age: float = 8.0,
    max_quote_skew: float = 1.5,
) -> list[Opportunity]:
    """Same-venue base priced in USD vs USDC (or EUR) — Coinbase dislocations live can take."""
    min_exec = min_edge_bps if min_executable_edge_bps is None else min_executable_edge_bps
    now = time.time()
    by_base: dict[str, list[Quote]] = {}
    for quote in book.snapshot():
        if quote.venue != venue or not quote.executable:
            continue
        try:
            base, q = split_pair(quote.canonical)
        except ValueError:
            continue
        if base in {"USD", "USDC", "USDT"} or q not in QUOTE_BOOKS:
            continue
        by_base.setdefault(base, []).append(quote)

    found: list[Opportunity] = []
    for base, rows in by_base.items():
        if len(rows) < 2:
            continue
        for cheap, rich in itertools.permutations(rows, 2):
            try:
                _b, cheap_q = split_pair(cheap.canonical)
                _b2, rich_q = split_pair(rich.canonical)
            except ValueError:
                continue
            if cheap_q == rich_q:
                continue
            cheap_ask = _usd_price(book, cheap.ask, cheap_q, venue)
            rich_bid = _usd_price(book, rich.bid, rich_q, venue)
            if not cheap_ask or not rich_bid or cheap_ask <= 0:
                continue
            raw_bps = (rich_bid / cheap_ask - 1.0) * 10_000
            if raw_bps > max_raw_edge_bps:
                continue
            used = [cheap, rich]
            legs: list[Leg] = []
            if cheap_q == "USD":
                legs = [
                    Leg("buy", venue, cheap.native_symbol, cheap.ask, True),
                    Leg("sell", venue, rich.native_symbol, rich.bid, True),
                ]
            else:
                bridge = book.find_pair(cheap_q, "USD", venue=venue)
                if bridge is None or rich_q != "USD":
                    continue
                used.append(bridge)
                legs = [
                    Leg("buy", venue, bridge.native_symbol, bridge.ask, True),
                    Leg("buy", venue, cheap.native_symbol, cheap.ask, True),
                    Leg("sell", venue, rich.native_symbol, rich.bid, True),
                ]
            if not legs or legs[0].action != "buy":
                continue
            fees = route_fee_bps(fee_map, legs) + extra_slippage_bps
            net = raw_bps - fees
            if net < min_edge_bps:
                continue
            fresh = _quotes_aligned(used, now, max_age=max_quote_age, max_skew=max_quote_skew)
            route = " → ".join(f"{leg.action} {leg.symbol}" for leg in legs)
            found.append(
                Opportunity(
                    kind=OpportunityKind.DISLOCATION,
                    edge_bps=raw_bps,
                    net_edge_bps=net,
                    notional=notional,
                    legs=legs,
                    summary=f"{base} dislocation on {venue}: {route}  net {net:.1f} bps",
                    executable=bool(fresh and net >= min_exec - 1e-9),
                    ts=now,
                    id=_oid("disloc", venue, base, cheap.native_symbol, rich.native_symbol),
                )
            )
    return found


def _quote_for_leg(book: MarketBook, src: str, dst: str, venue: str | None = None) -> Quote | None:
    quote = book.find_pair(src, dst, venue=venue)
    if quote:
        return quote
    return book.find_pair(dst, src, venue=venue)
