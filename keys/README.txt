Drop your exchange API file here. You only need the venue you will trade live on.

Coinbase (Advanced Trade Secret API key):
    coinbase.json
Create at: https://portal.cdp.coinbase.com/projects/api-keys
View + Trade only — no Transfer. Signature: ECDSA.
In the popup click Download API key, then rename the file coinbase.json.

Kraken (no download — you make this file):
    kraken.json
Copy kraken.json.example and rename it to kraken.json.
Create the key at: https://www.kraken.com/u/security/api
Paste:
    "key"    = Kraken API Key
    "secret" = Kraken Private Key
Permissions: Query Funds + Create & Modify Orders. Do NOT enable Withdraw.

You do not need both. Pick Coinbase or Kraken on the dashboard.
See LIVE.txt. Run CHECK-LIVE.bat (does not send orders) before going live.

This folder is for keys on YOUR computer. Do not zip or email these files.
