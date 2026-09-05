#!/usr/bin/env bash
# Watch any run that emits `PROGRESS done=N total=M t=SECONDS` lines.
#
#   tools/watch-progress.sh runs/standings.log            # one shot
#   tools/watch-progress.sh runs/standings.log --watch    # refresh every 5s
#
# The ETA is derived from the measured rate of THIS run, never estimated up
# front: guessed ETAs on this project have been wrong by an order of magnitude
# in both directions, which is worse than offering none.
set -uo pipefail
log=${1:?usage: watch-progress.sh LOGFILE [--watch]}
watch=${2:-}

render() {
  [ -f "$log" ] || { echo "  $log: not created yet"; return; }
  local line done total t rate left eta pct bar filled
  line=$(grep '^PROGRESS' "$log" 2>/dev/null | tail -1)
  if [ -z "$line" ]; then
    if grep -q '^total ' "$log" 2>/dev/null; then
      echo "  finished:"; tail -12 "$log"
    else
      echo "  starting up, no games finished yet"
    fi
    return
  fi
  done=$(sed -n 's/.*done=\([0-9]*\).*/\1/p' <<<"$line")
  total=$(sed -n 's/.*total=\([0-9]*\).*/\1/p' <<<"$line")
  t=$(sed -n 's/.*t=\([0-9.]*\).*/\1/p' <<<"$line")
  pct=$(awk -v d="$done" -v n="$total" 'BEGIN{printf "%.0f", 100*d/n}')
  filled=$(awk -v d="$done" -v n="$total" 'BEGIN{printf "%d", 30*d/n}')
  bar=$(printf '%*s' "$filled" '' | tr ' ' '#')
  rate=$(awk -v d="$done" -v t="$t" 'BEGIN{printf "%.2f", (t>0)? d/(t/60) : 0}')
  eta=$(awk -v d="$done" -v n="$total" -v t="$t" \
        'BEGIN{ if(d>0){ r=t/d; s=(n-d)*r; printf "%dm%02ds", s/60, s%60 } else printf "--" }')
  printf "  [%-30s] %s%%  %s/%s games   %.0fm elapsed   %s/min   ETA %s\n" \
         "$bar" "$pct" "$done" "$total" "$(awk -v t="$t" 'BEGIN{printf "%.0f", t/60}')" \
         "$rate" "$eta"
  grep '^RESULT' "$log" 2>/dev/null | tail -3 | sed 's/^RESULT /  done: /'
}

if [ "$watch" = "--watch" ]; then
  while :; do clear; echo "  $log"; echo; render; sleep 5; done
else
  render
fi
