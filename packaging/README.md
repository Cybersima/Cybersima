# Packaging notes — CyberSym SecureTrade 2

The Python project is the product. Installers wrap the same entry point: `securetrade`.

## Windows (.exe / .msi)

1. `pip install pyinstaller`
2. `pyinstaller packaging/securetrade.spec`
3. Sign `dist/SecureTrade Desktop.exe` with your Authenticode certificate.
4. Wrap with WiX / Inno Setup as `CyberSym-SecureTrade-2.msi`.

The spec produces a GUI command center. The 24/7 engine should still be deployed with Docker on a VPS, not inside the laptop .exe.

## macOS (.dmg / .pkg)

1. `pyinstaller packaging/securetrade.spec`
2. Sign and notarize the `.app`
3. Build a `.dmg` or productbuild `.pkg`

## Auto-update

`/api/updates` is the signed-update hook. Ship a manifest URL and require a signature before applying a payload. This build reports the current version and `require_signature: true`.

## First-run

`securetrade wizard` and the `/setup` view. `~/.cybersym/securetrade/first_run_complete` marks completion.
