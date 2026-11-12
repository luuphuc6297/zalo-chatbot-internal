#!/usr/bin/env bash
# Stub of scripts/start_local.sh for the installer tests (16.10). It prints the nine real step titles, runs the
# stub init-env, spawns sleepers whose command lines and working folders look like the real services, and writes
# <name>.pid and <name>.start like start_local.sh:96-102. It writes the names of its environment variables and the
# values of no_proxy, NO_PROXY, DISABLE_UPDATES and PATH to <tmp>/start-env.json.
# Behaviour (key "start_local" of <tmp>/behaviour.json): "exit" (code, default 0), "fail_at_step" (1-9),
# "hook" (run the real backup hook line before a migration call), "migrate" (call wrangler d1 migrations apply),
# "rooms" (also start an OpenMausBot sleeper in BOT_HOME/openmausbot), "skip" (service names not started),
# "sleep" (seconds the sleepers live, default 300).
# Written for macOS /bin/bash 3.2.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOT_HOME="${THOMHOUSE_BOT_HOME:-$HOME/.thomhouse-bot}"
RUN_DIR="$BOT_HOME/run"
LOG_DIR="$BOT_HOME/logs"
D1_DIR="$BOT_HOME/d1"
ENGINE_VERSION="2.5.9"
ENGINE_BIN="$ROOT/tools/zalo-agent/node_modules/.bin/zalo-agent"
SERVER_URL="http://127.0.0.1:8787"
TEST_DIR="${THOMHOUSE_TEST_DIR:-$(dirname "$HOME")}"
[[ -f "$TEST_DIR/.installer-test" ]] || { echo "stub: no test folder" >&2; exit 99; }

TRAMPOLINE='import os, sys
try:
    os.setsid()
except OSError:
    pass
os.execvp(sys.argv[1], sys.argv[1:])'

say() { printf '%s\n' "$*"; }
die() {
  printf 'LỖI: %s\n' "$*" >&2
  exit 1
}

# beh <key> [default]: value of start_local.<key> in behaviour.json (lists joined by spaces).
beh() {
  python3 -I -c 'import json, sys
try:
    d = json.load(open(sys.argv[1])).get("start_local", {})
except Exception:
    d = {}
v = d.get(sys.argv[2], sys.argv[3])
if isinstance(v, bool):
    v = "1" if v else ""
elif isinstance(v, list):
    v = " ".join(str(x) for x in v)
print(v)' "$TEST_DIR/behaviour.json" "$1" "${2:-}"
}

python3 -I -c 'import json, os, sys
names = sorted(os.environ)
doc = {"names": names, "no_proxy": os.environ.get("no_proxy"), "NO_PROXY": os.environ.get("NO_PROXY"),
       "DISABLE_UPDATES": os.environ.get("DISABLE_UPDATES"), "PATH": os.environ.get("PATH"),
       "cwd": os.getcwd()}
json.dump(doc, open(sys.argv[1], "w"))
with open(sys.argv[2], "a") as f:
    f.write(json.dumps({"tool": "start_local.sh", "argv": sys.argv[3:], "cwd": os.getcwd(), "env_names": names,
                        "env": {"no_proxy": os.environ.get("no_proxy"),
                                "DISABLE_UPDATES": os.environ.get("DISABLE_UPDATES")}}) + "\n")
' "$TEST_DIR/start-env.json" "$TEST_DIR/calls.jsonl" "$@"

FAIL_AT="$(beh fail_at_step 0)"
SKIP=" $(beh skip) "
SLEEP_S="$(beh sleep 300)"
SLEEPER=(python3 -c 'import sys, time; time.sleep(float(sys.argv[1]))' "$SLEEP_S")

step() {
  say "$1/9 $2"
  if [[ "$FAIL_AT" == "$1" ]]; then die "stub failure at step $1"; fi
}

