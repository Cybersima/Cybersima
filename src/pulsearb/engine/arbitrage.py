from __future__ import annotations

import hashlib
import itertools
import time
from collections import defaultdict

from pulsearb.engine.book import MarketBook
from pulsearb.models import Leg, Opportunity, OpportunityKind, Quote
from pulsearb.symbols import split_binance_symbol


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
) -> list[Opportunity]:
    out: list[Opportunity] = []
    for cheap, rich in ((a, b), (b, a)):
        if cheap.ask <= 0 or rich.bid <= 0:
            continue
        raw_bps = (rich.bid / cheap.ask - 1.0) * 10_000
        fees = (
            fee_bps_by_venue.get(cheap.venue, 0.0)
            + fee_bps_by_venue.get(rich.venue, 0.0)
            + extra_slippage_bps
        )
        net = raw_bps - fees
        if net < min_edge_bps:
            continue
        executable = bool(cheap.executable and rich.executable)
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
                id=_oid(pair_id, cheap.venue, rich.venue, f"{net:.2f}"),
            )
        )
    return out


def discover_triangles(symbols: list[str]) -> list[tuple[str, str, str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for symbol in symbols:
        try:
            base, quote = split_binance_symbol(symbol)
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


def detect_triangles(
    book: MarketBook,
    triangles: list[tuple[str, str, str]],
    min_edge_bps: float,
    taker_bps: float,
    extra_slippage_bps: float,
    notional: float,
) -> list[Opportunity]:
    found: list[Opportunity] = []
    now = time.time()
    fee = 3 * taker_bps + extra_slippage_bps
    for a, b, c in triangles:
        for path in ((a, b, c), (a, c, b)):
            start, x, y = path
            amount = 1.0
            legs_assets = [(start, x), (x, y), (y, start)]
            ok = True
            prices: list[tuple[str, str, float]] = []
            for src, dst in legs_assets:
                converted = book.convert(src, dst, amount)
                quote = _quote_for_leg(book, src, dst)
                if converted is None or quote is None:
                    ok = False
                    break
                prices.append((src, dst, converted / amount if amount else 0.0))
                amount = converted
            if not ok:
                continue
            raw_bps = (amount - 1.0) * 10_000
            net = raw_bps - fee
            if net < min_edge_bps:
                continue
            executable = True
            summary = (
                f"{start} → {x} → {y} → {start}  "
                f"{amount:.6f} per 1 {start}  net {net:.1f} bps"
            )
            legs = []
            cursor = 1.0
            for src, dst, _ratio in prices:
                quote = _quote_for_leg(book, src, dst)
                assert quote is not None
                if quote.native_symbol.startswith(src):
                    action = "sell"
                    price = quote.bid
                else:
                    action = "buy"
                    price = quote.ask
                legs.append(Leg(action, quote.venue, quote.native_symbol, price, quote.executable))
                nxt = book.convert(src, dst, cursor)
                cursor = nxt if nxt is not None else cursor
            found.append(
                Opportunity(
                    kind=OpportunityKind.TRIANGULAR,
                    edge_bps=raw_bps,
                    net_edge_bps=net,
                    notional=notional,
                    legs=legs,
                    summary=summary,
                    executable=executable,
                    ts=now,
                    id=_oid("tri", start, x, y, f"{net:.2f}"),
                )
            )
    return found


def _quote_for_leg(book: MarketBook, src: str, dst: str) -> Quote | None:
    quote = book.binance_pair(src, dst)
    if quote:
        return quote
    return book.binance_pair(dst, src)
