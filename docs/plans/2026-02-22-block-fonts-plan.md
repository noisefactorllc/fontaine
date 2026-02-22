# Block Fonts Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Generate metric-matched block fonts for all 100 fontaine fonts and integrate them into the web font pipeline and 10 Noise Factor sites to eliminate CLS.

**Architecture:** A Python script (`build_block_fonts.py`) uses fontTools to read each source font, replace glyph outlines with solid rectangles while preserving all metrics, and export tiny WOFF2 files. These are synced to the CDN alongside real fonts. Each site's CSS adds block font @font-face rules and inserts them into fallback chains.

**Tech Stack:** Python 3, fontTools (existing dependency), WOFF2, CSS @font-face

**Design doc:** `docs/plans/2026-02-22-block-fonts-design.md`

---

### Task 1: Build the block font generator

**Files:**
- Create: `build_block_fonts.py`
- Reference: `build_bundle.py` (for directory structure patterns)

**Step 1: Write the script**

```python
#!/usr/bin/env python3
"""build_block_fonts.py - Generate metric-matched block fonts

Reads WOFF2 fonts from .build/ and generates block font variants where
every glyph is a solid rectangle with identical metrics to the source.
Output goes to .build-block/ for S3 sync.

Copyright (c) 2025 Noise Factor (https://noisefactor.io/)
MIT License
"""

import sys
from pathlib import Path

try:
    from fontTools.ttLib import TTFont
    from fontTools.pens.t2Pen import T2Pen
    from fontTools.pens.pointPen import PointToSegmentPen
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
    pen.lineTo((advance_width, descender))
    pen.lineTo((advance_width, ascender))
    pen.lineTo((0, ascender))
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

            from fontTools.ttLib import newTable
            from fontTools.ttLib.tables._g_l_y_f import table__g_l_y_f

            font["glyf"] = newTable("glyf")
            font["glyf"].glyphs = {}
            font["loca"] = newTable("loca")

            # Update head table for TrueType
            font["head"].glyphDataFormat = 0

            glyf_table = font["glyf"]

            for glyph_name in glyph_order:
                advance_width = hmtx[glyph_name][0]
                if advance_width == 0 or glyph_name == ".notdef":
                    # Empty glyph
                    from fontTools.ttLib.tables._g_l_y_f import Glyph
                    glyf_table[glyph_name] = Glyph()
                    continue

                pen = glyf_table.glyphPen(font)
                # We use the table's pen interface instead
                from fontTools.pens.ttGlyphPen import TTGlyphPen
                ttpen = TTGlyphPen(None)
                make_block_glyph(ttpen, advance_width, ascender, descender)
                glyf_table[glyph_name] = ttpen.glyph()
        else:
            # TrueType outlines - replace each glyph in-place
            from fontTools.pens.ttGlyphPen import TTGlyphPen

            for glyph_name in glyph_order:
                advance_width = hmtx[glyph_name][0]
                if advance_width == 0 or glyph_name == ".notdef":
                    from fontTools.ttLib.tables._g_l_y_f import Glyph
                    glyf_table[glyph_name] = Glyph()
                    continue

                ttpen = TTGlyphPen(None)
                make_block_glyph(ttpen, advance_width, ascender, descender)
                glyf_table[glyph_name] = ttpen.glyph()

        # Strip unnecessary tables
        for table_tag in STRIP_TABLES:
            if table_tag in font:
                del font[table_tag]

        # Update maxp for TrueType
        if "maxp" in font:
            font["maxp"].recalc(font)

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
    import re
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
```

**Step 2: Run the generator**

Run: `cd /Users/aayars/source/fontaine && python build_block_fonts.py`
Expected: Generates block fonts in `.build-block/`, reports ~2-8KB per font.

**Step 3: Verify output**

Check a few generated block fonts:
```bash
ls -la .build-block/57-nunito/
# Should see Nunito-Block.woff2 and Nunito-Italic-Block.woff2, each ~2-8KB

ls -la .build-block/08-noto-sans-mono/
# Should see NotoSansMono-Block.woff2, ~2-8KB
```

