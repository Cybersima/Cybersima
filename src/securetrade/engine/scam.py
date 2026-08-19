from __future__ import annotations

from dataclasses import dataclass, field

from securetrade.models import Opportunity


SUSPICIOUS_TOKENS = {"SCAMCOIN", "HONYPOT", "RUGPULL", "FREEETH"}
MALICIOUS_ADDRESSES = {"0xdeadbeefmalicious", "bc1qevil"}
PHISHING_DOMAINS = {"coinbase-login.xyz", "kraken-support.app", "secure-binance.io"}
COUNTERFEIT_TICKERS = {"BTC.e", "USD₮", "ETH2X"}


@dataclass
class ScamReport:
    clean: bool
    critical: bool
    findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"clean": self.clean, "critical": self.critical, "findings": self.findings}


class ScamDefense:
    """Cybercriminal / scam defense — spectacular 'opportunities' can still be rejected."""

    def inspect(self, opportunity: Opportunity, destination: str = "") -> ScamReport:
        findings: list[str] = []
        critical = False
        blob = " ".join(
            [
                opportunity.summary,
                opportunity.pair,
                destination,
                *[leg.symbol for leg in opportunity.legs],
            ]
        ).upper()
        for token in SUSPICIOUS_TOKENS:
            if token in blob.replace("-", "").replace("/", ""):
                findings.append(f"Suspicious token/contract: {token}")
                critical = True
        for ticker in COUNTERFEIT_TICKERS:
            if ticker.upper() in blob:
                findings.append(f"Counterfeit-token indicator: {ticker}")
                critical = True
        if destination.lower() in MALICIOUS_ADDRESSES:
            findings.append("Malicious-address intelligence match")
            critical = True
        lower = (opportunity.summary + " " + destination).lower()
        for domain in PHISHING_DOMAINS:
            if domain in lower:
                findings.append(f"Phishing-domain warning: {domain}")
                critical = True
        if "HONEYPOT" in blob or "can't sell" in lower or "cannot sell" in lower:
            findings.append("Honeypot / rug-pull indicator")
            critical = True
        if opportunity.net_edge_bps > 800 and opportunity.liquidity_usd < opportunity.notional:
            findings.append("Abnormal wallet/liquidity behavior on a spectacular spread")
        return ScamReport(clean=not findings, critical=critical, findings=findings)
