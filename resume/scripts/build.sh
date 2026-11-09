#!/bin/bash
# Back up the .tex (optional), render the PDF, and write a diff for review.
#
#   scripts/build.sh            render NoahSafferResume.pdf
#   scripts/build.sh backup     copy NoahSafferResume.tex to NoahSafferResume_<last-edited-date>.tex first
#   scripts/build.sh diff FILE  write a unified diff of FILE -> NoahSafferResume.tex into history/
#
# Needs tectonic (brew install tectonic). deedy-resume.cls and fonts/ must sit next to the .tex.
set -euo pipefail
cd "$(dirname "$0")/.."
TEX=NoahSafferResume.tex

case "${1:-}" in
  backup)
    mkdir -p history
    d=$(stat -f %Sm -t %Y-%m-%d "$TEX" 2>/dev/null || date -r "$TEX" +%Y-%m-%d)
    out="history/NoahSafferResume_$d.tex"; n=2
    while [ -e "$out" ]; do out="history/NoahSafferResume_${d}_$n.tex"; n=$((n + 1)); done
    cp -p "$TEX" "$out"
    echo "$out"
    ;;
  diff)
    mkdir -p history
    base=$(basename "${2:?usage: build.sh diff BACKUP.tex}" .tex)
    out="history/resume-changes-${base#NoahSafferResume_}.diff"
    diff -u "$2" "$TEX" > "$out" || true
    echo "$out"
    ;;
  *)
    tectonic "$TEX"
    ;;
esac
