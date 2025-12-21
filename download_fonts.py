#!/usr/bin/env python3
"""fontaine - Font Downloader

Downloads and unpacks fonts while maintaining provenance.
Idempotent: skips fonts that are already downloaded.
Includes rate limiting and backoff to be respectful to servers.

Fonts are tagged as:
  - core: Classic, reliable, workhorse fonts
  - quirky: Stylish, personality-forward, display-oriented fonts

Copyright © 2025 Noise Factor (https://noisefactor.io/)
MIT License
"""

import os
import sys
import zipfile
import tarfile
import json
import shutil
import urllib.request
import urllib.error
import time
import random
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional

# ============================================================================
# Configuration
# ============================================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
FONTS_DIR = SCRIPT_DIR / "dist"
TEMP_DIR = SCRIPT_DIR / ".temp"

# Rate limiting settings
BASE_DELAY = 2.0  # Base delay between downloads in seconds
MAX_DELAY = 60.0  # Maximum delay for exponential backoff
JITTER = 0.5  # Random jitter factor (0.5 = ±50%)

# Colors for terminal output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    NC = '\033[0m'  # No Color

# Counters
stats = {"downloaded": 0, "skipped": 0, "failed": 0}
last_download_time = 0.0

# ============================================================================
# Rate limiting
# ============================================================================

def rate_limit_delay():
    """Apply rate limiting delay between downloads."""
    global last_download_time
    
    if last_download_time > 0:
        elapsed = time.time() - last_download_time
        # Add jitter to avoid thundering herd
        delay = BASE_DELAY * (1 + random.uniform(-JITTER, JITTER))
        if elapsed < delay:
            sleep_time = delay - elapsed
            log_info(f"Rate limiting: waiting {sleep_time:.1f}s...")
            time.sleep(sleep_time)
    
    last_download_time = time.time()

def exponential_backoff(attempt: int) -> float:
    """Calculate exponential backoff delay."""
    delay = min(BASE_DELAY * (2 ** attempt), MAX_DELAY)
    # Add jitter
    delay *= (1 + random.uniform(-JITTER, JITTER))
    return delay

# ============================================================================
# Logging
# ============================================================================

def log_info(msg: str):
    print(f"{Colors.BLUE}[INFO]{Colors.NC} {msg}")

def log_success(msg: str):
    print(f"{Colors.GREEN}[SUCCESS]{Colors.NC} {msg}")

def log_skip(msg: str):
    print(f"{Colors.CYAN}[SKIP]{Colors.NC} {msg} (already downloaded)")

def log_warning(msg: str):
    print(f"{Colors.YELLOW}[WARNING]{Colors.NC} {msg}")

def log_error(msg: str):
    print(f"{Colors.RED}[ERROR]{Colors.NC} {msg}")

# ============================================================================
# Font checking and provenance
# ============================================================================

def is_font_downloaded(font_dir: Path) -> bool:
    """Check if font is already downloaded (has font files and provenance)."""
    if not font_dir.exists():
        return False
    
    # Check for provenance file
    if not (font_dir / "PROVENANCE.md").exists():
        return False
    
    # Check for at least one font file
    font_extensions = {'.ttf', '.otf', '.woff', '.woff2', '.ttc'}
    for f in font_dir.rglob('*'):
        if f.suffix.lower() in font_extensions:
            return True
    
    return False

def create_provenance(font_name: str, source_url: str, license_type: str, font_dir: Path):
    """Create provenance file for a font."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    content = f"""# Provenance: {font_name}

- **Source**: {source_url}
- **License**: {license_type}
- **Downloaded**: {timestamp}
- **Downloaded by**: 50 Fonts Project (download_fonts.py)

