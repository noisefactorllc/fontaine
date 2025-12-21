#!/usr/bin/env python3
"""
fontaine - Font Classifier

Uses OpenAI Vision API to classify font styles by rendering samples.
Updates .style_cache.json with the results.

Copyright © 2025 Noise Factor (https://noisefactor.io/)
MIT License
"""

import json
import base64
import urllib.request
import urllib.error
import io
import os
import time
import sys
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Error: Pillow required. Install with: pip install Pillow")
    sys.exit(1)

# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
DIST_DIR = SCRIPT_DIR / "dist"
CACHE_FILE = SCRIPT_DIR / "style_cache.json"

# Load OpenAI API key
OPENAI_KEY_FILE = SCRIPT_DIR / ".openai"
if OPENAI_KEY_FILE.exists():
    OPENAI_API_KEY = OPENAI_KEY_FILE.read_text().strip()
else:
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Valid style tags
VALID_STYLES = ["sans-serif", "serif", "monospace", "handwritten", "display", "symbols"]

# ============================================================================
# Style cache
# ============================================================================

def load_style_cache() -> dict:
    """Load cached style classifications."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except:
            pass
    return {}

def save_style_cache(cache: dict):
    """Save style cache to disk."""
    CACHE_FILE.write_text(json.dumps(cache, indent=2))
    print(f"Saved cache to {CACHE_FILE}")

# ============================================================================
# OpenAI Vision classification
# ============================================================================

def render_font_sample(font_dir: Path) -> Optional[bytes]:
    """Render a sample image of the font for classification."""
    # Find a font file
    font_file = None
    for ext in ['.ttf', '.otf']:
        files = list(font_dir.rglob(f'*{ext}'))
        # Prefer regular weight
        for f in files:
            name_lower = f.stem.lower()
            if 'regular' in name_lower or 'medium' in name_lower:
                font_file = f
                break
        if not font_file and files:
            font_file = files[0]
        if font_file:
            break
    
    if not font_file:
        return None

    try:
        # Create image
        img = Image.new('RGB', (800, 200), color='white')
        draw = ImageDraw.Draw(img)
        
        # Load font
        try:
            font = ImageFont.truetype(str(font_file), 64)
            small_font = ImageFont.truetype(str(font_file), 32)
        except:
            return None
            
        # Draw text
        draw.text((20, 20), "The quick brown fox", font=font, fill='black')
        draw.text((20, 100), "Jumps over the lazy dog", font=font, fill='black')
        draw.text((20, 140), "abcdefghijklmnopqrstuvwxyz", font=small_font, fill='black')
        
        # Convert to PNG bytes
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        return buffer.getvalue()
        
    except Exception as e:
        print(f"  Error rendering {font_dir.name}: {e}")
        return None

def classify_with_vision(image_bytes: bytes, font_name: str) -> Optional[str]:
    """Use OpenAI Vision API to classify font style."""
    if not OPENAI_API_KEY:
        print("  Skipping Vision API (no key provided)")
        return None
    
    # Encode image
    b64_image = base64.b64encode(image_bytes).decode('utf-8')
    
    prompt = f"""This is a sample of the font "{font_name}". Classify it into exactly ONE of these categories:
- serif: has serifs (small lines/feet at the ends of strokes)
- sans-serif: no serifs, clean geometric or humanist letterforms
- monospace: all characters have equal width (like a typewriter)
- handwritten: looks hand-drawn, script, or cursive
- display: decorative, stylized, meant for headlines not body text
- symbols: icons, emoji, musical notation, or math symbols

Respond with ONLY the category name, nothing else."""

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64_image}",
                            "detail": "low"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 20
    }
    
    try:
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode('utf-8'),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENAI_API_KEY}"
            }
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode())
            style = result['choices'][0]['message']['content'].strip().lower()
            
            # Validate response
            if style in VALID_STYLES:
                return style
            
            # Try to extract valid style from response
            for valid in VALID_STYLES:
                if valid in style:
                    return valid
            
            print(f"  Warning: Invalid style returned for {font_name}: {style}")
            return None
            
    except Exception as e:
        print(f"  Vision API error for {font_name}: {e}")
        return None

def main():
    if not DIST_DIR.exists():
        print(f"Error: {DIST_DIR} not found. Run download_fonts.py first.")
        sys.exit(1)

    # Check if cache exists
    if CACHE_FILE.exists() and "--force" not in sys.argv:
        print(f"Style cache found at {CACHE_FILE}. Skipping classification.")
        print("Use --force to update missing fonts or regenerate cache.")
        return

    if not OPENAI_API_KEY:
        print("Warning: OPENAI_API_KEY not set. Cannot classify new fonts.")
        print("Existing cache will be preserved.")
    
    cache = load_style_cache()
    initial_size = len(cache)
    
    # Process all fonts in dist/
    font_dirs = sorted([d for d in DIST_DIR.iterdir() if d.is_dir() and d.name != "site"])
    
    print(f"Found {len(font_dirs)} fonts. Checking cache...")
    
    changed = False
    for font_dir in font_dirs:
        dir_name = font_dir.name
        
        if dir_name in cache:
            continue
            
        if not OPENAI_API_KEY:
            print(f"  [MISSING] {dir_name} (no API key to classify)")
            continue
            
        print(f"  Classifying {dir_name}...")
        image_bytes = render_font_sample(font_dir)
        if image_bytes:
            style = classify_with_vision(image_bytes, dir_name)
            if style:
                print(f"    -> {style}")
                cache[dir_name] = style
                changed = True
                # Rate limit
                time.sleep(0.5)
            else:
                print(f"    -> Failed to classify (API error or invalid response)")
        else:
            print(f"    -> Failed to render sample")
    
    if changed:
        save_style_cache(cache)
        print(f"Updated cache with {len(cache) - initial_size} new fonts.")
    else:
        print("Cache is up to date.")

if __name__ == "__main__":
    main()
