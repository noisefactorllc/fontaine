#!/usr/bin/env python3
"""
fontaine - Bundle Builder

Builds a distributable font bundle from the downloaded fonts in dist/.
Creates:
  - bundle/fonts.json: Catalog with metadata, tags, and file listings
  - bundle/fonts.zip: Compressed archive of all font files
  - bundle/manifest.json: Bundle manifest with version

The build is deterministic: identical font content produces byte-identical
artifacts, and the manifest version is derived from the bundle content
(zip hash + catalog) instead of the wall clock. FontLoader treats the
version as an opaque cache key, so an unchanged font set keeps the same
version + sha256 and clients reuse their IndexedDB cache instead of
re-downloading the bundle on every rebuild.

Font style is classified using OpenAI Vision API to analyze rendered samples.

Copyright © 2025 Noise Factor (https://noisefactor.io/)
MIT License
"""

import json
import zipfile
import hashlib
import base64
import urllib.request
import urllib.error
import io
import os
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Optional
import sys

try:
    from fontTools.ttLib import TTFont
except ImportError:
    TTFont = None  # Checked in build_bundle(); keeps this module importable
                   # (e.g. by the test suite) without fontTools installed.

# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
DIST_DIR = SCRIPT_DIR / "dist"
BUNDLE_DIR = SCRIPT_DIR / "bundle"
CACHE_FILE = SCRIPT_DIR / "style_cache.json"

# Valid style tags
VALID_STYLES = ["sans-serif", "serif", "monospace", "handwritten", "display", "symbols"]

# ============================================================================
# Style cache - avoid re-classifying fonts
# ============================================================================

def load_style_cache() -> dict:
    """Load cached style classifications."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception as e:
            print(f"Warning: Failed to load style cache from {CACHE_FILE}: {e}")
            pass
    else:
        print(f"Warning: Style cache file not found at {CACHE_FILE}")
    return {}

def extract_font_style(font_dir: Path, cache: dict, font_name: str = None) -> str:
    """Extract font style from cache or default to sans-serif."""
    dir_name = font_dir.name
    
    # Check cache first
    if dir_name in cache:
        return cache[dir_name]
    
    # Fallback if not in cache
    print(f"Error: Style for {dir_name} not found in cache.")
    print("Run 'python3 classify_fonts.py' to generate style cache.")
    sys.exit(1)

def get_font_number(dir_name: str) -> int:
    """Extract font number from directory name like '01-inter'."""
    try:
        return int(dir_name.split("-")[0])
    except (ValueError, IndexError):
        return 0

def get_tags(font_num: int, name: str, style: str) -> list:
    """Generate tags for a font based on extracted style and position.

    The returned list is deterministically ordered so repeated builds
    produce identical catalog bytes (set iteration order is not stable
    across Python processes).
    """
    tags = []

    def add_tag(tag):
        if tag not in tags:
            tags.append(tag)

    # Core vs quirky based on font number
    if font_num <= 50:
        add_tag("core")
    else:
        add_tag("quirky")

    # Style tag from extracted metadata
    add_tag(style)

    # Variable font detection from filename
    name_lower = name.lower()
    if "variable" in name_lower or "flex" in name_lower:
        add_tag("variable")

    # Specific feature tags from name
    if "condensed" in name_lower:
        add_tag("condensed")
    if name.endswith(" SC") or " SC " in name:
        add_tag("small-caps")

    return tags

# ============================================================================
# Font metadata dataclasses
# ============================================================================

@dataclass
class FontFile:
    filename: str
    size: int
    sha256: str

@dataclass
class FontEntry:
    id: str
    name: str
    dir_name: str
    category: str
    style: str
    tags: list
    license: str
    files: list

def extract_license(font_dir: Path) -> str:
    """Extract license type from font directory."""
    for license_file in ["LICENSE.txt", "OFL.txt", "LICENSE", "LICENSE.md"]:
        license_path = font_dir / license_file
        if license_path.exists():
            content = license_path.read_text(errors="ignore").lower()
            if "apache" in content:
                return "Apache-2.0"
            elif "mit" in content:
                return "MIT"
            elif "ofl" in content or "open font" in content:
                return "OFL-1.1"
    return "OFL-1.1"  # Default

def hash_file(file_path: Path) -> str:
    """Calculate SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

# ============================================================================
# WOFF2 Conversion
# ============================================================================

BUILD_DIR = SCRIPT_DIR / ".build"

