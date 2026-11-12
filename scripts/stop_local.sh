#!/usr/bin/env bash
# Stop what scripts/start_local.sh started, in this order: console, cron ticker, zalo-agent listener (only a
# daemon started with the bridge webhook), runner, room platform (OpenMausBot, optional), bridge, server.
# Idempotent: a part that is not running, or not installed, is skipped. Written for macOS /bin/bash 3.2.
#
# Runner and bridge get SIGTERM on their main process first, so they finish what they are doing (the runner its
# claude -p calls, the bridge the Zalo send in progress and its result). A second SIGTERM aborts that work; only
# then is the process group killed.
#
# A PID file is trusted only when the process still has the start time recorded in <name>.start (written by
# start_local.sh) and its command line contains the service's pattern: after a reboot the same PID can belong to
# another program, which must never get a signal.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOT_HOME="${THOMHOUSE_BOT_HOME:-$HOME/.thomhouse-bot}"
APP_HOME="${THOMHOUSE_APP_HOME:-$HOME/ThomHouse}"
# Same runtime PATH as start_local.sh on an installed device (VERSION.json at the root): without it a hand-run stop
# on a Mac without developer tools would call the /usr/bin/python3 shim and leave the listener running.
if [[ -f "$ROOT/VERSION.json" ]]; then
  for runtime_dir in "$APP_HOME/runtime/bin" "$APP_HOME/runtime/python/bin" "$APP_HOME/runtime/node/bin"; do
    if [[ -d "$runtime_dir" ]]; then PATH="$runtime_dir:$PATH"; fi
  done
  export PATH
fi
RUN_DIR="$BOT_HOME/run"
ENGINE_BIN="$ROOT/tools/zalo-agent/node_modules/.bin/zalo-agent"

say() { printf '%s\n' "$*"; }

alive() { kill -0 "$1" 2>/dev/null; }

# proc_start <pid>: start time of the process as ps prints it, empty when there is no such process.
proc_start() {
  ps -o lstart= -p "$1" 2>/dev/null | sed -e 's/^ *//' -e 's/ *$//'
}

# ours <name> <pid> <pattern>: the process is the one start_local.sh started for <name>.
ours() {
  ps -o command= -p "$2" 2>/dev/null | grep -F -q -- "$3" || return 1
  if [[ -f "$RUN_DIR/$1.start" ]]; then
    [[ "$(proc_start "$2")" == "$(cat "$RUN_DIR/$1.start")" ]] || return 1
  fi
  return 0
}

# wait_gone <pid> <seconds>
wait_gone() {
  local pid="$1" ticks=$(($2 * 5)) i
  for ((i = 0; i < ticks; i++)); do
    alive "$pid" || return 0
    sleep 0.2
  done
  ! alive "$pid"
}

signal() {
  # signal <SIG> <pid> <group|main>
  if [[ "$3" == group ]]; then
    kill "-$1" -- "-$2" 2>/dev/null || kill "-$1" "$2" 2>/dev/null || true
  else
    kill "-$1" "$2" 2>/dev/null || true
  fi
}

# stop_one <name> <pattern> <group|main> <grace_s> [<second_term_grace_s>]
stop_one() {
  local name="$1" pattern="$2" how="$3" grace="$4" grace2="${5:-0}" file pid
  file="$RUN_DIR/$name.pid"
  if [[ ! -f "$file" ]]; then
    say "  $name: không chạy"
    return 0
  fi
  pid="$(cat "$file")"
  if [[ -z "$pid" ]] || ! alive "$pid" || ! ours "$name" "$pid" "$pattern"; then
    rm -f "$file" "$RUN_DIR/$name.start"
    say "  $name: không chạy (đã xóa PID file cũ)"
    return 0
  fi
  signal TERM "$pid" "$how"
  if ! wait_gone "$pid" "$grace"; then
    if [[ "$grace2" -gt 0 ]]; then
      say "  $name: chưa dừng sau ${grace} giây, gửi tín hiệu dừng lần hai"
      signal TERM "$pid" main
      wait_gone "$pid" "$grace2" || true
    fi
    if alive "$pid"; then
      signal KILL "$pid" group
      wait_gone "$pid" 5 || true
    fi
  fi
  # Leftover children in the service's process group (node, workerd).
  kill -TERM -- "-$pid" 2>/dev/null || true
  rm -f "$file" "$RUN_DIR/$name.start"
  if alive "$pid"; then say "  $name: vẫn còn chạy (PID $pid)"; else say "  $name: đã dừng"; fi
}

say "Dừng chatbot thom house trên máy này"
mkdir -p "$RUN_DIR"
stop_one console "$ROOT/apps/console/" group 5
stop_one cron __scheduled group 2

if [[ -x "$ENGINE_BIN" && -f "$ROOT/apps/zalo-bridge/.env" ]]; then
  if out="$(cd "$ROOT/apps/zalo-bridge" && THOMHOUSE_BOT_HOME="$BOT_HOME" python3 -m bridge.main listener stop --only-ours 2>/dev/null)"; then
    case "$out" in
      *'"stopped": true'*) say "  listener: đã dừng" ;;
      *'"running": true'*) say "  listener: một daemon zalo-agent không do bridge mở vẫn chạy; script không dừng daemon đó" ;;
      *) say "  listener: không chạy" ;;
    esac
  else
    say "  listener: không đọc được trạng thái; dừng tay bằng: $ENGINE_BIN listen --stop"
  fi
else
  say "  listener: chưa cài zalo-agent, bỏ qua"
fi

stop_one runner runner.main main 25 15
# The room platform stops after the runner, which may still be finishing a room turn. It is optional: without an
# install there is no PID file and the line says it is not running. Its log is never printed (pairing codes).
stop_one openmausbot "$ROOT/tools/openmausbot/" group 15
stop_one bridge bridge.main main 40 10
stop_one server "$ROOT/apps/server/" group 15
say "Xong."
