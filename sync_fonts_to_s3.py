#!/usr/bin/env python3
"""sync_fonts_to_s3.py - Sync web fonts to S3 for individual font hosting

Uploads woff2 fonts from .build/*/ to S3, stripping the NN- prefix from
directory names. Idempotent: only uploads changed files.

Usage:
    python sync_fonts_to_s3.py [--dry-run]

Prerequisites:
    - AWS CLI configured with appropriate credentials
    - Fonts built via build_bundle.py (creates .build/ with woff2 files)

Copyright © 2025 Noise Factor (https://noisefactor.io/)
MIT License
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Configuration
S3_BUCKET = "s3://noisedeck-fonts"
S3_PREFIX = "fonts"
SCRIPT_DIR = Path(__file__).parent.resolve()
BUILD_DIR = SCRIPT_DIR / ".build"

# Colors for terminal output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'


def log_info(msg: str):
    print(f"{Colors.BLUE}[INFO]{Colors.NC} {msg}")


def log_success(msg: str):
    print(f"{Colors.GREEN}[DONE]{Colors.NC} {msg}")


def log_skip(msg: str):
    print(f"{Colors.YELLOW}[SKIP]{Colors.NC} {msg}")


def log_error(msg: str):
    print(f"{Colors.RED}[ERROR]{Colors.NC} {msg}")


def check_aws_cli():
    """Verify AWS CLI is available."""
    try:
        subprocess.run(["aws", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def strip_number_prefix(dir_name: str) -> str:
    """Strip NN- prefix from directory name."""
    return re.sub(r'^\d{2,3}-', '', dir_name)


def sync_font_to_s3(font_dir: Path, font_name: str, dry_run: bool) -> bool:
    """Sync a font directory to S3."""
    s3_path = f"{S3_BUCKET}/{S3_PREFIX}/{font_name}/"
    
    dry_run_flag = ["--dryrun"] if dry_run else []
    
    # Sync woff2 files with appropriate headers
    cmd = [
        "aws", "s3", "sync",
        str(font_dir), s3_path,
        "--size-only",
        "--content-type", "font/woff2",
        "--cache-control", "public, max-age=31536000, immutable",
        *dry_run_flag
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        log_error(f"Failed to sync {font_name}: {e.stderr.decode()}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Sync web fonts to S3 for individual font hosting"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be uploaded without actually uploading"
    )
    args = parser.parse_args()
    
    if args.dry_run:
        print(f"{Colors.YELLOW}[DRY RUN]{Colors.NC} No files will be uploaded\n")
    
    # Check prerequisites
    if not check_aws_cli():
        log_error("AWS CLI not found. Install with: brew install awscli")
        sys.exit(1)
    
    if not BUILD_DIR.exists():
        log_error(".build/ directory not found. Run build_bundle.py first.")
        sys.exit(1)
    
    log_info(f"Syncing fonts to {S3_BUCKET}/{S3_PREFIX}/\n")
    
    font_count = 0
    failed_count = 0
    
    # Iterate over font directories
    for font_dir in sorted(BUILD_DIR.iterdir()):
        if not font_dir.is_dir():
            continue
        
        # Check for woff2 files
        woff2_files = list(font_dir.glob("*.woff2"))
        if not woff2_files:
            log_skip(f"{font_dir.name} - no woff2 files")
            continue
        
        # Strip NN- prefix from directory name
        font_name = strip_number_prefix(font_dir.name)
        
        log_info(f"Syncing {font_name}/")
        
        if sync_font_to_s3(font_dir, font_name, args.dry_run):
            font_count += 1
        else:
            failed_count += 1
    
    print()
    log_success(f"Synced {font_count} fonts to {S3_BUCKET}/{S3_PREFIX}/")
    
    if failed_count > 0:
        log_error(f"{failed_count} fonts failed to sync")
        sys.exit(1)
    
    if args.dry_run:
        print(f"{Colors.YELLOW}[NOTE]{Colors.NC} This was a dry run. Remove --dry-run to upload files.")


if __name__ == "__main__":
    main()
