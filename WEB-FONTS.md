# Fontaine Web Fonts

Fontaine fonts are hosted at `fonts.noisefactor.io` for use in Noise Factor web applications.

## Updating Fonts in S3

When fonts are added, removed, or updated:

```bash
# 1. Download fonts locally
python download_fonts.py

# 2. Build woff2 files
python build_bundle.py

# 3. Preview what will be synced (optional)
python sync_fonts_to_s3.py --dry-run

# 4. Push fonts to S3
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

## CORS

CORS is configured to allow requests from Noise Factor applications. If you're adding a new domain, update the S3 bucket CORS configuration.

## Font Catalog

See [bundle/fonts.json](bundle/fonts.json) for the complete list of available fonts with metadata.
