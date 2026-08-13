# Lockwell security model

## Goals versus typical identity apps

1. **Vault secrecy** — server operators cannot read vault contents.
2. **Minimized identity storage** — monitored values are hashed, not stored in cleartext.
3. **Accountability** — sensitive actions emit audit events the user can review.
4. **Session hygiene** — bearer tokens are random, per-session, and revocable on logout.

## Crypto choices (MVP)

| Surface | Mechanism |
| --- | --- |
| Account password | Werkzeug password hash (pbkdf2) |
| Vault key derivation | PBKDF2-HMAC-SHA256, 210k iterations, per-user salt |
| Vault payload | AES-GCM (browser Web Crypto) |
| Monitored values | HMAC-SHA256 with server pepper + display mask |

## Explicit non-goals for this MVP

- Live dark-web crawling
- Credit bureau data access
- Identity theft insurance underwriting
- Full endpoint antivirus / VPN agents
