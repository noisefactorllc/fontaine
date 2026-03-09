#!/usr/bin/env python3
"""Build the site bundle for deployment."""

import os
import shutil
from pathlib import Path


def build_site():
    """Build the site: landing page at root, bundle demo at /demo."""
    script_dir = Path(__file__).parent
    dist_dir = script_dir / "dist" / "site"
    bundle_dir = script_dir / "bundle"

    # Clean and create output directory
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(parents=True, exist_ok=True)

    # Copy landing page as index.html
    landing_path = script_dir / "index.html"
    if not landing_path.exists():
        raise FileNotFoundError(f"index.html not found at {landing_path}")

    index_path = dist_dir / "index.html"
    shutil.copy(landing_path, index_path)
    print(f"✓ Created {index_path}")
    print(f"  Source: {landing_path}")
    print(f"  Size: {index_path.stat().st_size:,} bytes")

    # Copy bundle/fonts.json to dist/site/bundle/ (needed by landing page)
    catalog_src = bundle_dir / "fonts.json"
    if catalog_src.exists():
        dest_catalog_dir = dist_dir / "bundle"
        dest_catalog_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(catalog_src, dest_catalog_dir / "fonts.json")
        print(f"✓ Copied fonts.json catalog for landing page")

    # Copy bundle demo to /demo
    demo_dir = dist_dir / "demo"
    demo_dir.mkdir(parents=True, exist_ok=True)

    example_path = script_dir / "example.html"
    if not example_path.exists():
        raise FileNotFoundError(f"example.html not found at {example_path}")

    demo_index = demo_dir / "index.html"
    shutil.copy(example_path, demo_index)
    print(f"✓ Created {demo_index}")

    # Copy font-loader.js to demo/
    font_loader_src = script_dir / "font-loader.js"
    if font_loader_src.exists():
        shutil.copy(font_loader_src, demo_dir / "font-loader.js")
        print(f"✓ Copied font-loader.js to demo/")
    else:
        print("⚠ font-loader.js not found")

    # Copy full bundle to demo/ (demo needs manifest, catalog, and zip)
    if bundle_dir.exists():
        dest_bundle = demo_dir / "bundle"
        shutil.copytree(bundle_dir, dest_bundle)
        bundle_files = list(dest_bundle.glob("*"))
        print(f"✓ Copied bundle to demo/ ({len(bundle_files)} files)")
    else:
        print("⚠ Bundle directory not found - skipping bundle copy")

    # Copy WOFF2 web fonts from .build/ into fonts/<name>/
    build_dir = script_dir / ".build"
    if build_dir.exists():
        import re
        fonts_dir = dist_dir / "fonts"
        count = 0
        for font_dir in sorted(build_dir.iterdir()):
            if not font_dir.is_dir():
                continue
            name = re.sub(r'^\d+-', '', font_dir.name)
            dest = fonts_dir / name
            dest.mkdir(parents=True, exist_ok=True)
            for woff2 in font_dir.glob("*.woff2"):
                shutil.copy2(woff2, dest / woff2.name)
                count += 1
        print(f"✓ Copied {count} web font files to {fonts_dir}")
    else:
        print("⚠ .build/ not found - skipping web fonts")

    # Copy block fonts from .build-block/ into fonts/<name>/
    block_dir = script_dir / ".build-block"
    if block_dir.exists():
        import re
        fonts_dir = dist_dir / "fonts"
        count = 0
        for font_dir in sorted(block_dir.iterdir()):
            if not font_dir.is_dir():
                continue
            name = re.sub(r'^\d+-', '', font_dir.name)
            dest = fonts_dir / name
            dest.mkdir(parents=True, exist_ok=True)
            for woff2 in font_dir.glob("*.woff2"):
                shutil.copy2(woff2, dest / woff2.name)
                count += 1
        print(f"✓ Copied {count} block font files to {fonts_dir}")
    else:
        print("⚠ .build-block/ not found - skipping block fonts")


if __name__ == "__main__":
    build_site()
