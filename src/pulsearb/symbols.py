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

ASSET_ALIASES = {
    "XBT": "BTC",
    "XXBT": "BTC",
    "XETH": "ETH",
    "XLTC": "LTC",
    "XXRP": "XRP",
    "XXLM": "XLM",
    "ZUSD": "USD",
    "ZEUR": "EUR",
    "ZGBP": "GBP",
    "ZJPY": "JPY",
}

USD_EQUIVALENTS_DEFAULT = {"USD", "USDT", "USDC", "FDUSD", "BUSD", "TUSD"}
FIAT_ASSETS = {
    "USD",
    "EUR",
    "GBP",
    "JPY",
    "AUD",
    "CAD",
    "CHF",
    "NZD",
    "SEK",
    "NOK",
    "MXN",
    "CNH",
    "DKK",
    "SGD",
    "HKD",
    "PLN",
    "ZAR",
}
FX_ASSETS = FIAT_ASSETS | {"USDC", "USDT", "DAI"}


def normalize_asset(code: str) -> str:
    text = code.upper().strip()
    return ASSET_ALIASES.get(text, text)


def split_pair(symbol: str) -> tuple[str, str]:
    text = symbol.strip().upper().replace(" ", "")
    if "/" in text:
        base, quote = text.split("/", 1)
        return normalize_asset(base), normalize_asset(quote)
    if "-" in text:
        base, quote = text.split("-", 1)
        return normalize_asset(base), normalize_asset(quote)
    compact = text.replace("-", "").replace("/", "")
    compact = (
        compact.replace("XXBT", "BTC")
        .replace("XBT", "BTC")
        .replace("XETH", "ETH")
        .replace("XLTC", "LTC")
        .replace("XXRP", "XRP")
        .replace("XXLM", "XLM")
        .replace("ZUSD", "USD")
        .replace("ZEUR", "EUR")
        .replace("ZGBP", "GBP")
    )
    for quote in sorted(QUOTE_ASSETS, key=len, reverse=True):
        if compact.endswith(quote) and len(compact) > len(quote):
            return normalize_asset(compact[: -len(quote)]), quote
    raise ValueError(f"Cannot split symbol: {symbol}")


def split_binance_symbol(symbol: str) -> tuple[str, str]:
    return split_pair(symbol)


def canonical_from_pair(symbol: str) -> str:
    base, quote = split_pair(symbol)
    return f"{base}-{quote}"


def pair_asset_class(symbol: str) -> str:
    """fx when both sides are fiat or cash stables; metals/energy stay named."""
    try:
        base, quote = split_pair(symbol)
    except ValueError:
        return "crypto"
    both = {base, quote}
    if both <= FX_ASSETS:
        return "fx"
    if both & {"XAU", "XAG"}:
        return "metal"
    if "WTI" in both:
        return "energy"
    return "crypto"


def canonical_from_binance(symbol: str) -> str:
    return canonical_from_pair(symbol)


def comparison_key(canonical: str, usd_equivalents: set[str] | None = None) -> str:
    usd = {item.upper() for item in (usd_equivalents or USD_EQUIVALENTS_DEFAULT)}
    base, quote = split_pair(canonical)
    if quote in usd:
        quote = "USD"
    if base in usd:
        base = "USD"
    return f"{base}-{quote}"


def to_native_symbol(venue: str, canonical: str) -> str:
    base, quote = split_pair(canonical)
    venue = venue.lower()
    if venue == "coinbase":
        return f"{base}-{quote}"
    if venue == "kraken":
        kbase = "XBT" if base == "BTC" else base
        kquote = "XBT" if quote == "BTC" else quote
        return f"{kbase}{kquote}"
    if venue in {"gemini", "bitstamp"}:
        gbase = "btc" if base == "BTC" else base.lower()
        gquote = "btc" if quote == "BTC" else quote.lower()
        return f"{gbase}{gquote}"
    if venue == "binance":
        q = "USDT" if quote == "USD" else quote
        return f"{base}{q}"
    if venue == "oanda":
        return f"{base}_{quote}"
    if venue == "robinhood":
        return f"{base}-{quote}"
    return canonical


def usd_canonical(base: str, quote: str, usd_equivalents: set[str]) -> str | None:
    base, quote = normalize_asset(base), normalize_asset(quote)
    if quote in usd_equivalents:
        return f"{base}-USD"
    if base in usd_equivalents:
        return f"USD-{quote}"
    return None
