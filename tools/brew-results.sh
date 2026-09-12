#!/usr/bin/env bash
# One line per brewery-rule run: the per-block results, or how far along it is.
cd "$(dirname "$0")/.."
for f in runs/brew2.log runs/brew-cap-only.log runs/brew-hold-only.log runs/brew-min{25,45,35}.log runs/plan-nosell-only.log runs/plan-pair.log runs/need-alone.log runs/need-plan.log runs/setup-alone.log runs/setup-plan.log runs/rail-hold-brew.log runs/rail-cap-hold-brew.log; do
  [ -f "$f" ] || { printf "  %-22s queued\n" "$(basename $f .log)"; continue; }
  r=$(grep -h "^RESULT" "$f" | sed -E 's/RESULT seed [0-9]+: //; s/ \(([-0-9.]+) sigma\)/ (\1σ)/' | paste -sd'|' - | sed 's/|/  |  /g')
  if [ -n "$r" ] && [ "$(grep -c ^RESULT "$f")" -eq 3 ]; then printf "  %-22s %s\n" "$(basename $f .log)" "$r"
  else printf "  %-22s %s   %s\n" "$(basename $f .log)" "$(tools/watch-progress.sh "$f" | head -1 | sed 's/^ *//')" "${r:+so far: $r}"; fi
done