## Notes
This font was downloaded as part of the 50 Fonts Project.
See the LICENSE file in this directory for full license terms.
"""
    (font_dir / "PROVENANCE.md").write_text(content)

# ============================================================================
# Download functions
# ============================================================================

def download_file_with_retry(url: str, dest_path: Path, headers: dict = None, max_retries: int = 3) -> bool:
    """Download a file with retry and exponential backoff."""
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=120) as response:
                with open(dest_path, 'wb') as f:
                    shutil.copyfileobj(response, f)
            return True
        except urllib.error.HTTPError as e:
            if e.code == 429:  # Too Many Requests
                delay = exponential_backoff(attempt + 2)  # Extra backoff for rate limits
                log_warning(f"Rate limited (429), backing off {delay:.1f}s...")
                time.sleep(delay)
            elif e.code >= 500:  # Server error, retry
                delay = exponential_backoff(attempt)
                log_warning(f"Server error ({e.code}), retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                return False
        except Exception as e:
            if attempt < max_retries - 1:
                delay = exponential_backoff(attempt)
                log_warning(f"Download failed, retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                return False
    return False

def get_json_with_retry(url: str, headers: dict = None, max_retries: int = 3) -> Optional[dict]:
    """Fetch JSON from URL with retry."""
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                delay = exponential_backoff(attempt)
                time.sleep(delay)
            else:
                return None
        except Exception:
            if attempt < max_retries - 1:
                delay = exponential_backoff(attempt)
                time.sleep(delay)
    return None

def extract_archive(archive_path: Path, dest_dir: Path):
    """Extract zip or tar archive."""
    if archive_path.suffix == '.zip':
        with zipfile.ZipFile(archive_path, 'r') as zf:
            zf.extractall(dest_dir)
    elif archive_path.suffix in ('.gz', '.xz') or '.tar' in archive_path.name:
        with tarfile.open(archive_path, 'r:*') as tf:
            tf.extractall(dest_dir)

def download_github_release(font_name: str, repo: str, asset_pattern: str, 
                            dir_name: str, license: str = "OFL-1.1") -> bool:
    """Download font from GitHub releases with rate limiting."""
    font_dir = FONTS_DIR / dir_name
    
    # Check if already downloaded
    if is_font_downloaded(font_dir):
        log_skip(font_name)
        stats["skipped"] += 1
        return True
    
    # Apply rate limiting before download
    rate_limit_delay()
    
    log_info(f"Downloading {font_name} from GitHub ({repo})...")
    
    try:
        # Get latest release
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "50-Fonts-Project/1.0"
        }
        
        # Add token if available
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"token {token}"
        
        release = get_json_with_retry(api_url, headers)
        
        if not release:
            log_error(f"Could not fetch release info for {font_name}")
            stats["failed"] += 1
            return False
        
        if "rate limit" in str(release).lower():
            log_error(f"GitHub API rate limit exceeded for {font_name}")
            stats["failed"] += 1
            return False
        
        # Find matching asset
        download_url = None
        for asset in release.get("assets", []):
            name = asset.get("name", "")
            if asset_pattern and asset_pattern in name:
                download_url = asset.get("browser_download_url")
                break
        
        # Fallback: first zip file
        if not download_url:
            for asset in release.get("assets", []):
                name = asset.get("name", "")
                if name.endswith(".zip"):
                    download_url = asset.get("browser_download_url")
                    break
        
        if not download_url:
            log_error(f"No download URL found for {font_name}")
            stats["failed"] += 1
            return False
        
        # Download the file
        filename = download_url.split("/")[-1]
        download_path = TEMP_DIR / filename
        
        dl_headers = {"User-Agent": "50-Fonts-Project/1.0"}
        if not download_file_with_retry(download_url, download_path, dl_headers):
            log_error(f"Failed to download {font_name}")
            stats["failed"] += 1
            return False
        
        # Extract
        font_dir.mkdir(parents=True, exist_ok=True)
        extract_archive(download_path, font_dir)
        download_path.unlink()
        
        create_provenance(font_name, f"https://github.com/{repo}", license, font_dir)
        log_success(f"{font_name} downloaded")
        stats["downloaded"] += 1
        return True
        
    except Exception as e:
        log_error(f"Failed to download {font_name}: {e}")
        stats["failed"] += 1
        return False

def download_from_google_fonts_repo(font_name: str, folder_path: str, 
                                     dir_name: str, license: str = "OFL-1.1") -> bool:
    """Download font directly from google/fonts repo (raw files)."""
    font_dir = FONTS_DIR / dir_name
    
    # Check if already downloaded
    if is_font_downloaded(font_dir):
        log_skip(font_name)
        stats["skipped"] += 1
        return True
    
    # Apply rate limiting
    rate_limit_delay()
    
    log_info(f"Downloading {font_name} from google/fonts repo...")
    
    try:
        # Get directory listing from GitHub API
        api_url = f"https://api.github.com/repos/google/fonts/contents/{folder_path}"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "50-Fonts-Project/1.0"
        }
        
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"token {token}"
        
        contents = get_json_with_retry(api_url, headers)
        
        if not contents:
            log_error(f"Could not list files for {font_name}")
            stats["failed"] += 1
            return False
        
        font_dir.mkdir(parents=True, exist_ok=True)
        downloaded_any = False
        
        for item in contents:
            name = item.get("name", "")
            if name.endswith((".ttf", ".otf", ".woff2", ".txt", ".md")) or name == "OFL.txt":
                download_url = item.get("download_url")
                if download_url:
                    dest_file = font_dir / name
                    dl_headers = {"User-Agent": "50-Fonts-Project/1.0"}
                    if download_file_with_retry(download_url, dest_file, dl_headers):
                        downloaded_any = True
                    time.sleep(0.5)  # Be gentle with rate limits
        
        if downloaded_any:
            create_provenance(font_name, f"https://github.com/google/fonts/tree/main/{folder_path}", license, font_dir)
            log_success(f"{font_name} downloaded")
            stats["downloaded"] += 1
            return True
        else:
            log_error(f"No font files found for {font_name}")
            stats["failed"] += 1
            return False
            
    except Exception as e:
        log_error(f"Failed to download {font_name}: {e}")
        stats["failed"] += 1
        return False

# ============================================================================
# Font definitions - All 50 fonts
# ============================================================================

@dataclass
class FontDef:
    name: str
    dir_name: str
    source: str  # "release" (GitHub releases) or "gfonts" (google/fonts repo)
    repo_or_path: str  # GitHub repo for releases, or folder path in google/fonts
    asset_pattern: str = ""  # Pattern to match in release assets
    license: str = "OFL-1.1"
    tag: str = "core"  # "core" or "quirky"
    style: str = "sans-serif"  # "sans-serif", "serif", "monospace", "handwritten", "display", "symbols"

# Fonts with verified sources
# source: "release" = GitHub releases, "gfonts" = google/fonts repo
# tag: "core" = classic workhorse fonts, "quirky" = stylish/display fonts
# style: "sans-serif", "serif", "monospace", "handwritten", "display", "symbols"
FONTS = [
    # =========================================================================
    # CORE FONTS (1-50) - Classic, reliable, workhorse fonts
    # =========================================================================
    
    # Core Sans-serif (1-25)
    FontDef("Inter", "01-inter", "release", "rsms/inter", "InterVariable", "OFL-1.1", "core", "sans-serif"),
    FontDef("Roboto", "02-roboto", "release", "googlefonts/roboto-2", "", "OFL-1.1", "core", "sans-serif"),
    FontDef("Roboto Condensed", "03-roboto-condensed", "gfonts", "ofl/robotocondensed", "", "OFL-1.1", "core", "sans-serif"),
    FontDef("Roboto Flex", "04-roboto-flex", "release", "googlefonts/roboto-flex", "", "OFL-1.1", "core", "sans-serif"),
    FontDef("Roboto Slab", "05-roboto-slab", "gfonts", "apache/robotoslab", "", "Apache-2.0", "core", "serif"),
    FontDef("Noto Sans", "06-noto-sans", "gfonts", "ofl/notosans", "", "OFL-1.1", "core", "sans-serif"),
    FontDef("Noto Sans Display", "07-noto-sans-display", "gfonts", "ofl/notosansdisplay", "", "OFL-1.1", "core", "sans-serif"),
    FontDef("Noto Sans Mono", "08-noto-sans-mono", "gfonts", "ofl/notosansmono", "", "OFL-1.1", "core", "monospace"),
    FontDef("Noto Sans Symbols", "09-noto-sans-symbols", "gfonts", "ofl/notosanssymbols", "", "OFL-1.1", "core", "symbols"),
    FontDef("Noto Sans Math", "10-noto-sans-math", "gfonts", "ofl/notosansmath", "", "OFL-1.1", "core", "symbols"),
    FontDef("Source Sans 3", "11-source-sans-3", "release", "adobe-fonts/source-sans", "OTF", "OFL-1.1", "core", "sans-serif"),
    FontDef("IBM Plex Sans", "12-ibm-plex-sans", "release", "IBM/plex", "TrueType", "OFL-1.1", "core", "sans-serif"),
    FontDef("Work Sans", "13-work-sans", "gfonts", "ofl/worksans", "", "OFL-1.1", "core", "sans-serif"),
    FontDef("Open Sans", "14-open-sans", "gfonts", "ofl/opensans", "", "OFL-1.1", "core", "sans-serif"),
    FontDef("PT Sans", "15-pt-sans", "gfonts", "ofl/ptsans", "", "OFL-1.1", "core", "sans-serif"),
    FontDef("Fira Sans", "16-fira-sans", "gfonts", "ofl/firasans", "", "OFL-1.1", "core", "sans-serif"),
    FontDef("Cabin", "17-cabin", "gfonts", "ofl/cabin", "", "OFL-1.1", "core", "sans-serif"),
    FontDef("Exo 2", "18-exo-2", "gfonts", "ofl/exo2", "", "OFL-1.1", "core", "sans-serif"),
    FontDef("Karla", "19-karla", "gfonts", "ofl/karla", "", "OFL-1.1", "core", "sans-serif"),
    FontDef("Atkinson Hyperlegible", "20-atkinson-hyperlegible", "gfonts", "ofl/atkinsonhyperlegible", "", "OFL-1.1", "core", "sans-serif"),
    FontDef("Space Grotesk", "21-space-grotesk", "gfonts", "ofl/spacegrotesk", "", "OFL-1.1", "core", "sans-serif"),
    FontDef("Outfit", "22-outfit", "gfonts", "ofl/outfit", "", "OFL-1.1", "core", "sans-serif"),
    FontDef("Lato", "23-lato", "gfonts", "ofl/lato", "", "OFL-1.1", "core", "sans-serif"),
    FontDef("Encode Sans", "24-encode-sans", "gfonts", "ofl/encodesans", "", "OFL-1.1", "core", "sans-serif"),
    FontDef("Red Hat Display", "25-red-hat-display", "gfonts", "ofl/redhatdisplay", "", "OFL-1.1", "core", "sans-serif"),
    
    # Core Serif (26-36)
    FontDef("Noto Serif", "26-noto-serif", "gfonts", "ofl/notoserif", "", "OFL-1.1", "core", "serif"),
    FontDef("Crimson Pro", "27-crimson-pro", "gfonts", "ofl/crimsonpro", "", "OFL-1.1", "core", "serif"),
    FontDef("Source Serif 4", "28-source-serif-4", "release", "adobe-fonts/source-serif", "OTF", "OFL-1.1", "core", "serif"),
    FontDef("Playfair Display", "29-playfair-display", "gfonts", "ofl/playfairdisplay", "", "OFL-1.1", "core", "serif"),
    FontDef("Merriweather", "30-merriweather", "gfonts", "ofl/merriweather", "", "OFL-1.1", "core", "serif"),
    FontDef("EB Garamond", "31-eb-garamond", "gfonts", "ofl/ebgaramond", "", "OFL-1.1", "core", "serif"),
    FontDef("Literata", "32-literata", "gfonts", "ofl/literata", "", "OFL-1.1", "core", "serif"),
    FontDef("Cardo", "33-cardo", "gfonts", "ofl/cardo", "", "OFL-1.1", "core", "serif"),
    FontDef("PT Serif", "34-pt-serif", "gfonts", "ofl/ptserif", "", "OFL-1.1", "core", "serif"),
    FontDef("Lora", "35-lora", "gfonts", "ofl/lora", "", "OFL-1.1", "core", "serif"),
    FontDef("Fraunces", "36-fraunces", "gfonts", "ofl/fraunces", "", "OFL-1.1", "core", "serif"),
    
    # Core Monospace (37-47)
    FontDef("JetBrains Mono", "37-jetbrains-mono", "release", "JetBrains/JetBrainsMono", "", "OFL-1.1", "core", "monospace"),
    FontDef("Fira Code", "38-fira-code", "release", "tonsky/FiraCode", "Fira_Code", "OFL-1.1", "core", "monospace"),
    FontDef("Cascadia Code", "39-cascadia-code", "release", "microsoft/cascadia-code", "CascadiaCode", "OFL-1.1", "core", "monospace"),
    FontDef("Source Code Pro", "40-source-code-pro", "release", "adobe-fonts/source-code-pro", "OTF", "OFL-1.1", "core", "monospace"),
    FontDef("IBM Plex Mono", "41-ibm-plex-mono", "gfonts", "ofl/ibmplexmono", "", "OFL-1.1", "core", "monospace"),
    FontDef("Victor Mono", "42-victor-mono", "gfonts", "ofl/victormono", "", "OFL-1.1", "core", "monospace"),
    FontDef("Courier Prime", "43-courier-prime", "gfonts", "ofl/courierprime", "", "OFL-1.1", "core", "monospace"),
    FontDef("Hack", "44-hack", "release", "source-foundry/Hack", "ttf", "MIT", "core", "monospace"),
    FontDef("Inconsolata", "45-inconsolata", "gfonts", "ofl/inconsolata", "", "OFL-1.1", "core", "monospace"),
    FontDef("Recursive", "46-recursive", "release", "arrowtype/recursive", "Recursive", "OFL-1.1", "core", "monospace"),
    FontDef("Monaspace", "47-monaspace", "release", "githubnext/monaspace", "monaspace", "OFL-1.1", "core", "monospace"),
    
    # Core Display / Special (48-50)
    FontDef("Noto Color Emoji", "48-noto-color-emoji", "gfonts", "ofl/notocoloremoji", "", "OFL-1.1", "core", "symbols"),
    FontDef("Noto Music", "49-noto-music", "gfonts", "ofl/notomusic", "", "OFL-1.1", "core", "symbols"),
    FontDef("Barlow", "50-barlow", "gfonts", "ofl/barlow", "", "OFL-1.1", "core", "sans-serif"),
    
    # =========================================================================
    # QUIRKY FONTS (51-100) - Stylish, personality-forward, display fonts
    # =========================================================================
    
    # Quirky Display / Sans (51-75) - geometric, rounded, futuristic sans-serifs
    FontDef("Raleway", "51-raleway", "gfonts", "ofl/raleway", "", "OFL-1.1", "quirky", "sans-serif"),
    FontDef("Lexend", "52-lexend", "gfonts", "ofl/lexend", "", "OFL-1.1", "quirky", "sans-serif"),
    FontDef("Rubik", "53-rubik", "gfonts", "ofl/rubik", "", "OFL-1.1", "quirky", "sans-serif"),
    FontDef("Signika", "54-signika", "gfonts", "ofl/signika", "", "OFL-1.1", "quirky", "sans-serif"),
    FontDef("Poppins", "55-poppins", "gfonts", "ofl/poppins", "", "OFL-1.1", "quirky", "sans-serif"),
    FontDef("Quicksand", "56-quicksand", "gfonts", "ofl/quicksand", "", "OFL-1.1", "quirky", "sans-serif"),
    FontDef("Nunito", "57-nunito", "gfonts", "ofl/nunito", "", "OFL-1.1", "quirky", "sans-serif"),
    FontDef("Comfortaa", "58-comfortaa", "gfonts", "ofl/comfortaa", "", "OFL-1.1", "quirky", "sans-serif"),
    FontDef("Baloo 2", "59-baloo-2", "gfonts", "ofl/baloo2", "", "OFL-1.1", "quirky", "sans-serif"),
    FontDef("Asap", "60-asap", "gfonts", "ofl/asap", "", "OFL-1.1", "quirky", "sans-serif"),
    FontDef("Jaldi", "61-jaldi", "gfonts", "ofl/jaldi", "", "OFL-1.1", "quirky", "sans-serif"),
    FontDef("Josefin Sans", "62-josefin-sans", "gfonts", "ofl/josefinsans", "", "OFL-1.1", "quirky", "sans-serif"),
    FontDef("Jost", "63-jost", "gfonts", "ofl/jost", "", "OFL-1.1", "quirky", "sans-serif"),
    FontDef("League Spartan", "64-league-spartan", "gfonts", "ofl/leaguespartan", "", "OFL-1.1", "quirky", "sans-serif"),
    FontDef("Chivo", "65-chivo", "gfonts", "ofl/chivo", "", "OFL-1.1", "quirky", "sans-serif"),
    FontDef("Syne", "66-syne", "gfonts", "ofl/syne", "", "OFL-1.1", "quirky", "sans-serif"),
    FontDef("Workbench", "67-workbench", "gfonts", "ofl/workbench", "", "OFL-1.1", "quirky", "display"),
    FontDef("Bungee Inline", "68-bungee-inline", "gfonts", "ofl/bungeeinline", "", "OFL-1.1", "quirky", "display"),
    FontDef("Orbitron", "69-orbitron", "gfonts", "ofl/orbitron", "", "OFL-1.1", "quirky", "display"),
    FontDef("Audiowide", "70-audiowide", "gfonts", "ofl/audiowide", "", "OFL-1.1", "quirky", "display"),
    FontDef("Bungee", "71-bungee", "gfonts", "ofl/bungee", "", "OFL-1.1", "quirky", "display"),
    FontDef("Rama Gothic", "72-ramaraja", "gfonts", "ofl/ramaraja", "", "OFL-1.1", "quirky", "display"),
    FontDef("Tomorrow", "73-tomorrow", "gfonts", "ofl/tomorrow", "", "OFL-1.1", "quirky", "sans-serif"),
    FontDef("Varta", "74-varta", "gfonts", "ofl/varta", "", "OFL-1.1", "quirky", "sans-serif"),
    FontDef("Yanone Kaffeesatz", "75-yanone-kaffeesatz", "gfonts", "ofl/yanonekaffeesatz", "", "OFL-1.1", "quirky", "sans-serif"),
    
    # Quirky Serif / Unusual Serif (76-90)
    FontDef("Cormorant Garamond", "76-cormorant-garamond", "gfonts", "ofl/cormorantgaramond", "", "OFL-1.1", "quirky", "serif"),
    FontDef("Cormorant SC", "77-cormorant-sc", "gfonts", "ofl/cormorantsc", "", "OFL-1.1", "quirky", "serif"),
    FontDef("Cormorant Infant", "78-cormorant-infant", "gfonts", "ofl/cormorantinfant", "", "OFL-1.1", "quirky", "serif"),
    FontDef("Cormorant Upright", "79-cormorant-upright", "gfonts", "ofl/cormorantupright", "", "OFL-1.1", "quirky", "serif"),
    FontDef("Bitter", "80-bitter", "gfonts", "ofl/bitter", "", "OFL-1.1", "quirky", "serif"),
    FontDef("Cormorant", "81-cormorant", "gfonts", "ofl/cormorant", "", "OFL-1.1", "quirky", "serif"),
    FontDef("Zilla Slab", "82-zilla-slab", "gfonts", "ofl/zillaslab", "", "OFL-1.1", "quirky", "serif"),
    FontDef("Arvo", "83-arvo", "gfonts", "ofl/arvo", "", "OFL-1.1", "quirky", "serif"),
    FontDef("Newsreader", "84-newsreader", "gfonts", "ofl/newsreader", "", "OFL-1.1", "quirky", "serif"),
    FontDef("Alice", "85-alice", "gfonts", "ofl/alice", "", "OFL-1.1", "quirky", "serif"),
    FontDef("Radley", "86-radley", "gfonts", "ofl/radley", "", "OFL-1.1", "quirky", "serif"),
    FontDef("Fanwood Text", "87-fanwood-text", "gfonts", "ofl/fanwoodtext", "", "OFL-1.1", "quirky", "serif"),
    FontDef("Alegreya", "88-alegreya", "gfonts", "ofl/alegreya", "", "OFL-1.1", "quirky", "serif"),
    FontDef("Alegreya SC", "89-alegreya-sc", "gfonts", "ofl/alegreyasc", "", "OFL-1.1", "quirky", "serif"),
    FontDef("Playfair Display SC", "90-playfair-display-sc", "gfonts", "ofl/playfairdisplaysc", "", "OFL-1.1", "quirky", "serif"),
    
    # Quirky Handwritten / Script / Humanist (91-100)
    FontDef("Caveat", "91-caveat", "gfonts", "ofl/caveat", "", "OFL-1.1", "quirky", "handwritten"),
    FontDef("Amatic SC", "92-amatic-sc", "gfonts", "ofl/amaticsc", "", "OFL-1.1", "quirky", "handwritten"),
    FontDef("Dancing Script", "93-dancing-script", "gfonts", "ofl/dancingscript", "", "OFL-1.1", "quirky", "handwritten"),
    FontDef("Yellowtail", "94-yellowtail", "gfonts", "apache/yellowtail", "", "Apache-2.0", "quirky", "handwritten"),
    FontDef("Pacifico", "95-pacifico", "gfonts", "ofl/pacifico", "", "OFL-1.1", "quirky", "handwritten"),
    FontDef("Sacramento", "96-sacramento", "gfonts", "ofl/sacramento", "", "OFL-1.1", "quirky", "handwritten"),
    FontDef("Satisfy", "97-satisfy", "gfonts", "apache/satisfy", "", "Apache-2.0", "quirky", "handwritten"),
    FontDef("Indie Flower", "98-indie-flower", "gfonts", "ofl/indieflower", "", "OFL-1.1", "quirky", "handwritten"),
    FontDef("Gloria Hallelujah", "99-gloria-hallelujah", "gfonts", "ofl/gloriahallelujah", "", "OFL-1.1", "quirky", "handwritten"),
    FontDef("Shadows Into Light", "100-shadows-into-light", "gfonts", "ofl/shadowsintolight", "", "OFL-1.1", "quirky", "handwritten"),
]

# ============================================================================
# Main
# ============================================================================

def print_banner():
    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║                      f o n t a i n e                       ║")
    print("║              Font Downloader & Provenance Tracker          ║")
    print("║                                                            ║")
    print("║  100 curated fonts | core (1-50) | quirky (51-100)         ║")
    print("║                     https://noisefactor.io/                ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    print("Downloads are idempotent - existing fonts will be skipped.")
    print()

def download_all():
    """Download all fonts."""
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    
    categories = [
        # Core fonts (1-50)
        ("CORE: SANS-SERIF (1-25)", FONTS[0:25]),
        ("CORE: SERIF (26-36)", FONTS[25:36]),
        ("CORE: MONOSPACE (37-47)", FONTS[36:47]),
        ("CORE: DISPLAY / SPECIAL (48-50)", FONTS[47:50]),
        # Quirky fonts (51-100)
        ("QUIRKY: DISPLAY / SANS (51-75)", FONTS[50:75]),
        ("QUIRKY: SERIF / UNUSUAL (76-90)", FONTS[75:90]),
        ("QUIRKY: HANDWRITTEN / SCRIPT (91-100)", FONTS[90:100]),
    ]
    
    for category_name, fonts in categories:
        print()
        print("=" * 50)
        print(f"  {category_name}")
        print("=" * 50)
        print()
        
        for font in fonts:
            if font.source == "release":
                download_github_release(font.name, font.repo_or_path, font.asset_pattern, 
                                        font.dir_name, font.license)
            else:  # gfonts
                download_from_google_fonts_repo(font.name, font.repo_or_path,
                                                 font.dir_name, font.license)

def main():
    print_banner()
    
    # Handle --force flag
    if "--force" in sys.argv:
        log_warning("Force mode: removing existing fonts...")
        import shutil
        if FONTS_DIR.exists():
            shutil.rmtree(FONTS_DIR)
    
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python download_fonts.py [options]")
        print()
        print("Options:")
        print("  --force    Re-download all fonts (ignore existing)")
        print("  --help     Show this help")
        return
    
    download_all()
    
    # Cleanup temp dir
    if TEMP_DIR.exists():
        import shutil
        shutil.rmtree(TEMP_DIR)
    
    print()
    print("=" * 42)
    print("  DOWNLOAD COMPLETE")
    print("=" * 42)
    print()
    print(f"Downloaded: {Colors.GREEN}{stats['downloaded']}{Colors.NC}")
    print(f"Skipped:    {Colors.CYAN}{stats['skipped']}{Colors.NC}")
    print(f"Failed:     {Colors.RED}{stats['failed']}{Colors.NC}")
    print()
    print(f"Fonts saved to: {FONTS_DIR}")
    print()
    
    if stats["failed"] > 0:
        log_warning("Some fonts failed. Run again to retry failed downloads.")
        sys.exit(1)

if __name__ == "__main__":
    main()
