#!/usr/bin/env bash
# Stub of scripts/stop_local.sh for the installer tests (16.10): stops the sleepers that the stub start_local.sh
# started, with the same PID rule (command line pattern and recorded start time), and removes their PID files.
# Behaviour (key "stop_local" of <tmp>/behaviour.json): "survive" (service names left running), "exit" (code).
# Written for macOS /bin/bash 3.2.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOT_HOME="${THOMHOUSE_BOT_HOME:-$HOME/.thomhouse-bot}"
RUN_DIR="$BOT_HOME/run"
TEST_DIR="${THOMHOUSE_TEST_DIR:-$(dirname "$HOME")}"
[[ -f "$TEST_DIR/.installer-test" ]] || { echo "stub: no test folder" >&2; exit 99; }

say() { printf '%s\n' "$*"; }

beh() {
  python3 -I -c 'import json, sys
try:
    d = json.load(open(sys.argv[1])).get("stop_local", {})
except Exception:
    d = {}
v = d.get(sys.argv[2], sys.argv[3])
if isinstance(v, list):
    v = " ".join(str(x) for x in v)
print(v)' "$TEST_DIR/behaviour.json" "$1" "${2:-}"
}

python3 -I -c 'import json, os, sys
with open(sys.argv[1], "a") as f:
    f.write(json.dumps({"tool": "stop_local.sh", "argv": sys.argv[2:], "cwd": os.getcwd(),
                        "env_names": sorted(os.environ)}) + "\n")
' "$TEST_DIR/calls.jsonl" "$@"

SURVIVE=" $(beh survive) "

proc_start() {
  ps -o lstart= -p "$1" 2>/dev/null | sed -e 's/^ *//' -e 's/ *$//'
}
ours() {
  ps -o command= -p "$2" 2>/dev/null | grep -F -q -- "$3" || return 1
  if [[ -f "$RUN_DIR/$1.start" ]]; then
    [[ "$(proc_start "$2")" == "$(cat "$RUN_DIR/$1.start")" ]] || return 1
  fi
  return 0
}
stop_one() {
  local name="$1" pattern="$2" file pid i
  file="$RUN_DIR/$name.pid"
  if [[ ! -f "$file" ]]; then
    say "  $name: không chạy"
    return 0
  fi
  pid="$(cat "$file")"
  if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null || ! ours "$name" "$pid" "$pattern"; then
    rm -f "$file" "$RUN_DIR/$name.start"
    say "  $name: không chạy (đã xóa PID file cũ)"
    return 0
  fi
  if [[ "$SURVIVE" == *" $name "* ]]; then
    say "  $name: vẫn còn chạy (PID $pid)"
    return 0
  fi
  kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  for i in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.2
  done
  kill -KILL -- "-$pid" 2>/dev/null || true
  rm -f "$file" "$RUN_DIR/$name.start"
  say "  $name: đã dừng"
}

say "Dừng chatbot thom house trên máy này (stub)"
mkdir -p "$RUN_DIR"
stop_one console "$ROOT/apps/console/"
stop_one cron __scheduled
stop_one runner runner.main
stop_one openmausbot "$ROOT/tools/openmausbot/"
stop_one bridge bridge.main
stop_one server "$ROOT/apps/server/"
say "Xong."
exit "$(beh exit 0)"
