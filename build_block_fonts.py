#!/usr/bin/env python3
"""build_block_fonts.py - Generate metric-matched block fonts

Reads WOFF2 fonts from .build/ and generates block font variants where
every glyph is a solid rectangle with identical metrics to the source.
Output goes to .build-block/ for S3 sync.

Copyright (c) 2025 Noise Factor (https://noisefactor.io/)
MIT License
"""

import re
import sys
from pathlib import Path

try:
    from fontTools.ttLib import TTFont, newTable
    from fontTools.ttLib.tables._g_l_y_f import Glyph
    from fontTools.pens.ttGlyphPen import TTGlyphPen
except ImportError:
    print("Error: fontTools required. Install with: pip install fonttools")
    sys.exit(1)

try:
    from tqdm import tqdm
except ImportError:
    print("Error: tqdm required. Install with: pip install tqdm")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent.resolve()
BUILD_DIR = SCRIPT_DIR / ".build"
BLOCK_DIR = SCRIPT_DIR / ".build-block"

# Tables to remove (not needed for metric-only block fonts)
STRIP_TABLES = [
    "GPOS", "GSUB", "GDEF",   # OpenType layout
    "fvar", "gvar", "avar",    # Variable font axes
    "STAT", "HVAR", "MVAR",    # Variable font metrics
    "cvar",                     # Variable font hints
    "fpgm", "prep", "cvt ",   # TrueType hinting
    "gasp",                     # Grid-fitting
    "COLR", "CPAL",            # Color fonts
    "SVG ",                     # SVG glyphs
    "DSIG",                     # Digital signature
    "LTSH", "VDMX", "hdmx",   # Device metrics
    "kern",                     # Legacy kerning (GPOS handles this)
    "morx", "feat",            # AAT layout
    "MATH",                     # Math layout
    "BASE",                     # Baseline data
    "JSTF",                     # Justification
    "EBDT", "EBLC", "EBSC",   # Embedded bitmaps
    "CBDT", "CBLC",            # Color bitmaps
    "sbix",                     # Apple color bitmaps
]


def make_block_glyph(pen, advance_width, ascender, descender):
    """Draw a solid rectangle from descender to ascender, full advance width."""
    if advance_width == 0:
        return
    pen.moveTo((0, descender))
    pen.lineTo((0, ascender))
    pen.lineTo((advance_width, ascender))
    pen.lineTo((advance_width, descender))
    pen.closePath()


def build_block_font(src_path: Path, dest_path: Path) -> bool:
    """Generate a block font from a source font file."""
    try:
        font = TTFont(src_path)

        # Read font-level metrics
        ascender = font["OS/2"].sTypoAscender
        descender = font["OS/2"].sTypoDescender

        # Determine if CFF or TrueType outlines
        is_cff = "CFF " in font or "CFF2" in font
        glyf_table = None if is_cff else font.get("glyf")

        # Get glyph order and metrics
        glyph_order = font.getGlyphOrder()
        hmtx = font["hmtx"]

        if is_cff:
            # For CFF fonts, rebuild with TrueType outlines (simpler rectangles)
            # Remove CFF tables and add glyf/loca
            for table_tag in ["CFF ", "CFF2"]:
                if table_tag in font:
                    del font[table_tag]

            font["glyf"] = newTable("glyf")
            font["glyf"].glyphs = {}
            font["glyf"].glyphOrder = glyph_order
            font["loca"] = newTable("loca")

            # Update head table for TrueType
            font["head"].glyphDataFormat = 0

            glyf_table = font["glyf"]

        # Replace each glyph with a solid rectangle
        for glyph_name in glyph_order:
            advance_width = hmtx[glyph_name][0]
            if advance_width == 0 or glyph_name == ".notdef":
                glyf_table[glyph_name] = Glyph()
                continue

            ttpen = TTGlyphPen(None)
            make_block_glyph(ttpen, advance_width, ascender, descender)
            glyf_table[glyph_name] = ttpen.glyph()

        # Strip unnecessary tables
        for table_tag in STRIP_TABLES:
            if table_tag in font:
                del font[table_tag]

        # Save as WOFF2
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        font.flavor = "woff2"
        font.save(str(dest_path))
        font.close()
        return True

    except Exception as e:
        print(f"  FAILED: {src_path.name}: {e}")
        return False


def get_block_filename(src_filename: str) -> str:
    """Convert source filename to block filename.

    Examples:
        Nunito[wght].woff2 -> Nunito-Block.woff2
        Nunito-Italic[wght].woff2 -> Nunito-Italic-Block.woff2
        Audiowide-Regular.woff2 -> Audiowide-Block.woff2
        NotoSansMono[wdth,wght].woff2 -> NotoSansMono-Block.woff2
    """
    name = src_filename
    # Remove .woff2 extension
    name = name.replace(".woff2", "")
    # Remove variable font axis brackets [wght], [wdth,wght], etc.
    name = re.sub(r'\[.*?\]', '', name)
    name = re.sub(r'%5B.*?%5D', '', name)  # URL-encoded brackets
    # Remove -Regular suffix (redundant with -Block)
    name = re.sub(r'-Regular$', '', name)
    # Remove trailing hyphen if any
    name = name.rstrip('-')
    return f"{name}-Block.woff2"


def main():
    print()
    print("=" * 60)
    print("  f o n t a i n e  —  Block Font Builder")
    print("  https://noisefactor.io/")
    print("=" * 60)
    print()

    if not BUILD_DIR.exists():
        print(f"Error: {BUILD_DIR} does not exist. Run build_bundle.py first.")
        sys.exit(1)

    BLOCK_DIR.mkdir(parents=True, exist_ok=True)

    # Collect all font files to process
    work_items = []
    for font_dir in sorted(BUILD_DIR.iterdir()):
        if not font_dir.is_dir():
            continue

        woff2_files = list(font_dir.glob("*.woff2"))
        if not woff2_files:
            continue

        dest_dir = BLOCK_DIR / font_dir.name

        for src_file in woff2_files:
            block_name = get_block_filename(src_file.name)
            dest_file = dest_dir / block_name
            if not dest_file.exists():
                work_items.append((src_file, dest_file, font_dir.name))

    if not work_items:
        print("All block fonts already generated.")
        return

    print(f"Generating {len(work_items)} block fonts...")
    print()

    success = 0
    failed = 0

    with tqdm(work_items, unit="file", ncols=80) as pbar:
        for src_file, dest_file, dir_name in pbar:
            pbar.set_description(f"{dir_name[:20]:<20}")
            if build_block_font(src_file, dest_file):
                success += 1
            else:
                failed += 1

    print()
    print(f"Done: {success} generated, {failed} failed")

    # Report sizes
    total_size = sum(
        f.stat().st_size
        for f in BLOCK_DIR.rglob("*.woff2")
    )
    print(f"Total block font size: {total_size / 1024:.0f} KB")
    print(f"Average per font: {total_size / max(success, 1) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
