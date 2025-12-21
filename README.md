# fontaine

**A curated collection of 100 freely distributable web fonts and an async, cache-aware bundler for JavaScript apps.**

By [Noise Factor](https://noisefactor.io/)

[Live Demo](https://fonts.noisedeck.app/)

## Fonts

**50 Core Fonts** (1-50) — Classic, reliable, workhorse fonts
- Sans-serif: Inter, Roboto, Noto Sans, Source Sans, IBM Plex Sans, Open Sans, Lato...
- Serif: Noto Serif, Crimson Pro, Playfair Display, Merriweather, EB Garamond, Lora...
- Monospace: JetBrains Mono, Fira Code, Cascadia Code, Source Code Pro, Hack, Inconsolata...
- Special: Noto Color Emoji, Noto Music, Barlow

**50 Quirky Fonts** (51-100) — Stylish, personality-forward, display fonts
- Display/Sans: Raleway, Poppins, Quicksand, Nunito, Comfortaa, Orbitron, Bungee...
- Unusual Serif: Cormorant, Bitter, Zilla Slab, Arvo, Alegreya...
- Handwritten/Script: Caveat, Dancing Script, Pacifico, Satisfy, Indie Flower...

All fonts are OFL-1.1, Apache 2.0, or MIT licensed.

## Quick Start

### 1. Download fonts
```bash
python3 download_fonts.py
```

### 2. Build bundle
```bash
python3 build_bundle.py
```

### 3. Use in your app
```html
<script src="font-loader.js"></script>
<script>
  const loader = new FontLoader();
  
  await loader.load('./bundle', {
    onProgress: (percent, message) => {
      console.log(`${percent.toFixed(0)}% - ${message}`);
    }
  });
  
  // Get fonts by tag
  const quirkyFonts = loader.getFontsByTag('quirky');
  const monoFonts = loader.getFontsByTag('monospace');
  const coreFonts = loader.getFontsByTag('core');
  
  // Register a font for CSS use
  await loader.registerFont('37-jetbrains-mono', 'JetBrains Mono');
  
  // Now use in CSS
  document.body.style.fontFamily = "'JetBrains Mono', monospace";
</script>
```

## Features

- **Async download** — Non-blocking with progress callbacks
- **IndexedDB caching** — Downloads only once, persists across sessions
- **Version management** — Updates only when bundle version changes
- **Zero dependencies** — Vanilla JS, JSZip loaded dynamically when needed
- **WOFF2 optimized** — Compressed font format for fast loading
- **Tag-based filtering** — `core`, `quirky`, `monospace`, `serif`, `handwritten`, etc.
- **AI Classification** — (Entirely optional) Uses OpenAI Vision to automatically tag fonts by style
- **Dynamic @font-face** — Register fonts on-demand

## Configuration

**Note:** This step is only required if you are modifying the curated font collection.

Font metadata in the wild is often inconsistent or incorrect. To ensure reliable tagging, we use an AI helper script to visually classify fonts. These generated tags are included in the repo.

To enable AI-powered classification:

1. Set your OpenAI API key:
   ```bash
   export OPENAI_API_KEY="sk-..."
   # or
   echo "sk-..." > .openai
   ```

2. Run the classifier:
   ```bash
   python3 classify_fonts.py
   ```

This generates a `style_cache.json` file. You can commit this file to source control so others don't need to run the classification.

### Manual Classification

If you prefer not to use AI, you can create `style_cache.json` manually (see included example).

Valid categories are: `sans-serif`, `serif`, `monospace`, `handwritten`, `display`, `symbols`.

## Files

| File | Description |
|------|-------------|
| `run_demo.sh` | One-click demo script (setup, build, serve) |
| `download_fonts.py` | Downloads fonts from source (GitHub, Google Fonts) |
| `classify_fonts.py` | (Optional) Classifies fonts using OpenAI Vision |
| `build_bundle.py` | Builds distributable bundle with WOFF2 conversion |
| `build_site.py` | Builds the static site for deployment |
| `font-loader.js` | Vanilla JS font loader library |
| `style_cache.json` | Cached font style classifications |
| `requirements.txt` | Python dependencies |
| `example.html` | Demo app with progress bar and font browser |
| `bundle/manifest.json` | Bundle metadata (version, size, hash) |
| `bundle/fonts.json` | Full catalog with tags and file listings |
| `bundle/fonts.zip` | Compressed WOFF2 font files |

## API Reference

### `FontLoader`

```javascript
const loader = new FontLoader(options);
```

**Options:**
- `dbName` — IndexedDB database name (default: `'fontaine'`)

### Methods

#### `load(bundlePath, options)`
Load fonts from bundle directory.

```javascript
await loader.load('./bundle', {
  force: false,           // Force re-download even if cached
  onProgress: (pct, msg) => {}  // Progress callback
});
```

Returns `true` if fonts were downloaded, `false` if using cache.

#### `getFontsByTag(tag)`
Get fonts with a specific tag.

```javascript
loader.getFontsByTag('quirky');     // Stylish/display fonts
loader.getFontsByTag('core');       // Classic workhorse fonts
loader.getFontsByTag('monospace');  // Coding fonts
loader.getFontsByTag('handwritten'); // Script/handwritten fonts
```

#### `getFontsByCategory(category)`
Get fonts by category.

```javascript
loader.getFontsByCategory('sans-serif');
loader.getFontsByCategory('serif');
loader.getFontsByCategory('monospace');
```

#### `getFont(fontId)`
Get a specific font by ID.

```javascript
const inter = loader.getFont('01-inter');
// { id, name, category, style, tags, license, files }
```

#### `searchFonts(query)`
Search fonts by name.

```javascript
loader.searchFonts('roboto');
```

#### `registerFont(fontId, fontFamily, options)`
Register font with CSS @font-face.

```javascript
await loader.registerFont('01-inter', 'Inter', {
  weight: 'normal',
  style: 'normal',
  display: 'swap'
});
```

#### `getFontUrl(fontId, filename)`
Get blob URL for a font file.

```javascript
const url = await loader.getFontUrl('01-inter');
```

#### `clearCache()`
Clear all cached fonts.

```javascript
await loader.clearCache();
```

## Tags

| Tag | Description |
|-----|-------------|
| `core` | Classic, reliable fonts (1-50) |
| `quirky` | Stylish, personality-forward fonts (51-100) |
| `sans-serif` | Sans-serif fonts |
| `serif` | Serif fonts |
| `monospace` | Monospace/coding fonts |
| `handwritten` | Script and handwritten fonts |
| `display` | Display/headline fonts |
| `variable` | Variable fonts |
| `condensed` | Condensed width fonts |

## Demo

Run the demo script to set up the environment, build the project, and serve the site:

```bash
./run_demo.sh
```

## License

MIT License

Copyright © 2025 Noise Factor

The fontaine loader and build tools are MIT licensed.

Individual fonts retain their original licenses (OFL-1.1, Apache-2.0, or MIT).
See each font's LICENSE file in the bundle for details.
