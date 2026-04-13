#!/bin/bash
# publish.sh — Commit, push to GitHub, and deploy Flamescribe to Flame.
#
# Edit files in ~/Flamescribe, then run this script to ship.
# The Flame install location (/opt/Autodesk/...) is a deploy target only — don't edit there directly.

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLAME_INSTALL="/opt/Autodesk/shared/python/transcribe_audio"

cd "$REPO_DIR"

echo ""
echo "════════════════════════════════════════════════"
echo "  FLAMESCRIBE PUBLISH"
echo "════════════════════════════════════════════════"
echo ""

# ── 1. Version ───────────────────────────────────────
printf "Enter version number (e.g. 1.0.1): "
read -r VERSION
[[ -z "$VERSION" ]] && echo "Error: version cannot be empty." && exit 1
VERSION="${VERSION#v}"

echo "→ Updating version in transcribe_audio.py..."
sed -i '' "s/^SCRIPT_VERSION *= *'.*'/SCRIPT_VERSION = 'v$VERSION'/" "$REPO_DIR/transcribe_audio.py"
echo "✓ Version set to v$VERSION."
echo ""

# ── 2. Commit & push to GitHub ────────────────────────
echo "→ Committing to GitHub..."
git add transcribe_audio.py worker.py
git diff --cached --quiet && echo "  (nothing staged — skipping commit)" || \
  git commit -m "v$VERSION"
git push -u origin main
echo "✓ Pushed to GitHub."
echo ""

# ── 3. Deploy to Flame install location ──────────────
echo "→ Deploying to Flame..."
cp "$REPO_DIR/transcribe_audio.py" "$FLAME_INSTALL/transcribe_audio.py"
cp "$REPO_DIR/worker.py"           "$FLAME_INSTALL/worker.py"
echo "✓ Deployed to $FLAME_INSTALL"
echo ""

echo "════════════════════════════════════════════════"
echo "  Done! Flamescribe v$VERSION shipped."
echo "  Restart Flame (or reload Python hooks) to pick up changes."
echo "════════════════════════════════════════════════"
echo ""
