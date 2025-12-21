#!/bin/bash
set -e

# Ensure we are in the project root
cd "$(dirname "$0")"

# Setup virtual environment to avoid polluting system python
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

if [ -z "$OPENAI_API_KEY" ] && [ ! -f ".openai" ]; then
    echo "Warning: OPENAI_API_KEY not set."
fi

# Run build pipeline
python3 download_fonts.py
python3 classify_fonts.py # Optional: requires OPENAI_API_KEY
python3 build_bundle.py
python3 build_site.py

# Serve
echo "Serving at http://localhost:8000"
cd dist/site
python3 -m http.server 8000