pid_of() {
  if [[ -f "$RUN_DIR/$1.pid" ]]; then cat "$RUN_DIR/$1.pid"; fi
}
proc_start() {
  ps -o lstart= -p "$1" 2>/dev/null | sed -e 's/^ *//' -e 's/ *$//'
}
is_running() {
  local pid
  pid="$(pid_of "$1")"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  ps -o command= -p "$pid" 2>/dev/null | grep -F -q -- "$2" || return 1
  if [[ -f "$RUN_DIR/$1.start" ]]; then
    [[ "$(proc_start "$pid")" == "$(cat "$RUN_DIR/$1.start")" ]] || return 1
  fi
  return 0
}
spawn() {
  local name="$1" log="$2"
  shift 2
  nohup python3 -I -c "$TRAMPOLINE" "$@" >>"$log" 2>&1 </dev/null &
  echo "$!" >"$RUN_DIR/$name.pid"
  proc_start "$!" >"$RUN_DIR/$name.start"
}
wanted() { [[ "$SKIP" != *" $1 "* ]]; }

mkdir -p "$RUN_DIR" "$LOG_DIR" "$D1_DIR"
chmod 700 "$BOT_HOME" 2>/dev/null || true

step 1 "Kiểm tra công cụ trên máy"
step 2 "Engine zalo-agent-cli $ENGINE_VERSION"
step 3 "File cấu hình (.dev.vars, runner .env, bridge .env)"
(cd "$ROOT/apps/zalo-bridge" && python3 -m bridge.main init-env --mode personal --engine-bin "$ENGINE_BIN" >/dev/null) ||
  die "không tạo được file cấu hình."
step 4 "Server local ($SERVER_URL, dữ liệu D1 ở $D1_DIR)"
if [[ -n "$(beh migrate)" || -n "$(beh hook)" ]]; then
  if [[ -n "$(beh hook)" ]]; then
    if [[ -f "$ROOT/install/thomhouse.py" ]]; then THOMHOUSE_BOT_HOME="$BOT_HOME" python3 -I "$ROOT/install/thomhouse.py" backup --stopped --reason before-migration --if-pending-migrations --quiet >>"$LOG_DIR/backup.log" 2>&1 || die "chưa sao lưu được dữ liệu nên chưa áp migration; xem $LOG_DIR/backup.log"; fi
  fi
  WRANGLER="$ROOT/apps/server/node_modules/.bin/wrangler"
  [[ -x "$WRANGLER" ]] || WRANGLER="wrangler"
  (cd "$ROOT/apps/server" && "$WRANGLER" d1 migrations apply thomhouse-main --local --persist-to "$D1_DIR" \
    </dev/null >>"$LOG_DIR/server.log" 2>&1) || die "áp migration lỗi; xem $LOG_DIR/server.log"
fi
if wanted server && ! is_running server "$ROOT/apps/server/"; then
  (cd "$ROOT/apps/server" && spawn server "$LOG_DIR/server.log" "${SLEEPER[@]}" "$ROOT/apps/server/")
fi
if wanted cron && ! is_running cron __scheduled; then
  spawn cron "$LOG_DIR/cron.log" "${SLEEPER[@]}" cron-tick "$SERVER_URL/__scheduled"
fi
step 5 "Danh sách tài khoản Claude cho runner"
step 6 "OpenMausBot cho phòng chat của hai bot (không bắt buộc)"
if [[ -n "$(beh rooms)" ]] && wanted openmausbot && ! is_running openmausbot "$ROOT/tools/openmausbot/"; then
  mkdir -p "$BOT_HOME/openmausbot"
  (cd "$BOT_HOME/openmausbot" && spawn openmausbot "$LOG_DIR/openmausbot.log" "${SLEEPER[@]}" \
    "$ROOT/tools/openmausbot/node_modules/.bin/openmausbot" serve --port 8799)
fi
step 7 "Runner và bridge"
if wanted runner && ! is_running runner runner.main; then
  (cd "$ROOT/apps/runner" && spawn runner "$LOG_DIR/runner.log" "${SLEEPER[@]}" runner.main run)
fi
if wanted bridge && ! is_running bridge bridge.main; then
  (cd "$ROOT/apps/zalo-bridge" && spawn bridge "$LOG_DIR/bridge.log" "${SLEEPER[@]}" bridge.main run)
fi
step 8 "Listener nhận tin Zalo"
step 9 "Console cho nhân viên"
if wanted console && ! is_running console "$ROOT/apps/console/"; then
  (cd "$ROOT/apps/console" && spawn console "$LOG_DIR/console.log" "${SLEEPER[@]}" "$ROOT/apps/console/")
fi
say "Chatbot thom house đang chạy trên máy này (stub)."
exit "$(beh exit 0)"
