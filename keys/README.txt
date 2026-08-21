Drop your exchange API file here. You only need the venue you will trade live on.

Coinbase (Advanced Trade Secret API key):
    coinbase.json
Create at: https://portal.cdp.coinbase.com/projects/api-keys
View + Trade only — no Transfer. Signature: ECDSA.
In the popup click Download API key, then rename the file coinbase.json.

Kraken:
    kraken.json
Create at: https://www.kraken.com/u/security/api
JSON shape: {"key":"...","secret":"..."}
Permissions: Query Funds + Create & Modify Orders. Do NOT enable Withdraw.

You do not need both. Pick Coinbase or Kraken on the dashboard.
See LIVE.txt. Run CHECK-LIVE.bat (does not send orders) before going live.

This folder is for keys on YOUR computer. Do not zip or email these files.
