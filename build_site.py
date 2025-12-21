#!/usr/bin/env python3
"""Build the site bundle for deployment."""

import os
import shutil
from pathlib import Path


def build_site():
    """Build the site by copying example.html to dist/site/index.html."""
    script_dir = Path(__file__).parent
    dist_dir = script_dir / "dist" / "site"
    bundle_dir = script_dir / "bundle"
    
    # Clean and create output directory
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    dist_dir.mkdir(parents=True, exist_ok=True)
    
    # Read example.html
    example_path = script_dir / "example.html"
    if not example_path.exists():
        raise FileNotFoundError(f"example.html not found at {example_path}")
    
    content = example_path.read_text(encoding="utf-8")
    
    # Write as index.html (no modifications needed - ./bundle path works as-is)
    index_path = dist_dir / "index.html"
    index_path.write_text(content, encoding="utf-8")
    
    print(f"✓ Created {index_path}")
    print(f"  Source: {example_path}")
    print(f"  Size: {index_path.stat().st_size:,} bytes")
    
    # Copy font-loader.js
    font_loader_src = script_dir / "font-loader.js"
    if font_loader_src.exists():
        font_loader_dest = dist_dir / "font-loader.js"
        shutil.copy(font_loader_src, font_loader_dest)
        print(f"✓ Copied font-loader.js")
    else:
        print("⚠ font-loader.js not found")
    
    # Copy bundle directory for local testing
    if bundle_dir.exists():
        dest_bundle = dist_dir / "bundle"
        shutil.copytree(bundle_dir, dest_bundle)
        bundle_files = list(dest_bundle.glob("*"))
        print(f"✓ Copied bundle ({len(bundle_files)} files)")
    else:
        print("⚠ Bundle directory not found - skipping bundle copy")


if __name__ == "__main__":
    build_site()
