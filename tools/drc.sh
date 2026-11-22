#!/usr/bin/env bash
# Regenerate the board with KiCad's Python, run DRC and print a summary.
#   tools/drc.sh [details]
set -euo pipefail
cd "$(dirname "$0")/.."
KPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
OUT=${DRC_OUT:-board/check/drc.json}
mkdir -p "$(dirname "$OUT")"
"$KPY" -I tools/gen_pcb.py 2>&1 | grep -v "wxApp\|stdpbase"; test "${PIPESTATUS[0]}" -eq 0
(cd board && kicad-cli pcb drc --severity-all --all-track-errors --format json --units mm --output "../$OUT" mnhttn48-unibody.kicad_pcb 2>&1 | grep -v Fontconfig | tail -1)
jq -r '.violations | group_by(.type) | map("\(length) \(.[0].type)") | .[]' "$OUT" | sort -rn
echo "unconnected: $(jq '.unconnected_items | length' "$OUT")"
matrix=$(python3 -I tools/check_matrix.py) || { echo "$matrix"; exit 1; }
echo "matrix: $(echo "$matrix" | tail -1)"
if [ "${1:-}" = "details" ]; then
  jq -r '.violations[] | "\(.type): \(.description) @ \(.items | map("\(.description) (\(.pos.x|tostring|.[0:6]),\(.pos.y|tostring|.[0:6]))") | join(" | "))"' "$OUT" | cut -c1-240
  echo "--- unconnected"; jq -r '.unconnected_items[] | .items | map(.description) | join(" <-> ")' "$OUT" | cut -c1-200
fi
