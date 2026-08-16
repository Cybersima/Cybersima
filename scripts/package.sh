#!/usr/bin/env bash
# Build a portable archive you can copy to another machine.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-/opt/cursor/artifacts/lockwell-portable}"
STAGE_ROOT="${TMPDIR:-/tmp}/lockwell-package-$$"
STAGE="$STAGE_ROOT/lockwell"

rm -rf "$STAGE_ROOT" "$OUT_DIR"
mkdir -p "$STAGE" "$OUT_DIR"

echo "==> Building frontend for portable package"
(
  cd "$ROOT/frontend"
  if [[ ! -d node_modules ]]; then
    npm install
  fi
  npm run build
)

echo "==> Staging files"
copy_tree() {
  local src="$1"
  local dest="$2"
  mkdir -p "$dest"
  tar -C "$src" \
    --exclude=node_modules \
    --exclude=.venv \
    --exclude=__pycache__ \
    --exclude='*.db' \
    --exclude=.git \
    --exclude=dist \
    -cf - . | tar -C "$dest" --no-same-owner --no-same-permissions -xf -
}

copy_tree "$ROOT/backend" "$STAGE/backend"
copy_tree "$ROOT/frontend" "$STAGE/frontend"
copy_tree "$ROOT/scripts" "$STAGE/scripts"
copy_tree "$ROOT/docs" "$STAGE/docs"
cp "$ROOT/README.md" "$ROOT/Dockerfile" "$ROOT/docker-compose.yml" "$STAGE/"
[[ -f "$ROOT/.dockerignore" ]] && cp "$ROOT/.dockerignore" "$STAGE/"

# Keep the built UI inside the package.
rm -rf "$STAGE/frontend/dist"
cp -a "$ROOT/frontend/dist" "$STAGE/frontend/dist"
chmod +x "$STAGE/scripts/"*.sh || true

cat > "$STAGE/RUN.txt" <<'EOF'
Lockwell portable package
=========================

Easiest:
  macOS/Linux:  ./scripts/start.sh
  Windows:      .\scripts\start.ps1
  Docker:       docker compose up --build

Then open http://127.0.0.1:5000

If the UI is already built (frontend/dist present) and you only want Python:

  cd backend
  python3 -m venv .venv
  source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  python app.py

More detail: docs/TESTING_LOCALLY.md
EOF

ARCHIVE="$OUT_DIR/lockwell-portable.tar.gz"
tar -C "$STAGE_ROOT" -czf "$ARCHIVE" lockwell
(
  cd "$STAGE_ROOT"
  zip -qr "$OUT_DIR/lockwell-portable.zip" lockwell
)

echo "==> Created:"
echo "    $ARCHIVE"
echo "    $OUT_DIR/lockwell-portable.zip"
ls -lh "$ARCHIVE" "$OUT_DIR/lockwell-portable.zip"
rm -rf "$STAGE_ROOT"