Verify metrics match by inspecting with fontTools:
```python
from fontTools.ttLib import TTFont
orig = TTFont(".build/57-nunito/Nunito[wght].woff2")
block = TTFont(".build-block/57-nunito/Nunito-Block.woff2")
# Compare: advance widths for 'A', 'W', 'm', 'i' should be identical
for g in ['A', 'W', 'm', 'i']:
    cmap = orig.getBestCmap()
    glyph_name = cmap[ord(g)]
    assert orig['hmtx'][glyph_name][0] == block['hmtx'][glyph_name][0], f"Mismatch for '{g}'"
print("Metrics match!")
```

**Step 4: Commit**

```bash
git add build_block_fonts.py
git commit -m "feat: add block font generator for zero-CLS font loading"
```

---

### Task 2: Update S3 sync to include block fonts

**Files:**
- Modify: `sync_fonts_to_s3.py`

**Step 1: Add block font sync**

In `sync_fonts_to_s3.py`, after the existing font sync loop (line ~146), add a second loop for block fonts. The block fonts go into the same S3 directories as regular fonts (same `fonts/{fontname}/` prefix).

Add at the top of the file, after `BUILD_DIR` (line 28):
```python
BLOCK_DIR = SCRIPT_DIR / ".build-block"
```

After the existing font sync loop (after the `for font_dir in sorted(BUILD_DIR.iterdir()):` block ends around line 141), add:

```python
    # Sync block fonts (same S3 prefix, merged into font directories)
    if BLOCK_DIR.exists():
        print()
        log_info(f"Syncing block fonts from {BLOCK_DIR.name}/\n")

        block_count = 0
        block_failed = 0

        for font_dir in sorted(BLOCK_DIR.iterdir()):
            if not font_dir.is_dir():
                continue

            woff2_files = list(font_dir.glob("*.woff2"))
            if not woff2_files:
                continue

            font_name = strip_number_prefix(font_dir.name)
            log_info(f"Syncing {font_name}/ (block)")

            if sync_font_to_s3(font_dir, font_name, args.dry_run):
                block_count += 1
            else:
                block_failed += 1

        log_success(f"Synced {block_count} block fonts")

        if block_failed > 0:
            log_error(f"{block_failed} block fonts failed to sync")
            failed_count += block_failed
```

**Step 2: Test with dry run**

Run: `cd /Users/aayars/source/fontaine && python sync_fonts_to_s3.py --dry-run`
Expected: Shows block fonts would be uploaded to the same S3 directories as regular fonts.

**Step 3: Commit**

```bash
git add sync_fonts_to_s3.py
git commit -m "feat: sync block fonts to S3 alongside regular fonts"
```

---

### Task 3: Update generative-toys-website fonts

**Files:**
- Modify: `/Users/aayars/source/generative-toys-website/public/css/index.css`

**Step 1: Add block font @font-face and update fallback chain**

Before the existing Nunito `@font-face`, add:
```css
@font-face {
    font-family: 'Nunito Block';
    src: url('https://fonts.noisefactor.io/fonts/nunito/Nunito-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}
```

Update all `font-family` declarations to include the block font fallback. Change:
```css
font-family: 'Nunito', sans-serif;
```
to:
```css
font-family: 'Nunito', 'Nunito Block', sans-serif;
```

Also remove the `<link rel="preload">` tag for Nunito from the HTML if present (the block font replaces this optimization).

**Step 2: Commit**

```bash
cd /Users/aayars/source/generative-toys-website
git add -A && git commit -m "feat: add block font fallback for zero-CLS font loading"
```

---

### Task 4: Update noisedeck fonts

**Files:**
- Modify: `/Users/aayars/source/noisedeck/app/css/theme.css`

**Step 1: Add block font @font-face rules**

Before existing font declarations, add:
```css
@font-face {
    font-family: 'Nunito Block';
    src: url('https://fonts.noisefactor.io/fonts/nunito/Nunito-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}

@font-face {
    font-family: 'Noto Sans Mono Block';
    src: url('https://fonts.noisefactor.io/fonts/noto-sans-mono/NotoSansMono-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}
```

