from __future__ import annotations

QUOTE_ASSETS = (
    "USDT",
    "USDC",
    "FDUSD",
    "BUSD",
    "TUSD",
    "BTC",
    "ETH",
    "BNB",
    "EUR",
    "TRY",
    "BRL",
    "DAI",
    "USD",
    "JPY",
    "GBP",
    "AUD",
    "CAD",
    "CHF",
    "NZD",
    "CNH",
    "SEK",
    "NOK",
    "MXN",
    "ZAR",
    "XAU",
    "XAG",
    "WTI",
)


def split_binance_symbol(symbol: str) -> tuple[str, str]:
    text = symbol.upper().replace("-", "").replace("/", "")
    for quote in sorted(QUOTE_ASSETS, key=len, reverse=True):
        if text.endswith(quote) and len(text) > len(quote):
            return text[: -len(quote)], quote
    raise ValueError(f"Cannot split symbol: {symbol}")


def canonical_from_binance(symbol: str) -> str:
    base, quote = split_binance_symbol(symbol)
    return f"{base}-{quote}"


def usd_canonical(base: str, quote: str, usd_equivalents: set[str]) -> str | None:
    base, quote = base.upper(), quote.upper()
    if quote in usd_equivalents:
        return f"{base}-USD"
    if base in usd_equivalents:
        return f"USD-{quote}"
    return None
