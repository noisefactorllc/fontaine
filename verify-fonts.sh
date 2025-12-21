#!/bin/bash

# Verify downloaded fonts
# Checks that all 50 fonts have been downloaded and have provenance files

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FONTS_DIR="$SCRIPT_DIR/dist"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

EXPECTED_FONTS=(
    "01-inter"
    "02-roboto"
    "03-roboto-condensed"
    "04-roboto-flex"
    "05-roboto-slab"
    "06-noto-sans"
    "07-noto-sans-display"
    "08-noto-sans-mono"
    "09-noto-sans-symbols"
    "10-noto-sans-math"
    "11-source-sans-3"
    "12-ibm-plex-sans"
    "13-work-sans"
    "14-open-sans"
    "15-pt-sans"
    "16-fira-sans"
    "17-cabin"
    "18-exo-2"
    "19-karla"
    "20-atkinson-hyperlegible"
    "21-space-grotesk"
    "22-outfit"
    "23-lato"
    "24-encode-sans"
    "25-red-hat-display"
    "26-noto-serif"
    "27-crimson-pro"
    "28-source-serif-4"
    "29-playfair-display"
    "30-merriweather"
    "31-eb-garamond"
    "32-literata"
    "33-cardo"
    "34-pt-serif"
    "35-lora"
    "36-fraunces"
    "37-jetbrains-mono"
    "38-fira-code"
    "39-cascadia-code"
    "40-source-code-pro"
    "41-ibm-plex-mono"
    "42-victor-mono"
    "43-courier-prime"
    "44-hack"
    "45-iosevka"
    "46-recursive"
    "47-monaspace"
    "48-noto-color-emoji"
    "49-noto-music"
    "50-barlow"
)

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║              50 FONTS - VERIFICATION REPORT                ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

total=0
found=0
missing=0
no_fonts=0
no_provenance=0

for font_dir in "${EXPECTED_FONTS[@]}"; do
    total=$((total + 1))
    font_path="$FONTS_DIR/$font_dir"
    
    if [ -d "$font_path" ]; then
        # Check for font files
        font_count=$(find "$font_path" -type f \( -name "*.ttf" -o -name "*.otf" -o -name "*.woff" -o -name "*.woff2" \) 2>/dev/null | wc -l)
        
        # Check for provenance
        has_provenance=0
        if [ -f "$font_path/PROVENANCE.md" ]; then
            has_provenance=1
        fi
        
        if [ "$font_count" -gt 0 ] && [ "$has_provenance" -eq 1 ]; then
            echo -e "${GREEN}✓${NC} $font_dir - $font_count font file(s)"
            found=$((found + 1))
        elif [ "$font_count" -eq 0 ]; then
            echo -e "${YELLOW}⚠${NC} $font_dir - No font files found"
            no_fonts=$((no_fonts + 1))
        elif [ "$has_provenance" -eq 0 ]; then
            echo -e "${YELLOW}⚠${NC} $font_dir - Missing PROVENANCE.md"
            no_provenance=$((no_provenance + 1))
        fi
    else
        echo -e "${RED}✗${NC} $font_dir - Not downloaded"
        missing=$((missing + 1))
    fi
done

echo ""
echo "=========================================="
echo "  SUMMARY"
echo "=========================================="
echo ""
echo "Total expected:     $total"
echo -e "Complete:           ${GREEN}$found${NC}"
echo -e "Missing:            ${RED}$missing${NC}"
echo -e "No font files:      ${YELLOW}$no_fonts${NC}"
echo -e "No provenance:      ${YELLOW}$no_provenance${NC}"
echo ""

if [ "$found" -eq "$total" ]; then
    echo -e "${GREEN}All 50 fonts verified successfully!${NC}"
    exit 0
else
    echo -e "${YELLOW}Some fonts are missing or incomplete.${NC}"
    echo "Run ./download-fonts.sh to download missing fonts."
    exit 1
fi
