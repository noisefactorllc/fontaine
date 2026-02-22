# Fontaine Web Fonts

Fontaine fonts are hosted at `fonts.noisefactor.io` for use in Noise Factor web applications.

## Updating Fonts in S3

When fonts are added, removed, or updated:

```bash
# 1. Download fonts locally
python download_fonts.py

# 2. Build woff2 files
python build_bundle.py

# 3. Build block fonts (zero-CLS placeholders)
python build_block_fonts.py

# 4. Preview what will be synced (optional)
python sync_fonts_to_s3.py --dry-run

# 5. Push fonts to S3
python sync_fonts_to_s3.py
```

The sync is idempotent—only changed files are uploaded. Fonts are cached aggressively (1 year).

## Using Fonts in Your Application

### Quick Start

Define `@font-face` rules in your CSS:

```css
@font-face {
  font-family: 'Inter';
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url('https://fonts.noisefactor.io/fonts/inter/Inter-Regular.woff2') format('woff2');
}

@font-face {
  font-family: 'Inter';
  font-style: normal;
  font-weight: 700;
  font-display: swap;
  src: url('https://fonts.noisefactor.io/fonts/inter/Inter-Bold.woff2') format('woff2');
}

body {
  font-family: 'Inter', sans-serif;
}
```

### Available Fonts

Fonts follow the pattern:
```
https://fonts.noisefactor.io/fonts/{fontname}/{Filename}.woff2
```

Examples:
- `https://fonts.noisefactor.io/fonts/inter/Inter-Regular.woff2`
- `https://fonts.noisefactor.io/fonts/roboto/Roboto-Regular.woff2`
- `https://fonts.noisefactor.io/fonts/jetbrains-mono/JetBrainsMono-Regular.woff2`

Font directory names use lowercase with hyphens (no numbers).

### Preloading Critical Fonts

For performance, preload fonts used above the fold:

```html
<link rel="preload" 
      href="https://fonts.noisefactor.io/fonts/inter/Inter-Regular.woff2" 
      as="font" 
      type="font/woff2" 
      crossorigin>
```

### Variable Fonts

Many fonts include variable font versions (when available):

```html
<link rel="preload" 
      href="https://fonts.noisefactor.io/fonts/inter/InterVariable.woff2" 
      as="font" 
      type="font/woff2" 
      crossorigin>
```

## Block Fonts (Zero-CLS Loading)

Block fonts are metric-matched placeholder fonts where every glyph is a solid rectangle.
They load near-instantly (~3-15KB) and prevent layout shift when the real font loads.

### Using Block Fonts

1. Add a block font `@font-face` rule:

```css
@font-face {
  font-family: 'Inter Block';
  src: url('https://fonts.noisefactor.io/fonts/inter/Inter-Block.woff2') format('woff2');
  font-weight: 400;
  font-style: normal;
}
```

2. Add the block font to your fallback chain:

```css
body {
  font-family: 'Inter', 'Inter Block', sans-serif;
}
```

Block fonts follow the naming pattern: `{FontName}-Block.woff2`

### Building Block Fonts

```bash
python build_block_fonts.py
```

This reads fonts from `.build/` and generates block variants in `.build-block/`.
They are synced to S3 alongside regular fonts by `sync_fonts_to_s3.py`.

## CORS

CORS is configured to allow requests from Noise Factor applications. If you're adding a new domain, update the S3 bucket CORS configuration.

## Font Catalog

See [bundle/fonts.json](bundle/fonts.json) for the complete list of available fonts with metadata.
