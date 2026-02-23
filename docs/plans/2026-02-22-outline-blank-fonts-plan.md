# Outline and Blank Font Variants Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Outline (thin-stroked rectangle) and Blank (invisible placeholder) font variants alongside existing Block fonts.

**Architecture:** Extend `build_block_fonts.py` with two new glyph drawing functions and a style loop. Each source font produces three output files (`-Block`, `-Outline`, `-Blank`). No changes needed to `build_site.py` or CI.

**Tech Stack:** Python 3, fontTools (TTGlyphPen, TrueType contours)

---

### Task 1: Add outline glyph drawing function

**Files:**
- Modify: `build_block_fonts.py:64-72` (add new function after `make_block_glyph`)

**Step 1: Add `make_outline_glyph` function**

Add this function after `make_block_glyph` (after line 72):

```python
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
```

**Step 2: Verify it parses**

Run: `python -c "import build_block_fonts; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add build_block_fonts.py
git commit -m "feat: add outline glyph drawing function"
```

---

### Task 2: Add style enum and refactor filename generation

**Files:**
- Modify: `build_block_fonts.py:254-273` (update `get_block_filename`)

**Step 1: Replace `get_block_filename` with style-aware version**

Replace the existing `get_block_filename` function with:

```python
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
```

**Step 2: Verify it parses**

Run: `python -c "import build_block_fonts; print(build_block_fonts.get_styled_filename('Nunito[wght].woff2', 'Outline'))"`
Expected: `Nunito-Outline.woff2`

**Step 3: Commit**

```bash
git add build_block_fonts.py
git commit -m "refactor: generalize filename generation for multiple font styles"
```

---

### Task 3: Refactor `build_block_font` to accept a style parameter

**Files:**
- Modify: `build_block_fonts.py:87-251` (refactor `build_block_font`)

**Step 1: Add style parameter and dispatch glyph drawing**

Change the function signature from:
```python
def build_block_font(src_path: Path, dest_path: Path) -> bool:
```
to:
```python
def build_block_font(src_path: Path, dest_path: Path, style: str = "Block") -> bool:
```

Then in the glyph replacement loop (around line 176), change:

```python
        # Replace each glyph with a solid rectangle
        for glyph_name in glyph_order:
            advance_width = hmtx[glyph_name][0]
            if advance_width == 0 or glyph_name == ".notdef":
                glyf_table[glyph_name] = Glyph()
                continue

            ttpen = TTGlyphPen(None)
            make_block_glyph(ttpen, advance_width, ascender, descender)
            glyf_table[glyph_name] = ttpen.glyph()
```

to:

```python
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
```

**Step 2: Adjust gvar logic for Blank style**

In the gvar section (around line 207), the point count calculation already handles empty glyphs correctly — `numberOfContours` will be 0 for Blank glyphs, so `n_points` will be 0, and phantom point coords will be just the 4 phantom entries. No change needed in the gvar logic itself.

**Step 3: Verify it parses**

Run: `python -c "import build_block_fonts; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add build_block_fonts.py
git commit -m "feat: add style parameter to build_block_font for Outline and Blank variants"
```

---

### Task 4: Update main() to generate all three styles

**Files:**
- Modify: `build_block_fonts.py:276+` (update `main` function)

**Step 1: Update work item collection to loop over styles**

Replace the work item collection loop in `main()` (the `for font_dir in sorted(BUILD_DIR.iterdir()):` block) with:

```python
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
```

**Step 2: Update the processing loop to pass style**

Change:
```python
        for src_file, dest_file, dir_name in pbar:
            pbar.set_description(f"{dir_name[:20]:<20}")
            if build_block_font(src_file, dest_file):
```

to:
```python
        for src_file, dest_file, dir_name, style in pbar:
            pbar.set_description(f"{dir_name[:20]:<20}")
            if build_block_font(src_file, dest_file, style):
```

**Step 3: Update the banner text**

Change the banner from:
```python
    print("  f o n t a i n e  —  Block Font Builder")
```
to:
```python
    print("  f o n t a i n e  —  Placeholder Font Builder")
```

**Step 4: Verify it parses**

Run: `python -c "import build_block_fonts; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add build_block_fonts.py
git commit -m "feat: generate Outline and Blank variants alongside Block fonts"
```

---

### Task 5: Update docstring and documentation

**Files:**
- Modify: `build_block_fonts.py:1-15` (update module docstring)
- Modify: `WEB-FONTS.md:94-129` (add Outline and Blank sections)

**Step 1: Update module docstring**

Replace the opening docstring with:

```python
"""build_block_fonts.py - Generate metric-matched placeholder fonts

Reads WOFF2 fonts from .build/ and generates three placeholder font styles
where every glyph has identical metrics to the source:

  - Block:   Solid filled rectangles (visible placeholder)
  - Outline: Thin-stroked rectangles (lighter visible placeholder)
  - Blank:   Empty glyphs (invisible metric reservation)

Output goes to .build-block/ for deployment.

For variable fonts, extracts exact advance widths across the weight axis
and builds gvar phantom point deltas so advance widths match at ALL
weight values.

Copyright (c) 2025 Noise Factor (https://noisefactor.io/)
MIT License
"""
```

**Step 2: Update WEB-FONTS.md**

Replace the "Block Fonts (Zero-CLS Loading)" section (lines 94-129) with updated docs covering all three styles. Change the section title to "Placeholder Fonts (Zero-CLS Loading)" and add usage examples for Outline and Blank variants with the same CSS pattern.

**Step 3: Commit**

```bash
git add build_block_fonts.py WEB-FONTS.md
git commit -m "docs: update documentation for Outline and Blank font variants"
```

---

### Task 6: Run a smoke test on a single font

**Step 1: Run the builder**

Pick a single small font directory in `.build/` and run:

```bash
python build_block_fonts.py
```

Watch for errors. It should generate new `-Outline.woff2` and `-Blank.woff2` files.

**Step 2: Verify output files exist**

```bash
ls .build-block/inter/
```

Expected: `Inter-Block.woff2`, `Inter-Outline.woff2`, `Inter-Blank.woff2` (and italic variants)

**Step 3: Verify Blank is smaller than Block**

Blank fonts should be smaller since they have no glyph contour data.

```bash
ls -la .build-block/inter/
```

**Step 4: Commit (no code changes — just verification)**

No commit needed for this task.
