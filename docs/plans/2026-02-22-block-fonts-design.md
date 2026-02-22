# Block Font Design

Zero-CLS font loading for Noise Factor web properties using metric-matched placeholder fonts.

## Problem

Web fonts load asynchronously. When they arrive, their metrics differ from system fallbacks, causing Cumulative Layout Shift (CLS). Preloading/preconnecting degrades initial page load speed.

## Solution

Generate "block fonts" — fonts where every glyph is a solid rectangle but all metrics (advance widths, ascent, descent, bearings, UPM) are identical to the real font. These are ~2-8KB, load in a single packet, and produce zero layout shift when the real font swaps in.

## Scope

- Generate block fonts for all 100 fontaine fonts
- Part of web font deployment pipeline (not the fontaine product bundle)
- Update CSS across 10 Noise Factor sites

## Block Font Generator

**New file:** `fontaine/build_block_fonts.py`

**Input:** WOFF2 fonts in `.build/` (produced by `build_bundle.py`)
**Output:** Block font WOFF2 files in `.build-block/{fontname}/{FontName}-Block.woff2`

**Algorithm per font:**

1. Open source font with fontTools
2. Read font-level metrics: unitsPerEm, ascender, descender
3. For each glyph:
   - Read advance width
   - Replace outline with filled rectangle: `(0, descender)` to `(advanceWidth, ascender)`
   - Preserve advance width exactly
4. Strip unnecessary tables (GPOS, GSUB, fvar, gvar, fpgm, prep, cvt, COLR, CPAL)
5. Keep essential tables: cmap, hmtx, head, hhea, maxp, name, OS/2, post
6. Save as static (non-variable) WOFF2

**Variable font handling:** Generate a single static block font from default axis values. Advance widths don't change with weight, so this is correct for all practical uses.

**Naming:** `{FontName}-Block.woff2`

**Expected sizes:** ~2-8KB per font (vs 50-300KB for real fonts)

## CDN Deployment

**CDN structure (fonts.noisefactor.io):**

```
fonts/{fontname}/{FontName}-Block.woff2     ← new
fonts/{fontname}/{FontName}[wght].woff2     ← existing
```

**Modified:** `sync_fonts_to_s3.py` adds `.build-block/` as source directory.

## CSS Integration Pattern

```css
/* Block font - loads near-instantly (~3KB) */
@font-face {
  font-family: 'Nunito Block';
  font-style: normal;
  font-weight: 400;
  src: url('https://fonts.noisefactor.io/fonts/nunito/Nunito-Block.woff2') format('woff2');
}

/* Real font - loads async */
@font-face {
  font-family: 'Nunito';
  font-style: normal;
  font-weight: 100 900;
  font-display: swap;
  src: url('https://fonts.noisefactor.io/fonts/nunito/Nunito[wght].woff2') format('woff2');
}

/* Fallback chain: real → block → system */
body {
  font-family: 'Nunito', 'Nunito Block', sans-serif;
}
```

**Loading sequence:**

1. Browser parses CSS, requests both fonts
2. Block font loads first (~3KB, one packet)
3. Text renders as solid bars with correct metrics — no invisible text
4. Real font loads, browser swaps it in — zero layout shift

**Inline option:** Sites can base64-encode block fonts directly in `<style>` for zero network requests.

## Pipeline

```bash
python download_fonts.py       # existing
python build_bundle.py          # existing → .build/
python build_block_fonts.py     # NEW → .build-block/
python sync_fonts_to_s3.py      # existing, updated to include .build-block/
```

## Site Updates

Each site's font CSS gets:
1. New `@font-face` rules for block fonts used by that site
2. Block font family added to fallback chains

**Skip:** Material Symbols (icon font, already uses `font-display: block`)
**Skip:** Dynamically loaded fonts in sharing-is-caring (only core UI font Nunito needs block treatment)

### Fonts per site

| Site | Block fonts needed |
|------|--------------------|
| generative-toys-website | Nunito |
| noisedeck | Nunito, Noto Sans Mono |
| polymorphic | Nunito, Comfortaa |
| foundry | Nunito, Noto Sans Mono, Victor Mono |
| shade | Nunito, Noto Sans Mono, Audiowide |
| layers | Nunito, Noto Sans Mono, Cormorant Upright |
| tetra | Nunito, Noto Sans Mono, Rubik |
| blaster | Nunito, Press Start 2P |
| sharing-is-caring | Nunito |
| shuffleset.stream | Nunito, Rubik, VCR |

## Visual behavior

**Before (current):** Text invisible → system font appears → real font loads → layout shifts
**After:** Text appears as solid bars → real font swaps in → no layout shift

The solid bars are a clear "loading" signal and maintain exact layout geometry.
