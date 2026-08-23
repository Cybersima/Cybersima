Drop your exchange API file here. You only need the venue you will trade live on.

Coinbase (Advanced Trade Secret API key):
    coinbase.json
Create at: https://portal.cdp.coinbase.com/projects/api-keys
View + Trade only — no Transfer. Signature: ECDSA.
In the popup click Download API key, then rename the file coinbase.json.

Kraken (no download — you make this file):
    kraken.json
Copy kraken.json.example and rename it to kraken.json.

Gemini:
    gemini.json
Copy gemini.json.example. Trading permission only.

OANDA:
    oanda.json
Copy oanda.json.example. Start with "environment": "practice".

Robinhood:
    robinhood.json
Copy robinhood.json.example. No sandbox — a working key is real money.
See LIVE.txt for the Ed25519 keypair command.

Bitstamp is not used (Robinhood merger; retail close-only 1 Feb 2027).
Yahoo is not used (delayed, not tradable).

You do not need every venue. Pick one on the dashboard.
See LIVE.txt. Run CHECK-LIVE.bat (does not send orders) before going live.

This folder is for keys on YOUR computer. Do not zip or email these files.
