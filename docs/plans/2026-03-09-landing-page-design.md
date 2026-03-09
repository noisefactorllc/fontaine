# Fontaine Landing Page Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a landing page positioning fontaine as a web font service, with a font browser that uses blank-variant preloading and a detail panel showing CSS snippets and license info.

**Architecture:** Single-page HTML with inline CSS/JS. Loads font catalog from `bundle/fonts.json`. Font previews lazy-load from CDN via IntersectionObserver, using blank variants as instant placeholders. Detail panel slides in from right on card click.

**Tech Stack:** Vanilla HTML/CSS/JS, handfish design system (CDN), fontaine web fonts (CDN)

---

### Task 1: Create `index.html` — Landing Page

**Files:**
- Create: `index.html`

The page is a single HTML file with these sections:

1. **Head** — handfish CSS from CDN, Sacramento + Nunito font faces from fontaine CDN, inline page styles
2. **Hero** — "fontaine" in Sacramento, tagline, three feature bullets
3. **Usage** — two `hf-card` blocks: "Use as Web Fonts" (CSS snippets, preload example) and "Use as a Bundle" (link to /demo)
4. **Font Browser** — search input, filter buttons, grid of lazy-loaded font cards
5. **Detail Panel** — right-side slide-in overlay with font info, live preview, CSS snippets, license

**Key behaviors:**
- Fetch `bundle/fonts.json` on load, render font cards
- IntersectionObserver on each card: when visible, load blank variant instantly (font-display: block), then load real Regular weight (font-display: swap) to replace it
- Card click opens detail panel with font metadata, editable preview text, weight selector, copy-ready CSS, license info (noting block/blank variants share the same license)
- Filter buttons and search box filter the grid
- Escape key or close button dismisses the detail panel

**Step 1:** Write the complete `index.html`

**Step 2:** Verify it loads locally

Run: `cd fontaine && python3 -m http.server 8000`
Open: `http://localhost:8000/index.html`
Expected: Page loads with hero, usage section, font browser populates from fonts.json

**Step 3:** Commit

```bash
git add index.html
git commit -m "feat: add landing page with font browser and detail panel"
```

---

### Task 2: Update `build_site.py`

**Files:**
- Modify: `build_site.py`

**Step 1:** Update build_site.py to:
- Copy `index.html` → `dist/site/index.html` (the landing page)
- Copy `example.html` → `dist/site/demo/index.html` (bundle demo)
- Copy `font-loader.js` → `dist/site/demo/font-loader.js`
- Copy `bundle/` → `dist/site/demo/bundle/` (only needed by demo)
- Continue copying web fonts and block fonts to `dist/site/fonts/`

The demo's `font-loader.js` script src and `./bundle` path both work from the `/demo/` directory.

**Step 2:** Run build and verify

Run: `python3 build_site.py`
Expected: Both pages output correctly, demo at `/demo/`

**Step 3:** Commit

```bash
git add build_site.py
git commit -m "feat: update build to output landing page + demo at /demo"
```