def convert_to_woff2(src_path: Path, dest_path: Path) -> bool:
    """Convert a TTF/OTF font to WOFF2 format."""
    try:
        from fontTools.ttLib import woff2
        
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load and save as WOFF2
        font = TTFont(src_path)
        font.flavor = 'woff2'
        font.save(dest_path)
        font.close()
        return True
    except Exception as e:
        return False

def build_woff2_fonts(force: bool = False) -> Path:
    """Convert all fonts to WOFF2 format in build directory (idempotent).
    
    Compares expected file count with actual files in dest. Only processes
    fonts that are missing or incomplete.
    """
    from tqdm import tqdm
    import shutil
    
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    
    font_dirs = sorted([d for d in DIST_DIR.iterdir() if d.is_dir()])
    
    # First pass: count all work to be done
    work_items = []  # (font_dir, dest_dir, src_files, is_copy)
    
    for font_dir in font_dirs:
        dir_name = font_dir.name
        dest_font_dir = BUILD_DIR / dir_name
        
        # Count source files
        ttf_otf_files = list(font_dir.rglob("*.ttf")) + list(font_dir.rglob("*.otf"))
        woff2_files = list(font_dir.rglob("*.woff2"))
        
        if woff2_files:
            # Source has WOFF2 - will copy
            expected_count = len(woff2_files)
            src_files = woff2_files
            is_copy = True
        elif ttf_otf_files:
            # Will convert TTF/OTF
            expected_count = len(ttf_otf_files)
            src_files = ttf_otf_files
            is_copy = False
        else:
            continue  # No fonts to process
        
        # Check how many already exist in dest
        if dest_font_dir.exists():
            existing = list(dest_font_dir.glob("*.woff2"))
            if len(existing) >= expected_count:
                continue  # Already complete
        
        # Need to process this font
        for src_file in src_files:
            if is_copy:
                dest_file = dest_font_dir / src_file.name
            else:
                dest_file = dest_font_dir / (src_file.stem + '.woff2')
            
            if not dest_file.exists():
                work_items.append((src_file, dest_file, is_copy, dir_name))
    
    if not work_items:
        print("All fonts already converted to WOFF2.")
        return BUILD_DIR
    
    print(f"Converting {len(work_items)} font files to WOFF2...")
    
    converted = 0
    copied = 0
    failed = 0
    
    with tqdm(work_items, unit="file", ncols=80) as pbar:
        for src_file, dest_file, is_copy, dir_name in pbar:
            pbar.set_description(f"{dir_name[:20]:<20}")
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            
            if is_copy:
                shutil.copy2(src_file, dest_file)
                copied += 1
            else:
                if convert_to_woff2(src_file, dest_file):
                    converted += 1
                else:
                    failed += 1
                    tqdm.write(f"  FAILED: {src_file}")
    
    print(f"Done: {converted} converted, {copied} copied, {failed} failed")
    return BUILD_DIR

def get_woff2_font_files(font_dir: Path) -> list:
    """Get list of WOFF2 font files with metadata."""
    files = []
    
    # Sorted so the catalog (and anything derived from it, like the
    # content-version hash) is stable regardless of directory order.
    for f in sorted(font_dir.rglob("*.woff2")):
        if f.is_file():
            rel_path = f.relative_to(font_dir)
            files.append(FontFile(
                filename=str(rel_path),
                size=f.stat().st_size,
                sha256=hash_file(f)
            ))
    
    return files

def get_font_files(font_dir: Path) -> list:
    """Get list of font files with metadata."""
    font_extensions = {".ttf", ".otf", ".woff", ".woff2", ".ttc"}
    files = []
    
    # Sorted so the catalog (and anything derived from it, like the
    # content-version hash) is stable regardless of directory order.
    for f in sorted(font_dir.rglob("*")):
        if f.is_file() and f.suffix.lower() in font_extensions:
            # Get path relative to font_dir
            rel_path = f.relative_to(font_dir)
            files.append(FontFile(
                filename=str(rel_path),
                size=f.stat().st_size,
                sha256=hash_file(f)
            ))
    
    return files