**Step 2: Update fallback chains**

In CSS variable declarations, insert block fonts before system fallbacks:
```css
--font-mono: 'Noto Sans Mono', 'Noto Sans Mono Block', ui-monospace, 'Cascadia Mono', 'Consolas', monospace;
--code-editor-font: 'Noto Sans Mono', 'Noto Sans Mono Block', ui-monospace, 'Cascadia Mono', 'Consolas', monospace;
```

And update body/general font-family rules to add `'Nunito Block'` after `Nunito` in all fallback chains.

**Step 3: Commit**

```bash
cd /Users/aayars/source/noisedeck
git add -A && git commit -m "feat: add block font fallbacks for zero-CLS font loading"
```

---

### Task 5: Update polymorphic fonts

**Files:**
- Modify: `/Users/aayars/source/polymorphic/public/index.html` (inline `<style>`)
- Modify: `/Users/aayars/source/polymorphic/public/css/menu.css`

**Step 1: Add block font @font-face in index.html `<style>`**

Add before existing @font-face rules:
```css
@font-face {
    font-family: 'Nunito Block';
    src: url('https://fonts.noisefactor.io/fonts/nunito/Nunito-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}

@font-face {
    font-family: 'Comfortaa Block';
    src: url('https://fonts.noisefactor.io/fonts/comfortaa/Comfortaa-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}
```

**Step 2: Update fallback chains**

In index.html:
```css
font-family: 'Nunito', 'Nunito Block', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
font-family: 'Comfortaa', 'Comfortaa Block', 'Nunito', 'Nunito Block', sans-serif;
```

In menu.css, update `--font-accent` and other font-family usages:
```css
--font-accent: 'Comfortaa', 'Comfortaa Block', 'Nunito', 'Nunito Block', sans-serif;
```

Remove `<link rel="preconnect" href="https://fonts.noisefactor.io" crossorigin>` if present (block fonts make preconnect unnecessary).

**Step 3: Commit**

```bash
cd /Users/aayars/source/polymorphic
git add -A && git commit -m "feat: add block font fallbacks for zero-CLS font loading"
```

---

### Task 6: Update foundry fonts

**Files:**
- Modify: `/Users/aayars/source/foundry/public/css/fonts.css`

**Step 1: Add block font @font-face rules**

Add before existing rules:
```css
@font-face {
    font-family: 'Nunito Block';
    src: url('https://fonts.noisefactor.io/fonts/nunito/Nunito-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}

@font-face {
    font-family: 'Noto Sans Mono Block';
    src: url('https://fonts.noisefactor.io/fonts/noto-sans-mono/NotoSansMono-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}

@font-face {
    font-family: 'Victor Mono Block';
    src: url('https://fonts.noisefactor.io/fonts/victor-mono/VictorMono-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}
```

**Step 2: Update CSS variable fallback chains**

```css
--font-display: 'Nunito', 'Nunito Block', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
--font-body: 'Nunito', 'Nunito Block', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
--font-mono: 'Noto Sans Mono', 'Noto Sans Mono Block', 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Code', monospace;
--font-logotype: 'Victor Mono', 'Victor Mono Block', 'SF Mono', 'Monaco', monospace;
```

Leave `--font-icon` unchanged (Material Symbols uses `font-display: block`).

**Step 3: Commit**

```bash
cd /Users/aayars/source/foundry
git add -A && git commit -m "feat: add block font fallbacks for zero-CLS font loading"
```

---

### Task 7: Update shade fonts

**Files:**
- Modify: `/Users/aayars/source/shade/public/css/fonts.css`

**Step 1: Add block font @font-face rules**

```css
@font-face {
    font-family: 'Audiowide Block';
    src: url('https://fonts.noisefactor.io/fonts/audiowide/Audiowide-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}

@font-face {
    font-family: 'Nunito Block';
    src: url('https://fonts.noisefactor.io/fonts/nunito/Nunito-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}

@font-face {
    font-family: 'Noto Sans Mono Block';
    src: url('https://fonts.noisefactor.io/fonts/noto-sans-mono/NotoSansMono-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}
```

