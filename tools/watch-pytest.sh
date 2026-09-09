#!/usr/bin/env bash
# Watch a backgrounded `pytest -q` run by counting the progress characters it
# prints. pytest emits no counter of its own until the end, and this suite runs
# for minutes, so the dots are the only live signal there is.
#
#   tools/watch-pytest.sh /tmp/fulltests.log            # one shot
#   tools/watch-pytest.sh /tmp/fulltests.log --watch    # refresh every 5s
#
# The total comes from `--collect-only`, cached next to the log, and the ETA is
# derived from the rate this run has actually managed, never guessed up front.
set -uo pipefail
log=${1:?usage: watch-pytest.sh LOGFILE [--watch]}
watch=${2:-}
totalfile="$log.total"

if [ ! -s "$totalfile" ]; then
  PYTHONPATH=. .venv/bin/python -m pytest -q --collect-only 2>/dev/null \
    | sed -n 's/^\([0-9]*\) tests collected.*/\1/p' | tail -1 > "$totalfile"
fi
total=$(cat "$totalfile" 2>/dev/null)

render() {
  [ -f "$log" ] || { echo "  $log: not created yet"; return; }
  if grep -qE '^[0-9]+ (passed|failed)|^(FAILED|ERROR)|(passed|failed|error)( |,).*in [0-9.]+s' "$log"; then
    echo "  finished:"; tail -15 "$log"; return
  fi
  local done started elapsed rate left eta pct
  # count only the lines that are pure progress characters: any other line,
  # a summary or a traceback, carries letters that would inflate the count
  done=$(grep -oE '^[.sFEx]+' "$log" | tr -d '\n' | wc -c)
  started=$(stat -c %Y "$log")
  elapsed=$(( $(date +%s) - started ))
  if [ -z "$total" ] || [ "$total" -eq 0 ] 2>/dev/null; then
    echo "  $done tests done, ${elapsed}s elapsed (total unknown, no ETA)"; return
  fi
  pct=$(awk -v d="$done" -v n="$total" 'BEGIN{printf "%.0f", 100*d/n}')
  if [ "$done" -gt 0 ]; then
    eta=$(awk -v d="$done" -v n="$total" -v e="$elapsed" \
      'BEGIN{r=e/d; s=int(r*(n-d)); printf "%dm%02ds", s/60, s%60}')
    printf "  %d/%d tests (%s%%)  %ds elapsed  ETA %s\n" "$done" "$total" "$pct" "$elapsed" "$eta"
  else
    printf "  0/%d tests, %ds elapsed, collecting (no rate yet)\n" "$total" "$elapsed"
  fi
}

if [ "$watch" = "--watch" ]; then
  while :; do clear; echo "  $log"; render; sleep 5; done
else
  render
fi
