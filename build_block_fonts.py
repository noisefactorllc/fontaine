#!/usr/bin/env python3
"""build_block_fonts.py - Generate metric-matched block fonts

Reads WOFF2 fonts from .build/ and generates block font variants where
every glyph is a solid rectangle with identical metrics to the source.
Output goes to .build-block/ for S3 sync.

For variable fonts, instantiates at each weight used across Noise Factor
sites, extracts exact advance widths, then builds a variable block font
with correct gvar phantom point deltas so advance widths match at ALL
weight values.

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
    from fontTools.varLib.instancer import instantiateVariableFont
    from fontTools.ttLib.tables._g_v_a_r import TupleVariation
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
    "HVAR",                     # Replaced by gvar phantom point deltas
    "MVAR",                     # Metric variations
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


def make_outline_glyph(pen, advance_width, ascender, descender):
    """Draw a thin-stroked rectangle outline from descender to ascender."""
    if advance_width == 0:
        return
    S = 2  # stroke width in font units
    # If glyph is too narrow for an outline, fall back to solid fill
    if advance_width < 2 * S + 1 or (ascender - descender) < 2 * S + 1:
        make_block_glyph(pen, advance_width, ascender, descender)
        return
    # Outer contour (clockwise = filled)
    pen.moveTo((0, descender))
    pen.lineTo((0, ascender))
    pen.lineTo((advance_width, ascender))
    pen.lineTo((advance_width, descender))
    pen.closePath()
    # Inner contour (counter-clockwise = hole)
    pen.moveTo((S, descender + S))
    pen.lineTo((advance_width - S, descender + S))
    pen.lineTo((advance_width - S, ascender - S))
    pen.lineTo((S, ascender - S))
    pen.closePath()


def get_advance_widths_at_weight(src_path, weight):
    """Instantiate variable font at a specific weight and return all advance widths."""
    font = TTFont(src_path)
    instantiateVariableFont(font, {"wght": weight}, inplace=True)
    hmtx = font["hmtx"]
    widths = {}
    for glyph_name in font.getGlyphOrder():
        widths[glyph_name] = hmtx[glyph_name][0]
    font.close()
    return widths


def build_block_font(src_path: Path, dest_path: Path, style: str = "Block") -> bool:
    """Generate a block font from a source font file."""
    try:
        font = TTFont(src_path)

        # Check if this is a variable font with weight axis
        is_variable = "fvar" in font
        has_weight_axis = False
        weight_min = weight_max = weight_default = 400
        if is_variable:
            for axis in font["fvar"].axes:
                if axis.axisTag == "wght":
                    has_weight_axis = True
                    weight_min = axis.minValue
                    weight_max = axis.maxValue
                    weight_default = axis.defaultValue
                    break

        # Read font-level metrics
        ascender = font["OS/2"].sTypoAscender
        descender = font["OS/2"].sTypoDescender

        # Determine if CFF or TrueType outlines
        is_cff = "CFF " in font or "CFF2" in font

        # Get glyph order and default metrics
        glyph_order = font.getGlyphOrder()
        hmtx = font["hmtx"]

        # For variable fonts: extract per-glyph advance width deltas from HVAR
        # to build matching gvar phantom point entries
        hvar_regions = []
        hvar_glyph_deltas = {}  # glyph_name -> list of deltas per region
        if is_variable and has_weight_axis and "HVAR" in font:
            hvar = font["HVAR"].table
            vs = hvar.VarStore

            # Extract region definitions (in normalized coordinates)
            for region in vs.VarRegionList.Region:
                for ar in region.VarRegionAxis:
                    if ar.PeakCoord != 0:
                        hvar_regions.append({
                            "start": ar.StartCoord,
                            "peak": ar.PeakCoord,
                            "end": ar.EndCoord,
                        })

            # Extract per-glyph deltas from HVAR
            adv_map = hvar.AdvWidthMap
            for glyph_name in glyph_order:
                if adv_map is not None and glyph_name in adv_map.mapping:
                    packed = adv_map.mapping[glyph_name]
                    outer = packed >> 16
                    inner = packed & 0xFFFF
                else:
                    outer = 0
                    inner = glyph_order.index(glyph_name)

                if outer < len(vs.VarData):
                    vd = vs.VarData[outer]
                    if inner < vd.ItemCount:
                        deltas = list(vd.Item[inner])
                        # Reorder deltas to match region order (VarData has VarRegionIndex)
                        ordered = [0] * len(hvar_regions)
                        for d_idx, r_idx in enumerate(vd.VarRegionIndex):
                            if d_idx < len(deltas):
                                ordered[r_idx] = deltas[d_idx]
                        if any(d != 0 for d in ordered):
                            hvar_glyph_deltas[glyph_name] = ordered

        # Strip gvar before rebuilding glyphs (we'll build our own)
        if "gvar" in font:
            del font["gvar"]

        if is_cff:
            # For CFF fonts, rebuild with TrueType outlines
            for table_tag in ["CFF ", "CFF2"]:
                if table_tag in font:
                    del font[table_tag]

            font["glyf"] = newTable("glyf")
            font["glyf"].glyphs = {}
            font["glyf"].glyphOrder = glyph_order
            font["loca"] = newTable("loca")
            font["head"].glyphDataFormat = 0

        glyf_table = font["glyf"]

        # Replace each glyph based on style
        for glyph_name in glyph_order:
            advance_width = hmtx[glyph_name][0]
            if advance_width == 0 or glyph_name == ".notdef":
                glyf_table[glyph_name] = Glyph()
                continue

            if style == "Blank":
                glyf_table[glyph_name] = Glyph()
            else:
                ttpen = TTGlyphPen(None)
                if style == "Outline":
                    make_outline_glyph(ttpen, advance_width, ascender, descender)
                else:
                    make_block_glyph(ttpen, advance_width, ascender, descender)
                glyf_table[glyph_name] = ttpen.glyph()

        # For variable fonts: build gvar with phantom point deltas for advance widths
        if is_variable and has_weight_axis and hvar_glyph_deltas:
            from fontTools.ttLib.tables._g_v_a_r import table__g_v_a_r

            gvar = table__g_v_a_r()
            gvar.version = 1
            gvar.reserved = 0
            gvar.variations = {}

            for glyph_name in glyph_order:
                glyph = glyf_table.get(glyph_name)
                if glyph is None or not hasattr(glyph, "numberOfContours"):
                    gvar.variations[glyph_name] = []
                    continue

                deltas = hvar_glyph_deltas.get(glyph_name)
                if not deltas:
                    gvar.variations[glyph_name] = []
                    continue

                # Count actual outline points
                n_contour = glyph.numberOfContours if glyph.numberOfContours > 0 else 0
                if n_contour > 0:
                    n_points = max(glyph.endPtsOfContours) + 1
                else:
                    n_points = 0

                # Build one TupleVariation per HVAR region
                tvs = []
                for region_idx, region in enumerate(hvar_regions):
                    adv_delta = deltas[region_idx] if region_idx < len(deltas) else 0
                    if adv_delta == 0:
                        continue

                    # Phantom points: 4 after outline points
                    # [0]=LSB origin, [1]=advance width, [2]=TSB, [3]=vert advance
                    coords = [(0, 0)] * n_points  # outline points: no change
                    coords.append((0, 0))          # phantom 0: LSB origin
                    coords.append((adv_delta, 0))  # phantom 1: advance width delta
                    coords.append((0, 0))          # phantom 2: TSB origin
                    coords.append((0, 0))          # phantom 3: vert advance

                    axes = {"wght": (region["start"], region["peak"], region["end"])}
                    tvs.append(TupleVariation(axes, coords))

                gvar.variations[glyph_name] = tvs

            font["gvar"] = gvar

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
        import traceback
        print(f"  FAILED: {src_path.name}: {e}")
        traceback.print_exc()
        return False


# Font styles to generate
FONT_STYLES = ["Block", "Outline", "Blank"]


def get_styled_filename(src_filename: str, style: str) -> str:
    """Convert source filename to styled filename.

    Examples:
        Nunito[wght].woff2, "Block" -> Nunito-Block.woff2
        Nunito[wght].woff2, "Outline" -> Nunito-Outline.woff2
        Nunito[wght].woff2, "Blank" -> Nunito-Blank.woff2
    """
    name = src_filename
    name = name.replace(".woff2", "")
    name = re.sub(r'\[.*?\]', '', name)
    name = re.sub(r'%5B.*?%5D', '', name)
    name = re.sub(r'-Regular$', '', name)
    name = name.rstrip('-')
    return f"{name}-{style}.woff2"


def main():
    print()
    print("=" * 60)
    print("  f o n t a i n e  —  Placeholder Font Builder")
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
            for style in FONT_STYLES:
                styled_name = get_styled_filename(src_file.name, style)
                dest_file = dest_dir / styled_name
                if not dest_file.exists():
                    work_items.append((src_file, dest_file, font_dir.name, style))

    if not work_items:
        print("All block fonts already generated.")
        return

    print(f"Generating {len(work_items)} block fonts...")
    print()

    success = 0
    failed = 0

    with tqdm(work_items, unit="file", ncols=80) as pbar:
        for src_file, dest_file, dir_name, style in pbar:
            pbar.set_description(f"{dir_name[:20]:<20}")
            if build_block_font(src_file, dest_file, style):
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
