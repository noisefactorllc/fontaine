# Outline and Blank Font Variants

## Summary

Add two new placeholder font styles alongside the existing Block fonts:

- **Outline**: Thin-stroked rectangle (2 font units). Two nested TrueType contours — outer clockwise (fill), inner counter-clockwise (hole).
- **Blank**: Empty glyphs with correct advance widths. No contour data — pure metric reservation.

## Glyph Drawing

| Style | Contours | Visual |
|-------|----------|--------|
| Block | 1 clockwise rectangle | Solid filled bar |
| Outline | 2 rectangles (outer CW, inner CCW) | Thin rectangle stroke |
| Blank | 0 contours | Invisible |

### Outline Detail

Outer contour (clockwise, same as Block):
```
(0, descender) → (0, ascender) → (width, ascender) → (width, descender)
```

Inner contour (counter-clockwise, creates hole):
```
(S, descender+S) → (width-S, descender+S) → (width-S, ascender-S) → (S, ascender-S)
```

Where S = 2 (stroke width in font units). Minimum advance width for outline = 2*S+1 = 5 units; narrower glyphs fall back to solid fill.

### Blank Detail

Empty `Glyph()` object — same as zero-width glyphs already get. Advance width preserved in `hmtx`.

## Output

```
.build-block/{font}/{Font}-Block.woff2    (existing)
.build-block/{font}/{Font}-Outline.woff2  (new)
.build-block/{font}/{Font}-Blank.woff2    (new)
```

## Variable Font Support

All three styles use identical gvar phantom point delta logic. Blank glyphs have 0 outline points, so phantom point coords are just 4 entries (no outline point padding).

## Pipeline

No changes needed to `build_site.py` or CI — existing copy logic and cache key handle this automatically.