**Step 2: Update CSS variable fallback chains**

```css
--font-display: 'Audiowide', 'Audiowide Block', 'Orbitron', 'Rajdhani', sans-serif;
--font-body: 'Nunito', 'Nunito Block', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
--font-chat: 'Nunito', 'Nunito Block', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
--font-mono: 'Noto Sans Mono', 'Noto Sans Mono Block', 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Code', monospace;
```

**Step 3: Commit**

```bash
cd /Users/aayars/source/shade
git add -A && git commit -m "feat: add block font fallbacks for zero-CLS font loading"
```

---

### Task 8: Update layers fonts

**Files:**
- Modify: `/Users/aayars/source/layers/public/css/fonts.css`

**Step 1: Add block font @font-face rules**

```css
@font-face {
    font-family: 'Nunito Block';
    src: url('https://fonts.noisefactor.io/fonts/nunito/Nunito-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}

@font-face {
    font-family: 'Noto Sans Mono Block';
    src: url('https://fonts.noisefactor.io/fonts/noto-sans-mono/NotoSansMono-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}

@font-face {
    font-family: 'Cormorant Upright Block';
    src: url('https://fonts.noisefactor.io/fonts/cormorant-upright/CormorantUpright-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}
```

**Step 2: Update CSS variable fallback chains**

```css
--font-body: 'Nunito', 'Nunito Block', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
--font-mono: 'Noto Sans Mono', 'Noto Sans Mono Block', 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Code', monospace;
--font-accent: 'Cormorant Upright', 'Cormorant Upright Block', 'Times New Roman', serif;
```

**Step 3: Commit**

```bash
cd /Users/aayars/source/layers
git add -A && git commit -m "feat: add block font fallbacks for zero-CLS font loading"
```

---

### Task 9: Update tetra fonts

**Files:**
- Modify: `/Users/aayars/source/tetra/app/css/index.css`

**Step 1: Add block font @font-face rules**

Add before existing rules:
```css
@font-face {
    font-family: 'Nunito Block';
    src: url('https://fonts.noisefactor.io/fonts/nunito/Nunito-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}

@font-face {
    font-family: 'Noto Sans Mono Block';
    src: url('https://fonts.noisefactor.io/fonts/noto-sans-mono/NotoSansMono-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}

@font-face {
    font-family: 'Rubik Block';
    src: url('https://fonts.noisefactor.io/fonts/rubik/Rubik-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}
```

**Step 2: Update font-family fallback chains**

Wherever Nunito, Noto Sans Mono, or Rubik appear in font-family declarations, insert the block variant after them. For example:
```css
font-family: 'Nunito', 'Nunito Block', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
```

**Step 3: Commit**

```bash
cd /Users/aayars/source/tetra
git add -A && git commit -m "feat: add block font fallbacks for zero-CLS font loading"
```

---

### Task 10: Update blaster fonts

**Files:**
- Modify: `/Users/aayars/source/blaster/frontend/css/index.css`

**Step 1: Add block font @font-face rules**

```css
@font-face {
    font-family: 'Nunito Block';
    src: url('https://fonts.noisefactor.io/fonts/nunito/Nunito-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}

@font-face {
    font-family: 'Press Start 2P Block';
    src: url('https://fonts.noisefactor.io/fonts/press-start-2p/PressStart2P-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}
```

**Step 2: Update fallback chains**

```css
--font-family: 'Nunito', 'Nunito Block', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
```

And for the logotype:
```css
.logotype { font-family: 'Press Start 2P', 'Press Start 2P Block', monospace; }
```

**Step 3: Commit**

```bash
cd /Users/aayars/source/blaster
git add -A && git commit -m "feat: add block font fallbacks for zero-CLS font loading"
```

---

### Task 11: Update sharing-is-caring fonts

**Files:**
- Modify: `/Users/aayars/source/sharing-is-caring/public/index.html`
- Modify: `/Users/aayars/source/sharing-is-caring/public/create.html`

