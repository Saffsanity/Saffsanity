#!/bin/bash
# Make a QR code (PNG + SVG) that opens the resume PDF on GitHub, then check it decodes.
#
#   scripts/make_qr.sh [url] [output_dir]
#
# Uses the GitHub file page because raw.githubusercontent.com serves PDFs as
# application/octet-stream, which makes phones download instead of display.
# Needs qrencode (brew install qrencode); the check uses macOS's built-in QR detector.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
URL="${1:-https://github.com/Saffsanity/Saffsanity/blob/main/Saffer%20Resume.pdf}"
OUT="${2:-$here/..}"

qrencode -l M -m 4 -s 20 -o "$OUT/Saffer Resume QR.png" "$URL"
qrencode -l M -m 4 -t SVG -o "$OUT/Saffer Resume QR.svg" "$URL"

decoded=$(swift "$here/qr_read.swift" "$OUT/Saffer Resume QR.png")
if [ "$decoded" != "$URL" ]; then
  echo "QR check failed: decoded '$decoded'" >&2
  exit 1
fi
echo "QR OK -> $URL"