def scan_fonts() -> list:
    """Scan dist/ directory and build font catalog."""
    fonts = []
    
    if not DIST_DIR.exists():
        print(f"Error: {DIST_DIR} does not exist. Run download_fonts.py first.")
        return []
    
    # Load style cache
    style_cache = load_style_cache()
    cached_count = len(style_cache)
    
    for font_dir in sorted(DIST_DIR.iterdir()):
        if not font_dir.is_dir():
            continue
        
        dir_name = font_dir.name
        font_num = get_font_number(dir_name)
        
        if font_num == 0:
            continue
        
        # Extract name from PROVENANCE.md or directory name
        provenance_file = font_dir / "PROVENANCE.md"
        if provenance_file.exists():
            content = provenance_file.read_text()
            # Extract name from "# Provenance: Font Name"
            for line in content.split("\n"):
                if line.startswith("# Provenance:"):
                    name = line.replace("# Provenance:", "").strip()
                    break
            else:
                name = dir_name.split("-", 1)[1].replace("-", " ").title() if "-" in dir_name else dir_name
        else:
            name = dir_name.split("-", 1)[1].replace("-", " ").title() if "-" in dir_name else dir_name
        
        # Get font files
        files = get_font_files(font_dir)
        if not files:
            print(f"Warning: No font files found in {dir_name}")
            continue
        
        # Extract style using Vision API (with caching)
        style = extract_font_style(font_dir, style_cache, name)
        tags = get_tags(font_num, name, style)
        license_type = extract_license(font_dir)
        
        entry = FontEntry(
            id=dir_name,
            name=name,
            dir_name=dir_name,
            category=style,
            style=style,
            tags=tags,
            license=license_type,
            files=[asdict(f) for f in files]
        )
        
        fonts.append(asdict(entry))
    
    return fonts

# ============================================================================
# Bundle creation
# ============================================================================

# Fixed timestamp for zip entry metadata (1980-01-01, the zip epoch).
# Zip entries default to the source file's mtime, which changes every
# time fonts are re-downloaded, so archive bytes would differ between
# rebuilds of identical content. Fonts ship with `immutable` caching and
# FontLoader verifies the bundle sha256, so a fixed stamp is safe.
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


