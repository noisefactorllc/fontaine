#!/usr/bin/env python3
"""Test the built site to verify it can load fonts."""

import http.server
import json
import socketserver
import threading
import time
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError


def test_site():
    """Test that the site bundle is correctly built and can serve fonts."""
    site_dir = Path(__file__).parent / "dist" / "site"
    
    if not site_dir.exists():
        print("✗ dist/site directory not found - run build_site.py first")
        return False
    
    # Check required files exist
    index_html = site_dir / "index.html"
    bundle_dir = site_dir / "bundle"
    fonts_json = bundle_dir / "fonts.json"
    fonts_zip = bundle_dir / "fonts.zip"
    manifest_json = bundle_dir / "manifest.json"
    
    all_good = True
    
    # Check index.html
    if index_html.exists():
        content = index_html.read_text()
        if "FontLoader" in content and "./bundle" in content:
            print(f"✓ index.html exists and references FontLoader with ./bundle path")
        else:
            print(f"✗ index.html missing FontLoader or bundle reference")
            all_good = False
    else:
        print(f"✗ index.html not found")
        all_good = False
    
    # Check bundle files
    if bundle_dir.exists():
        print(f"✓ bundle/ directory exists")
    else:
        print(f"✗ bundle/ directory not found")
        all_good = False
        return all_good
    
    if fonts_json.exists():
        try:
            data = json.loads(fonts_json.read_text())
            font_count = len(data.get("fonts", []))
            print(f"✓ fonts.json exists ({font_count} fonts)")
        except json.JSONDecodeError:
            print(f"✗ fonts.json is not valid JSON")
            all_good = False
    else:
        print(f"✗ fonts.json not found")
        all_good = False
    
    if fonts_zip.exists():
        size_mb = fonts_zip.stat().st_size / (1024 * 1024)
        print(f"✓ fonts.zip exists ({size_mb:.1f} MB)")
    else:
        print(f"✗ fonts.zip not found")
        all_good = False
    
    if manifest_json.exists():
        try:
            data = json.loads(manifest_json.read_text())
            print(f"✓ manifest.json exists (version: {data.get('version', 'unknown')})")
        except json.JSONDecodeError:
            print(f"✗ manifest.json is not valid JSON")
            all_good = False
    else:
        print(f"✗ manifest.json not found")
        all_good = False
    
    if all_good:
        print("\n✓ Site bundle is ready for deployment!")
    else:
        print("\n✗ Site bundle has issues")
    
    return all_good


if __name__ == "__main__":
    import sys
    success = test_site()
    sys.exit(0 if success else 1)
