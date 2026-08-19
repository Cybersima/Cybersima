# CyberSym SecureTrade — version guide

This tree is **SecureTrade 2.0.0**, the packaged product. Earlier scanner work lives on `cursor/pulsearb-multimarket-scanner-c11f` (v0.1.0).

| Version | Role | What it did |
|---|---|---|
| **v0.1.0** | First branded scanner | Coinbase/Kraken/Gemini/Bitstamp/Yahoo feeds, cross-venue + triangle detection, instant paper fills, iPad dashboard, kill switch. Internal package name `pulsearb`. |
| **v0.3.7** (design lineage) | Last known-good *Paper Lab* flow | Handoff → Paper Lab → CAPTURED / REVERSED / MISSED / EXPIRED. Regular profitable paper outcomes. |
| **v0.3.8 / v0.3.8a** (design lineage) | Experimental regression | Final Commit was wired as a lifecycle replacement; completed paper outcomes effectively stopped. Useful telemetry: commit edge, edge retention, snapshot age, latency skew. |
| **v0.3.8b** (design lineage) | Final Commit pipeline recovery | Restored the v0.3.7 Paper Lab path. Final Commit became an advisory gate: ATOMIC_READY → COMMIT / RESEARCH_COMMIT / CANCEL → Paper Lab. CANCEL never enters Paper Lab. |
| **v2.0.0 SecureTrade 2** | This product | Installable command center + Docker engine, Guardian™, Trust Score, Learn/Assist/Auto, Academy, decision journal, capital protection, scam defense, takeover detection, and the recovered v0.3.8b pipeline implemented on the v0.1 scanner foundation. |

## Pipeline in v2.0.0

```
v0.3.7 working flow                 v0.3.8 observability
Microstructure / scanner            Scheduler delay
   ↓                                Snapshot / book age
Handoff ATOMIC_READY                Commit edge
   ↓                                Edge retention
Recovery Final Commit               Freshness
   ↓                                Latency skew
COMMIT | RESEARCH_COMMIT | CANCEL
   ↓
Original Paper Lab
   ↓
CAPTURED | REVERSED | MISSED | EXPIRED
```

Watch these counters first: `handoff_atomic_ready`, `recovery_commit_pass` / `recovery_research_pass`, and `paper_opened` at `/api/recovery-commit`.

Dashboard outcome colors:

- CAPTURED → green (`--up`)
- LOSS → red (`--down`)
- MISSED → blue (`--miss`)
- REVERSED → orange (`--rev`)
