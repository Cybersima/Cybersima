import csv
import io

from pulsearb.engine.report import REPORT_HEADERS, ProfitLedger, build_report_row, ordered_values
from pulsearb.models import Fill, Leg, Opportunity, OpportunityKind


def _opp(executable: bool = True) -> Opportunity:
    return Opportunity(
        kind=OpportunityKind.CROSS_VENUE if executable else OpportunityKind.ALERT,
        edge_bps=120,
        net_edge_bps=44,
        notional=250,
        legs=[
            Leg("buy", "coinbase", "BTC-USD", 97010, True),
            Leg("sell", "kraken", "XBTUSD", 98100, True),
        ],
        summary="buy coinbase / sell kraken",
        executable=executable,
        ts=1_700_000_000,
        id="gap-1",
    )


def test_headers_match_profit_sheet() -> None:
    assert REPORT_HEADERS == [
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


def test_filled_paper_row_extracts_venues_and_pnl() -> None:
    opp = _opp()
    fills = [
        Fill(
            venue="coinbase",
            symbol="BTC-USD",
            side="buy",
            qty=0.002,
            price=97010,
            notional=250,
            ts=1_700_000_001,
            paper=True,
            opportunity_id="gap-1",
            status="filled",
        )
    ]
    row = build_report_row(
        opp,
        fills,
        paper=True,
        killed=False,
        fee_map={"coinbase": 50, "kraken": 26},
        slippage_bps=2,
        closed_at=1_700_000_001.5,
    )
    assert row["ID"] == "gap-1"
    assert row["Strategy"] == "Cross-venue"
    assert row["Market"] == "BTC-USD"
    assert row["Buy Venue"] == "coinbase"
    assert row["Sell Venue"] == "kraken"
    assert row["Raw Edge"] == 120
    assert row["Net Edge (bps)"] == 44
    assert row["Fee (bps)"] == 66
    assert row["Slippage (bps)"] == 2
    assert row["Expected P&L"] == 1.1
    from pulsearb.engine.money import paper_tap_pnl

    assert row["Realized P&L"] == round(paper_tap_pnl(fills, 250), 6)
    assert row["Fill Ratio"] == 1.0
    assert row["Paper Notional"] == 250
    assert row["Guardian Status"] == "pass"
    assert row["Close Reason"] == "paper_fill"
    values = ordered_values(row)
    assert len(values) == len(REPORT_HEADERS)
    assert values[7] == "pass"
    assert values[8] == "ok"


def test_csv_round_trip(tmp_path) -> None:
    ledger = ProfitLedger(csv_path=tmp_path / "report.csv")
    opp = _opp()
    fills = [
        Fill(
            venue="coinbase",
            symbol="BTC-USD",
            side="buy",
            qty=0.002,
            price=97010,
            notional=250,
            ts=1_700_000_001,
            paper=True,
            opportunity_id="gap-1",
            status="filled",
        )
    ]
    row = build_report_row(
        opp,
        fills,
        paper=True,
        killed=False,
        fee_map={"coinbase": 50, "kraken": 26},
        slippage_bps=2,
        closed_at=1_700_000_001.5,
    )
    ledger.record(row)
    raw = ledger.to_csv_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[0] == REPORT_HEADERS
    assert parsed[1][0] == "gap-1"
    assert parsed[1][6] == "paper"
    assert ledger.export_csv_bytes().startswith(b"\xef\xbb\xbf")
    assert b"gap-1" in ledger.export_csv_bytes()


def test_export_prefers_full_disk_file_over_memory_window(tmp_path) -> None:
    path = tmp_path / "report.csv"
    ledger = ProfitLedger(csv_path=path, max_rows=2)
    for index in range(5):
        row = build_report_row(
            _opp(),
            [
                Fill(
                    venue="coinbase",
                    symbol="BTC-USD",
                    side="buy",
                    qty=0.001,
                    price=97010,
                    notional=250,
                    ts=1_700_000_001,
                    paper=True,
                    opportunity_id=f"gap-{index}",
                    status="filled",
                )
            ],
            paper=True,
            killed=False,
            fee_map={"coinbase": 50, "yahoo": 0},
            slippage_bps=2,
            closed_at=1_700_000_000.4,
        )
        row["ID"] = f"gap-{index}"
        ledger.record(row)
    assert len(ledger.rows) == 2
    assert ledger.total_rows == 5
    exported = ledger.export_csv_bytes().decode("utf-8-sig")
    assert "gap-0" in exported
    assert "gap-4" in exported
    memory_only = ledger.to_csv_bytes().decode("utf-8-sig")
    assert "gap-0" not in memory_only
    assert "gap-3" in memory_only


def test_export_skips_alert_rows(tmp_path) -> None:
    path = tmp_path / "report.csv"
    ledger = ProfitLedger(csv_path=path)
    alert = build_report_row(
        _opp(executable=False),
        [],
        paper=True,
        killed=False,
        fee_map={"coinbase": 50, "yahoo": 0},
        slippage_bps=2,
        closed_at=1_700_000_000.4,
    )
    taken = build_report_row(
        _opp(),
        [
            Fill(
                venue="coinbase",
                symbol="BTC-USD",
                side="buy",
                qty=0.001,
                price=97010,
                notional=250,
                ts=1_700_000_001,
                paper=True,
                opportunity_id="gap-1",
                status="filled",
            )
        ],
        paper=True,
        killed=False,
        fee_map={"coinbase": 50, "kraken": 26},
        slippage_bps=2,
        closed_at=1_700_000_001.5,
    )
    ledger.record(alert)
    ledger.record(taken)
    assert ledger.taken_rows == 1
    assert ledger.as_dicts()[0]["ID"] == "gap-1"
    exported = ledger.export_csv_bytes().decode("utf-8-sig")
    assert "alert" not in exported.splitlines()[1] if exported.strip() else True
    assert "paper" in exported
    assert "gap-1" in exported
    # Old files that already mixed alerts still filter on download.
    mixed = tmp_path / "mixed.csv"
    mixed.write_text(
        "ID,Detected Time,Strategy,Market,Route,Financial,Execution,Guardian,Guardian,Expected P&L,Realized P&L,Edge Lifetime,Close Reason,Buy Venue,Sell Venue,Raw Edge,Net Edge (bps),Fee (bps),Slippage (bps),Fill Ratio,Paper Notional\n"
        "scan-1,t,Alert,BTC-USD,watch,paper USD,alert,watch,data,0,0,0,alert_only,coinbase,kraken,1,1,0,0,0,0\n"
        "trade-1,t,Triangular,ETH-USD,buy,live USD,live,pass,ok,0.1,0.1,1,live_fill,coinbase,coinbase,12,8,50,2,1,10\n",
        encoding="utf-8-sig",
    )
    from pulsearb.engine.report import filter_taken_csv_bytes

    filtered = filter_taken_csv_bytes(mixed.read_bytes()).decode("utf-8-sig")
    assert "scan-1" not in filtered
    assert "trade-1" in filtered
    assert "alert" not in filtered.split("\n")[1]


def test_cooldown_blocks_are_not_trades(tmp_path) -> None:
    ledger = ProfitLedger(csv_path=tmp_path / "report.csv")
    row = build_report_row(
        _opp(),
        [
            Fill(
                venue="paper",
                symbol="-",
                side="blocked",
                qty=0,
                price=0,
                notional=0,
                ts=1_700_000_001,
                paper=True,
                opportunity_id="gap-1",
                status="blocked",
                note="cooldown",
            )
        ],
        paper=True,
        killed=False,
        fee_map={"coinbase": 50, "kraken": 26},
        slippage_bps=2,
        closed_at=1_700_000_001.5,
    )
    assert row["Close Reason"] == "cooldown"
    ledger.record(row)
    assert ledger.taken_rows == 0
    assert ledger.as_dicts() == []
    mixed = tmp_path / "mixed.csv"
    mixed.write_text(
        "ID,Detected Time,Strategy,Market,Route,Financial,Execution,Guardian,Guardian,Expected P&L,Realized P&L,Edge Lifetime,Close Reason,Buy Venue,Sell Venue,Raw Edge,Net Edge (bps),Fee (bps),Slippage (bps),Fill Ratio,Paper Notional\n"
        "cool-1,t,Triangular,BTC-USD,sell XBTUSD,paper USD,blocked,block,cooldown,0.03,0,0.01,cooldown,kraken,kraken,110,30,78,2,0,1\n"
        "fill-1,t,Triangular,ETH-USD,buy ETH-USD,paper USD,paper,pass,ok,0.02,0.01,1,paper_fill,coinbase,coinbase,40,28,50,2,1,1\n",
        encoding="utf-8-sig",
    )
    from pulsearb.engine.report import filter_taken_csv_bytes

    filtered = filter_taken_csv_bytes(mixed.read_bytes()).decode("utf-8-sig")
    assert "cool-1" not in filtered
    assert "fill-1" in filtered


def test_clear_rewrites_csv_to_headers_only(tmp_path) -> None:
    path = tmp_path / "report.csv"
    ledger = ProfitLedger(csv_path=path)
    taken = build_report_row(
        _opp(),
        [
            Fill(
                venue="coinbase",
                symbol="BTC-USD",
                side="buy",
                qty=0.001,
                price=97010,
                notional=250,
                ts=1_700_000_001,
                paper=True,
                opportunity_id="gap-1",
                status="filled",
            )
        ],
        paper=True,
        killed=False,
        fee_map={"coinbase": 50, "kraken": 26},
        slippage_bps=2,
        closed_at=1_700_000_001.5,
    )
    ledger.record(taken)
    assert ledger.taken_rows == 1
    ledger.clear()
    assert ledger.taken_rows == 0
    assert ledger.as_dicts() == []
    text = path.read_text(encoding="utf-8-sig")
    assert "gap-1" not in text
    assert text.strip().startswith("ID,")
    assert "paper_fill" not in text
