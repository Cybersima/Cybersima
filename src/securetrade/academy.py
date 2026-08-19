from __future__ import annotations

LESSONS: list[dict[str, str]] = [
    {
        "id": "arbitrage",
        "title": "Arbitrage",
        "body": "Arbitrage is buying an asset where it is cheap and selling where it is rich, at the same moment. SecureTrade looks for those gaps after fees and slippage — not the raw quoted spread.",
    },
    {
        "id": "spread",
        "title": "Spread",
        "body": "The spread is the gap between the best bid and best ask. A wide spread means you pay more to cross the market, so a 'profit' on paper can disappear in the first fill.",
    },
    {
        "id": "slippage",
        "title": "Slippage",
        "body": "Slippage is the difference between the price you hoped for and the price you actually got. Thin books cause more slippage. Pre-trade simulation exists to catch this before money moves.",
    },
    {
        "id": "market-orders",
        "title": "Market orders",
        "body": "A market order says 'fill me now at whatever price is available.' Fast, but dangerous in thin or moving markets. Guardian prefers limit and IOC/FOK behavior when the book is fragile.",
    },
    {
        "id": "limit-orders",
        "title": "Limit orders",
        "body": "A limit order caps the worst price you will accept. It can miss the window, which is often better than capturing a toxic fill.",
    },
    {
        "id": "api-security",
        "title": "API security",
        "body": "Exchange API keys should be withdrawal-disabled, IP-restricted, and stored encrypted. SecureTrade will not enable live trading until those safety checks pass.",
    },
    {
        "id": "phishing",
        "title": "Phishing",
        "body": "Fake exchange domains and 'support' messages exist to steal keys and seed phrases. Guardian warns on known phishing domains and will not send funds to high-risk destinations.",
    },
    {
        "id": "wallet-security",
        "title": "Wallet security",
        "body": "Never paste a seed phrase into this product. Hardware-backed storage and passkeys protect credentials. If a new device or unusual IP appears, Auto mode suspends until you reauthenticate.",
    },
    {
        "id": "why-rejected",
        "title": "Why a trade was rejected",
        "body": "Guardian can block a profitable-looking trade. Typical reasons: unusual liquidity, abnormal price divergence, failed trust requirements, possible manipulation, or elevated counterparty risk. Potential profit does not override your security policy.",
    },
    {
        "id": "learn-assist-auto",
        "title": "Learn, Assist, Auto",
        "body": "Learn Mode uses simulated money and explanations. Assist Mode finds opportunities but waits for your approval. Auto Mode executes only inside the limits you set. One product, three levels of control.",
    },
    {
        "id": "starter-ladder",
        "title": "Starting with $10 or $100",
        "body": "Everyone can start in Learn with simulated $10 or $100. A 0.31% capture on $100 is about 31 cents — SecureTrade shows dollars, not just percents. Paper $100 is the practice floor. Micro live $100 is optional after paper, with Auto off and a $5 daily loss cap. Live $10 is not offered because exchange fees would dominate such a small ticket. This is access to the opportunity to learn safely, not a promise of profit.",
    },
    {
        "id": "trust-score",
        "title": "CyberSym Trust Score",
        "body": "Every idea gets a 0–100 score: venue reliability, asset reputation, liquidity, book quality, volatility, data consistency, abnormal behavior, security indicators, and execution risk. 92/100 — Low Risk is more useful than a bare BUY.",
    },
]


def lesson(lesson_id: str) -> dict[str, str] | None:
    for item in LESSONS:
        if item["id"] == lesson_id:
            return item
    return None


def explain_rejection(reasons: list[str]) -> dict[str, str]:
    return {
        "id": "why-rejected",
        "title": "Why this trade was rejected",
        "body": "Guardian blocked execution. " + " ".join(f"• {reason}." for reason in reasons),
        "lesson": "Potential profit does not satisfy your security policy. No customer funds were exposed.",
    }
