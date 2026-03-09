#!/bin/bash
# Deploy only the HTML pages to the server. Does not touch fonts or bundle.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SITE_DIR="$SCRIPT_DIR/dist/site"

# Build site first
python3 "$SCRIPT_DIR/build_site.py"

# Read server from .scaffold-host or fall back to env
if [ -f "$SCRIPT_DIR/.scaffold-host" ]; then
    HOST=$(cat "$SCRIPT_DIR/.scaffold-host")
else
    HOST="${SCAFFOLD_HOST:-}"
fi

if [ -z "$HOST" ]; then
    echo "Set SCAFFOLD_HOST or create .scaffold-host with deploy@host"
    exit 1
fi

DEST="$HOST:~/sites/fonts.noisefactor.io/content/"

echo "Deploying pages to $DEST"
rsync -avz "$SITE_DIR/index.html" "$DEST"
rsync -avz "$SITE_DIR/demo/" "${DEST}demo/"
echo "Done. Fonts and bundle were not touched."
