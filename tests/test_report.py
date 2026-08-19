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
    assert row["Fee (bps)"] == 76
    assert row["Slippage (bps)"] == 2
    assert row["Expected P&L"] == 1.1
    assert row["Realized P&L"] == 1.1
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
    row = build_report_row(
        _opp(executable=False),
        [],
        paper=True,
        killed=False,
        fee_map={"coinbase": 50, "yahoo": 0},
        slippage_bps=2,
        closed_at=1_700_000_000.4,
    )
    ledger.record(row)
    raw = ledger.to_csv_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    parsed = list(csv.reader(io.StringIO(text)))
    assert parsed[0] == REPORT_HEADERS
    assert parsed[1][0] == "gap-1"
    assert parsed[1][2] == "Alert"
    assert parsed[1][10] == "0.0" or float(parsed[1][10]) == 0.0
