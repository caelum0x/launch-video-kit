#!/usr/bin/env bash
# Build, render and mix: ./render.sh [hook ...]   (default: every folder in hooks/)
# Each hook renders from its own index-<hook>.html, so several hooks can build side by side.
set -uo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-../.venv/bin/python}"; [ -x "$PY" ] || PY=python3
if [ $# -gt 0 ]; then HOOKS=("$@"); else HOOKS=(); for d in hooks/*/; do HOOKS+=("$(basename "$d")"); done; fi
mkdir -p renders
for h in "${HOOKS[@]}"; do
  if "$PY" build.py "$h" > "renders/build-$h.log" 2>&1 &&
     npx -y hyperframes@0.8.77 render -c "index-$h.html" --quality looks --output "renders/$h-picture.mp4" > "renders/render-$h.log" 2>&1 &&
     "$PY" audio.py "$h" > "renders/mix-$h.log" 2>&1; then
    echo "$h ok: film/renders/$h.mp4 ($(ffprobe -v error -show_entries format=duration -of csv=p=0 "renders/$h.mp4") s)"
  else
    echo "$h FAILED: see film/renders/build-$h.log, render-$h.log, mix-$h.log"
  fi
done