def create_zip_bundle(fonts: list, source_dir: Path, zip_path: Path = None) -> tuple:
    """Create ZIP archive of all font files. Returns (path, size, hash).

    The archive is byte-for-byte deterministic for identical font
    content: entries are sorted by path and written with fixed metadata,
    independent of filesystem mtimes.
    """
    zip_path = zip_path or (BUNDLE_DIR / "fonts.zip")

    print("Creating fonts.zip...")

    # Collect then sort by archive path so entry order is deterministic
    # regardless of catalog iteration order.
    entries = []
    for font in fonts:
        font_dir = source_dir / font["dir_name"]

        for file_info in font["files"]:
            file_path = font_dir / file_info["filename"]
            if file_path.exists():
                # Store with path: dir_name/filename
                arc_name = f"{font['dir_name']}/{file_info['filename']}"
                entries.append((arc_name, file_path))
    entries.sort(key=lambda entry: entry[0])

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for arc_name, file_path in entries:
            info = zipfile.ZipInfo(arc_name, date_time=ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 3  # Fixed so archives match across platforms
            with open(file_path, "rb") as f:
                zf.writestr(info, f.read())

    size = zip_path.stat().st_size
    file_hash = hash_file(zip_path)

    return zip_path, size, file_hash


def derive_bundle_version(fonts: list, bundle_sha256: str) -> int:
    """Derive the bundle version from bundle content.

    FontLoader uses the version (together with bundle_sha256) as its
    cache key, so the version must change exactly when the bundle
    changes. A wall-clock version invalidated every client's cache on
    every rebuild, even when no font changed. Hashing the catalog plus
    the zip hash makes the version a pure function of content; the
    result is truncated to 52 bits so it stays exact as a JavaScript
    Number (JSON consumers, e.g. FontLoader's version comparison).
    """
    payload = json.dumps(fonts, sort_keys=True).encode("utf-8")
    payload += b"\0" + bundle_sha256.encode("ascii")
    return int(hashlib.sha256(payload).hexdigest()[:13], 16)

def scan_woff2_fonts(woff2_dir: Path) -> list:
    """Scan WOFF2 build directory and build font catalog."""
    fonts = []
    
    if not woff2_dir.exists():
        print(f"Error: {woff2_dir} does not exist.")
        return []
    
    # Load style cache
    style_cache = load_style_cache()
    
    for font_dir in sorted(woff2_dir.iterdir()):
        if not font_dir.is_dir():
            continue
        
        dir_name = font_dir.name
        font_num = get_font_number(dir_name)
        
        if font_num == 0:
            continue
        
        # Get name from original dist directory
        orig_font_dir = DIST_DIR / dir_name
        provenance_file = orig_font_dir / "PROVENANCE.md"
        if provenance_file.exists():
            content = provenance_file.read_text()
            for line in content.split("\n"):
                if line.startswith("# Provenance:"):
                    name = line.replace("# Provenance:", "").strip()
                    break
            else:
                name = dir_name.split("-", 1)[1].replace("-", " ").title() if "-" in dir_name else dir_name
        else:
            name = dir_name.split("-", 1)[1].replace("-", " ").title() if "-" in dir_name else dir_name
        
        # Get WOFF2 files
        files = get_woff2_font_files(font_dir)
        if not files:
            print(f"Warning: No WOFF2 files in {dir_name}")
            continue
        
        # Get style from cache (already classified from dist/)
        style = style_cache.get(dir_name, "sans-serif")
        tags = get_tags(font_num, name, style)
        license_type = extract_license(orig_font_dir)
        
        entry = FontEntry(
            id=dir_name,
            name=name,
            dir_name=dir_name,
            category=style,
            style=style,
            tags=tags,
            license=license_type,
            files=[asdict(f) for f in files]
        )
        
        fonts.append(asdict(entry))
    
    return fonts

def build_bundle():
    """Build the complete font bundle."""
    if TTFont is None:
        print("Error: fontTools required. Install with: pip install fonttools")
        sys.exit(1)

    print()
    print("═" * 60)
    print("  f o n t a i n e  —  Bundle Builder")
    print("  https://noisefactor.io/")
    print("═" * 60)
    print()
    
    # Create bundle directory
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    
    # First, scan original fonts to classify them (populates style cache)
    print("Scanning fonts in dist/...")
    orig_fonts = scan_fonts()
    
    if not orig_fonts:
        print("No fonts found!")
        return
    
    print(f"Found {len(orig_fonts)} fonts")
    
    # Convert to WOFF2
    print()
    woff2_dir = build_woff2_fonts()
    
    # Scan WOFF2 fonts for catalog
    print()
    print("Building WOFF2 catalog...")
    fonts = scan_woff2_fonts(woff2_dir)
    print(f"Cataloged {len(fonts)} fonts")
    
    # Create ZIP bundle from WOFF2 files
    zip_path, zip_size, zip_hash = create_zip_bundle(fonts, woff2_dir)
    print(f"Created: {zip_path}")
    print(f"Size: {zip_size / 1024 / 1024:.1f} MB")
    
    # Version is derived from bundle content (see derive_bundle_version):
    # unchanged fonts keep the same version + sha256, so FontLoader's
    # "already up to date" path stays effective across rebuilds.
    version = derive_bundle_version(fonts, zip_hash)
    version_date = datetime.now(timezone.utc).isoformat()
    
    # Create catalog
    catalog = {
        "name": "fontaine",
        "version": version,
        "version_date": version_date,
        "total_fonts": len(fonts),
        "fonts": fonts
    }
    
    catalog_path = BUNDLE_DIR / "fonts.json"
    with open(catalog_path, "w") as f:
        json.dump(catalog, f, indent=2)
    print(f"Created: {catalog_path}")
    
    # Create manifest
    manifest = {
        "name": "fontaine",
        "version": version,
        "version_date": version_date,
        "bundle_file": "fonts.zip",
        "bundle_size": zip_size,
        "bundle_sha256": zip_hash,
        "catalog_file": "fonts.json",
        "total_fonts": len(fonts),
        "categories": {
            "core": len([f for f in fonts if "core" in f["tags"]]),
            "quirky": len([f for f in fonts if "quirky" in f["tags"]]),
        },
        "styles": {
            "sans-serif": len([f for f in fonts if "sans-serif" in f["tags"]]),
            "serif": len([f for f in fonts if "serif" in f["tags"]]),
            "monospace": len([f for f in fonts if "monospace" in f["tags"]]),
            "handwritten": len([f for f in fonts if "handwritten" in f["tags"]]),
            "display": len([f for f in fonts if "display" in f["tags"]]),
            "special": len([f for f in fonts if f["category"] == "special"]),
        }
    }
    
    manifest_path = BUNDLE_DIR / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Created: {manifest_path}")
    
    # Summary
    print()
    print("=" * 60)
    print("  BUNDLE COMPLETE")
    print("=" * 60)
    print()
    print(f"Version:     {version}")
    print(f"Date:        {version_date}")
    print(f"Total fonts: {len(fonts)}")
    print(f"Bundle size: {zip_size / 1024 / 1024:.1f} MB")
    print()
    print(f"Files created in {BUNDLE_DIR}/:")
    print(f"  - manifest.json  (bundle metadata)")
    print(f"  - fonts.json     (full catalog)")
    print(f"  - fonts.zip      (font files)")
    print()

if __name__ == "__main__":
    build_bundle()
