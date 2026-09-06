#!/usr/bin/env bash
# Run a list of commands one after another, so cores are never idle between
# measurements. Each line of the queue file is a shell command; blank lines and
# those starting with # are ignored.
#
#   tools/run-queue.sh runs/queue.txt                 # start now
#   tools/run-queue.sh runs/queue.txt --after 12345   # wait for that pid first
#
# Emits PROGRESS lines so tools/watch-progress.sh can show which job is running
# and derive an ETA from the measured rate of completed jobs.
set -uo pipefail
queue=${1:?usage: run-queue.sh QUEUEFILE [--after PID]}
if [ "${2:-}" = "--after" ] && [ -n "${3:-}" ]; then
  echo "waiting for pid $3 to finish before starting"
  while kill -0 "$3" 2>/dev/null; do sleep 20; done
  echo "pid $3 done"
fi

mapfile -t jobs < <(grep -vE '^\s*(#|$)' "$queue")
total=${#jobs[@]}
start=$(date +%s)
echo "queue: $total jobs from $queue"

for i in "${!jobs[@]}"; do
  n=$((i + 1))
  echo
  echo "=== JOB $n/$total  $(date '+%H:%M:%S')  ${jobs[$i]}"
  echo "PROGRESS done=$i total=$total unit=jobs t=$(( $(date +%s) - start ))"
  bash -c "${jobs[$i]}"
  rc=$?
  echo "=== JOB $n/$total finished rc=$rc after $(( $(date +%s) - start ))s total"
  echo "PROGRESS done=$n total=$total unit=jobs t=$(( $(date +%s) - start ))"
done
echo
echo "queue complete in $(( $(date +%s) - start ))s"