**Step 1: Add block font @font-face in both HTML files' `<style>` blocks**

Add before existing Nunito @font-face:
```css
@font-face {
    font-family: 'Nunito Block';
    src: url('https://fonts.noisefactor.io/fonts/nunito/Nunito-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}
```

**Step 2: Update fallback chains**

```css
font-family: 'Nunito', 'Nunito Block', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
```

Remove `<link rel="preload" ...Nunito...>` tags (block font replaces this).

**Step 3: Commit**

```bash
cd /Users/aayars/source/sharing-is-caring
git add -A && git commit -m "feat: add block font fallback for zero-CLS font loading"
```

---

### Task 12: Update shuffleset.stream fonts

**Files:**
- Modify: `/Users/aayars/source/shuffleset.stream/public/css/base.css`

**Step 1: Add block font @font-face rules**

```css
@font-face {
    font-family: 'Nunito Block';
    src: url('https://fonts.noisefactor.io/fonts/nunito/Nunito-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}

@font-face {
    font-family: 'Rubik Block';
    src: url('https://fonts.noisefactor.io/fonts/rubik/Rubik-Block.woff2') format('woff2');
    font-weight: 400;
    font-style: normal;
}
```

Note: VCR OSD Mono is a TTF file (`VCR_OSD_MONO_1.001.ttf`). The block font generator needs to handle this — it may not be in `.build/` as WOFF2. Check if it exists; if not, skip VCR block font for now.

**Step 2: Update fallback chains**

```css
body { font-family: Nunito, 'Nunito Block', sans-serif; }
h1, h2, h3, h4, h5, h6 { font-family: Rubik, 'Rubik Block', sans-serif; }
```

**Step 3: Commit**

```bash
cd /Users/aayars/source/shuffleset.stream
git add -A && git commit -m "feat: add block font fallbacks for zero-CLS font loading"
```

---

### Task 13: Update fontaine docs

**Files:**
- Modify: `WEB-FONTS.md`

**Step 1: Add block fonts documentation**

Add a new section to WEB-FONTS.md after the "Variable Fonts" section:

```markdown
## Block Fonts (Zero-CLS Loading)

Block fonts are metric-matched placeholder fonts where every glyph is a solid rectangle.
They load near-instantly (~3KB) and prevent layout shift when the real font loads.

### Using Block Fonts

1. Add a block font `@font-face` rule:

\```css
@font-face {
  font-family: 'Inter Block';
  src: url('https://fonts.noisefactor.io/fonts/inter/Inter-Block.woff2') format('woff2');
  font-weight: 400;
  font-style: normal;
}
\```

2. Add the block font to your fallback chain:

\```css
body {
  font-family: 'Inter', 'Inter Block', sans-serif;
}
\```

Block fonts follow the naming pattern: `{FontName}-Block.woff2`

### Building Block Fonts

\```bash
python build_block_fonts.py
\```

This reads fonts from `.build/` and generates block variants in `.build-block/`.
They are synced to S3 alongside regular fonts by `sync_fonts_to_s3.py`.
```

**Step 2: Commit**

```bash
cd /Users/aayars/source/fontaine
git add WEB-FONTS.md
git commit -m "docs: add block fonts documentation to WEB-FONTS.md"
```

---

### Task 14: Run full pipeline and deploy

**Step 1: Generate all block fonts**

```bash
cd /Users/aayars/source/fontaine
python build_block_fonts.py
```

Expected: All 100 fonts get block variants, total size ~300-500KB.

**Step 2: Dry-run S3 sync**

```bash
python sync_fonts_to_s3.py --dry-run
```

Expected: Shows block fonts would be uploaded alongside existing fonts.

**Step 3: Deploy to S3**

```bash
python sync_fonts_to_s3.py
```

**Step 4: Verify a block font loads from CDN**

```bash
curl -I https://fonts.noisefactor.io/fonts/nunito/Nunito-Block.woff2
```

Expected: HTTP 200, Content-Type: font/woff2
