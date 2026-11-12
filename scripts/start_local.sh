#!/usr/bin/env bash
# Start the thom house chatbot on this Mac: local server (wrangler dev --local), cron ticker, the optional room
# platform (OpenMausBot, docs/contracts.md 14.10), runner (claude -p on the subscription pool), Zalo bridge,
# zalo-agent listener and the staff console.
#
#   scripts/start_local.sh            personal Zalo mode (default)
#   THOMHOUSE_ZALO_MODE=mock scripts/start_local.sh    mock mode: no bridge, no listener
#
# The room platform is optional. Without tools/openmausbot the step is skipped and the stack starts as it always
# did. With it, the platform needs Node 24 or newer (looked up on PATH and under ~/.nvm/versions/node; the rest
# keeps Node 22), gets its config from `python3 -m runner.main rooms-setup`, and is started with a clean
# environment on 127.0.0.1 only: never with a tunnel, LAN, relay, domain or login option. Its log
# (~/.thomhouse-bot/logs/openmausbot.log) contains pairing codes: this script never prints it. Any problem with
# the platform is one line on screen and the stack goes on without it.
#
# Idempotent: a part that already runs is left alone. Secrets are generated into gitignored env files and never
# printed. PID files: ~/.thomhouse-bot/run (<name>.pid, plus <name>.start = the process start time, so a PID reused
# by another program after a reboot is not taken for ours), logs: ~/.thomhouse-bot/logs. Stop with scripts/stop_local.sh.
# Written for macOS /bin/bash 3.2.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOT_HOME="${THOMHOUSE_BOT_HOME:-$HOME/.thomhouse-bot}"
APP_HOME="${THOMHOUSE_APP_HOME:-$HOME/ThomHouse}"
# On a device installed by install/thomhouse.py (the root holds VERSION.json), the installer's private runtimes
# come first on PATH, in this order: node, python, runtime/bin (pnpm, and claude linked to ~/.local/bin/claude). The
# build Mac's checkout has no VERSION.json, so nothing changes there.
if [[ -f "$ROOT/VERSION.json" ]]; then
  for runtime_dir in "$APP_HOME/runtime/bin" "$APP_HOME/runtime/python/bin" "$APP_HOME/runtime/node/bin"; do
    if [[ -d "$runtime_dir" ]]; then PATH="$runtime_dir:$PATH"; fi
  done
  export PATH
fi
RUN_DIR="$BOT_HOME/run"
LOG_DIR="$BOT_HOME/logs"
D1_DIR="$BOT_HOME/d1"
MODE="${THOMHOUSE_ZALO_MODE:-personal}"
ENGINE_VERSION="2.5.9"
ENGINE_DIR="$ROOT/tools/zalo-agent"
ENGINE_BIN="$ENGINE_DIR/node_modules/.bin/zalo-agent"
ENGINE_PKG="$ENGINE_DIR/node_modules/@ardennguyen/zalo-agent-cli/package.json"
SERVER_PORT="8787"
SERVER_URL="http://127.0.0.1:$SERVER_PORT"
CONSOLE_PORT="5173"
CONSOLE_URL="http://127.0.0.1:$CONSOLE_PORT"
WRANGLER="$ROOT/apps/server/node_modules/.bin/wrangler"
VITE="$ROOT/apps/console/node_modules/.bin/vite"
SERVER_VARS="$ROOT/apps/server/.dev.vars"
RUNNER_ENV="$ROOT/apps/runner/.env"
BRIDGE_ENV="$ROOT/apps/zalo-bridge/.env"
ROOMS_DIR="$ROOT/tools/openmausbot"
ROOMS_BIN="$ROOMS_DIR/node_modules/.bin/openmausbot"
ROOMS_PORT="8799"
ROOMS_DATA_DIR="$BOT_HOME/openmausbot"
ROOMS_LOG="$LOG_DIR/openmausbot.log"
# Seconds to wait for the platform's port (whole number; the tests shorten it).
ROOMS_WAIT_S="${THOMHOUSE_ROOMS_WAIT_S:-60}"
[[ "$ROOMS_WAIT_S" =~ ^[0-9]+$ ]] || ROOMS_WAIT_S=60
ROOMS_OFF_NOTE="Các phần khác vẫn chạy; khi không có OpenMausBot, runner soạn tin theo ROOM_FALLBACK (mặc định: gọi thẳng claude -p)."

# New session for each service: its PID is also its process group, so stop_local.sh can stop the whole tree.
TRAMPOLINE='import os, sys
try:
    os.setsid()
except OSError:
    pass
os.execvp(sys.argv[1], sys.argv[1:])'

say() { printf '%s\n' "$*"; }
ok() { printf '  [ok] %s\n' "$*"; }
warn() { printf '  [!!] %s\n' "$*" >&2; }
die() {
  printf 'LỖI: %s\n' "$*" >&2
  exit 1
}

need() {
  command -v "$1" >/dev/null 2>&1 || die "máy chưa có lệnh '$1'. $2"
}

pid_of() {
  if [[ -f "$RUN_DIR/$1.pid" ]]; then cat "$RUN_DIR/$1.pid"; fi
}

# proc_start <pid>: start time of the process as ps prints it, empty when there is no such process.
proc_start() {
  ps -o lstart= -p "$1" 2>/dev/null | sed -e 's/^ *//' -e 's/ *$//'
}

# is_running <name> <pattern>: the PID file points at a live process whose command line contains <pattern> (fixed
# string) and whose start time equals the one recorded by spawn. A PID file written before <name>.start existed is
# checked by the pattern only.
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

# spawn <name> <logfile> <command...>: start in the background, detached, and write the PID and start-time files.
spawn() {
  local name="$1" log="$2"
  shift 2
  nohup python3 -I -c "$TRAMPOLINE" "$@" >>"$log" 2>&1 </dev/null &
  echo "$!" >"$RUN_DIR/$name.pid"
  proc_start "$!" >"$RUN_DIR/$name.start"
}

port_busy() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$1" -sTCP:LISTEN -t >/dev/null 2>&1
  else
    curl -s -m 2 -o /dev/null "http://127.0.0.1:$1/"
  fi
}

server_up() { curl -fsS -m 3 -o /dev/null "$SERVER_URL/health" 2>/dev/null; }
console_up() { curl -fsS -m 3 -o /dev/null "$CONSOLE_URL/" 2>/dev/null; }

wait_for() {
  local secs="$1" i
  shift
  for ((i = 0; i < secs; i++)); do
    if "$@"; then return 0; fi
    sleep 1
  done
  return 1
}

# run_limited <secs> <command...>: run the command and stop it after <secs> seconds (exit 124). macOS has no
# timeout(1).
run_limited() {
  python3 -I -c 'import subprocess, sys
try:
    sys.exit(subprocess.run(sys.argv[2:], timeout=float(sys.argv[1])).returncode)
except subprocess.TimeoutExpired:
    sys.exit(124)' "$@"
}

file_sum() {
  if [[ -f "$1" ]]; then cksum <"$1"; else echo "missing"; fi
}

case "$MODE" in
  personal | mock) ;;
  *) die "THOMHOUSE_ZALO_MODE phải là personal hoặc mock (đang là '$MODE')." ;;
esac

# After `thomhouse move-out` the data runs on another Mac: never start a second listener on the same Zalo account.
[[ ! -f "$BOT_HOME/moved-out.json" ]] || die "dữ liệu chatbot trong $BOT_HOME đã chuyển sang máy khác, nên script không bật chatbot ở máy này. Muốn bật lại ở đây, chạy lệnh move-back của thomhouse."

mkdir -p "$RUN_DIR" "$LOG_DIR" "$D1_DIR"
chmod 700 "$BOT_HOME" 2>/dev/null || true

# ---------------------------------------------------------------- (a) tools
say "1/9 Kiểm tra công cụ trên máy"
need node "Cài Node.js 22 trở lên."
need npm "npm đi kèm Node.js."
need pnpm "Cài pnpm 10.32.1: chạy ~/ThomHouse/bin/thomhouse install, hoặc xem docs/cai-dat-may-moi.md."
need python3 "Cài Python 3.11 trở lên."
need claude "Cài Claude Code CLI rồi đăng nhập bằng tài khoản Claude."
need curl "curl có sẵn trên macOS."
node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 22 ? 0 : 1)' ||
  die "cần Node.js 22 trở lên (máy đang có $(node --version))."
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' ||
  die "cần Python 3.11 trở lên (máy đang có $(python3 --version 2>&1))."
if [[ ! -x "$WRANGLER" || ! -x "$VITE" ]]; then
  say "  Cài thư viện JavaScript (pnpm install)..."
  (cd "$ROOT" && pnpm install --frozen-lockfile >>"$LOG_DIR/pnpm-install.log" 2>&1) ||
    die "pnpm install lỗi; xem $LOG_DIR/pnpm-install.log"
fi
ok "node $(node --version), pnpm $(pnpm --version), $(python3 --version 2>&1), claude có trên PATH"

# ---------------------------------------------------------------- (b) zalo-agent engine (local, not global)
say "2/9 Engine zalo-agent-cli $ENGINE_VERSION"
installed="$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["version"])' "$ENGINE_PKG" 2>/dev/null || true)"
if [[ "$installed" != "$ENGINE_VERSION" || ! -x "$ENGINE_BIN" ]]; then
  say "  Cài @ardennguyen/zalo-agent-cli@$ENGINE_VERSION vào tools/zalo-agent..."
  mkdir -p "$ENGINE_DIR"
  if [[ -f "$ENGINE_DIR/package-lock.json" ]]; then
    # Frozen install from the engine's lockfile: npm checks every package against its integrity hash.
    npm ci --prefix "$ENGINE_DIR" --no-fund --no-audit >>"$LOG_DIR/engine-install.log" 2>&1 ||
      die "cài zalo-agent-cli lỗi; xem $LOG_DIR/engine-install.log"
  else
    npm install --prefix "$ENGINE_DIR" --save-exact --no-fund --no-audit \
      "@ardennguyen/zalo-agent-cli@$ENGINE_VERSION" >>"$LOG_DIR/engine-install.log" 2>&1 ||
      die "cài zalo-agent-cli lỗi; xem $LOG_DIR/engine-install.log"
  fi
fi
[[ -x "$ENGINE_BIN" ]] || die "không thấy $ENGINE_BIN sau khi cài."
ok "zalo-agent $ENGINE_VERSION tại tools/zalo-agent"

# ---------------------------------------------------------------- (c) env files
say "3/9 File cấu hình (.dev.vars, runner .env, bridge .env)"
server_sum="$(file_sum "$SERVER_VARS")"
runner_sum="$(file_sum "$RUNNER_ENV")"
bridge_sum="$(file_sum "$BRIDGE_ENV")"
(cd "$ROOT/apps/zalo-bridge" && python3 -m bridge.main init-env --mode "$MODE" --engine-bin "$ENGINE_BIN" >/dev/null) ||
  die "không tạo được file cấu hình."
ok "ZALO_MODE=$MODE; token và secret nằm trong file gitignored, không in ra màn hình"

# warn_restart <name> <env file> <checksum before init-env>: the service runs with values read before the change.
warn_restart() {
  if [[ "$(file_sum "$2")" != "$3" ]]; then
    warn "$1 đang chạy với giá trị cũ, trong khi $2 vừa đổi. Chạy scripts/stop_local.sh rồi chạy lại script này."
  fi
}

# ---------------------------------------------------------------- (d) server, migrations, catalog
say "4/9 Server local ($SERVER_URL, dữ liệu D1 ở $D1_DIR)"
if is_running server "$ROOT/apps/server/"; then
  ok "server đang chạy (PID $(pid_of server))"
  warn_restart "Server" "$SERVER_VARS" "$server_sum"
else
  if port_busy "$SERVER_PORT"; then
    die "cổng $SERVER_PORT đang có tiến trình khác (không do script này mở, ví dụ một 'pnpm dev' cũ). Dừng tiến trình đó rồi chạy lại."
  fi
  (cd "$ROOT/apps/server" && node scripts/gen-seed-data.mjs >>"$LOG_DIR/server.log" 2>&1) ||
    die "gen-seed-data lỗi; xem $LOG_DIR/server.log"
  # Back up the data before pending migrations are applied (install/thomhouse.py backup, docs/contracts.md 16.8.2).
  # Without install/ (an older copy, the tests' temporary roots) nothing changes.
  if [[ -f "$ROOT/install/thomhouse.py" ]]; then THOMHOUSE_BOT_HOME="$BOT_HOME" python3 -I "$ROOT/install/thomhouse.py" backup --stopped --reason before-migration --if-pending-migrations --quiet >>"$LOG_DIR/backup.log" 2>&1 || die "chưa sao lưu được dữ liệu nên chưa áp migration; xem $LOG_DIR/backup.log"; fi
  (cd "$ROOT/apps/server" && "$WRANGLER" d1 migrations apply thomhouse-main --local --persist-to "$D1_DIR" \
    </dev/null >>"$LOG_DIR/server.log" 2>&1) || die "áp migration lỗi; xem $LOG_DIR/server.log"
  (cd "$ROOT/apps/server" && spawn server "$LOG_DIR/server.log" "$WRANGLER" dev --local --persist-to "$D1_DIR" \
    --ip 127.0.0.1 --port "$SERVER_PORT" --test-scheduled)
  wait_for 90 server_up || die "server chưa trả lời sau 90 giây; xem $LOG_DIR/server.log"
  ok "server đã chạy (PID $(pid_of server))"
fi
health="$(curl -fsS -m 3 "$SERVER_URL/health" 2>/dev/null || true)"
mode_re="\"zalo_mode\":[[:space:]]*\"$MODE\""
if [[ ! "$health" =~ $mode_re ]]; then
  warn "server báo /health = $health, trong khi script muốn ZALO_MODE=$MODE."
fi
# Catalog version from the content of the source files: re-seeding the same data keeps the same version, so
# conversation sessions are not reset by a restart.
catalog_version="cv_local_$(cat "$ROOT/data/services.json" "$ROOT/data/business-facts.json" \
  "$ROOT/design/system-prompt-draft.md" "$ROOT/design/tools-schema.json" | shasum -a 256 | cut -c1-12)" ||
  die "không đọc được data/ hoặc design/ để tính phiên bản catalog."
python3 -I "$ROOT/scripts/seed_dev.py" --url "$SERVER_URL" --catalog-version "$catalog_version" \
  >>"$LOG_DIR/seed.log" 2>&1 || die "nạp catalog lỗi; xem $LOG_DIR/seed.log"
ok "catalog $catalog_version đã nạp"

# Wrangler dev does not fire cron triggers by itself; the scheduler (follow-ups, lease expiry, sweeps) needs a tick.
if is_running cron __scheduled; then
  ok "cron ticker đang chạy"
else
  spawn cron "$LOG_DIR/cron.log" bash -c 'while :; do sleep 60; curl -fsS -m 30 -o /dev/null -A thomhouse-cron/1.0 "$1/__scheduled?cron=*+*+*+*+*" || echo "$(date "+%F %T") cron tick failed"; done' cron-tick "$SERVER_URL"
  ok "cron ticker gọi $SERVER_URL/__scheduled mỗi 60 giây"
fi

# ---------------------------------------------------------------- (e) Claude account pool
say "5/9 Danh sách tài khoản Claude cho runner"
if [[ -f "$BOT_HOME/accounts.json" ]]; then
  ok "đã có $BOT_HOME/accounts.json"
else
  THOMHOUSE_BOT_HOME="$BOT_HOME" python3 -I "$ROOT/scripts/runner/claude_pool.py" add-default default --priority 1 \
    >>"$LOG_DIR/runner.log" 2>&1 || die "không đăng ký được tài khoản Claude mặc định; xem $LOG_DIR/runner.log"
  ok "đã đăng ký tài khoản Claude đang đăng nhập trên máy (label default)"
fi

# Claude Code exports CLAUDE_EFFORT (and CLAUDECODE, CLAUDE_CODE_*) in its own sessions; the runner (and its
# rooms-setup command) must not inherit them. Outside a Claude Code session only CLAUDE_EFFORT is dropped, so
# variables the owner set on purpose (for example CLAUDE_CODE_OAUTH_TOKEN) still reach claude -p.
clean_env=(-u CLAUDE_EFFORT)
if [[ -n "${CLAUDECODE:-}" ]]; then
  while IFS= read -r var; do
    clean_env+=(-u "$var")
  done < <(compgen -e | grep -E '^(CLAUDECODE|CLAUDE_CODE_[A-Za-z0-9_]*)$' || true)
fi

# ---------------------------------------------------------------- (f) room platform (optional)
say "6/9 OpenMausBot cho phòng chat của hai bot (không bắt buộc)"
# start_rooms always returns 0: every problem is one line and the stack goes on without the platform. It sets
# rooms_node_dir (the directory of the node 24+ the platform runs on) only when the platform is up afterwards.
# Nothing is installed from the network unless tools/openmausbot/package.json exists and node_modules is missing.
rooms_node_dir=""
start_rooms() {
  local node_dir pid user npm_cmd
  if [[ ! -x "$ROOMS_BIN" && ! -f "$ROOMS_DIR/package.json" ]]; then
    ok "chưa cài OpenMausBot (không có tools/openmausbot): bỏ qua bước này, các phần khác chạy như trước"
    return 0
  fi
  node_dir="$(cd "$ROOT/apps/zalo-bridge" && python3 -m bridge.main rooms-node 2>/dev/null)" || node_dir=""
  if is_running openmausbot "$ROOMS_DIR/"; then
    ok "OpenMausBot đang chạy (PID $(pid_of openmausbot))"
    rooms_node_dir="$node_dir"
    return 0
  fi
  if port_busy "$ROOMS_PORT"; then
    warn "cổng $ROOMS_PORT đang có tiến trình khác (không do script này mở) nên script không mở OpenMausBot. $ROOMS_OFF_NOTE"
    return 0
  fi
  if [[ -z "$node_dir" ]]; then
    warn "OpenMausBot cần Node.js 24 trở lên, máy chưa có bản đó trong PATH và trong ~/.nvm/versions/node. $ROOMS_OFF_NOTE"
    return 0
  fi
  if [[ -f "$ROOMS_DIR/package.json" && ! -d "$ROOMS_DIR/node_modules" ]]; then
    say "  Cài OpenMausBot đúng phiên bản ghi trong tools/openmausbot/package.json..."
    npm_cmd=install
    if [[ -f "$ROOMS_DIR/package-lock.json" ]]; then npm_cmd=ci; fi
    if ! PATH="$node_dir:$PATH" npm "$npm_cmd" --prefix "$ROOMS_DIR" --no-fund --no-audit \
      >>"$LOG_DIR/openmausbot-install.log" 2>&1; then
      warn "cài OpenMausBot lỗi; xem $LOG_DIR/openmausbot-install.log. $ROOMS_OFF_NOTE"
      return 0
    fi
  fi
  if [[ ! -x "$ROOMS_BIN" ]]; then
    warn "không thấy $ROOMS_BIN nên script không mở OpenMausBot. $ROOMS_OFF_NOTE"
    return 0
  fi
  # The platform reads its config when it starts, so the runner writes it first, into the data folder and for the
  # CLI this script starts (an OPENMAUSBOT_DATA_DIR or OPENMAUSBOT_BIN in apps/runner/.env cannot point elsewhere).
  if ! (cd "$ROOT/apps/runner" && run_limited 120 env ${clean_env[@]+"${clean_env[@]}"} \
    THOMHOUSE_BOT_HOME="$BOT_HOME" OPENMAUSBOT_NODE_DIR="$node_dir" OPENMAUSBOT_DATA_DIR="$ROOMS_DATA_DIR" \
    OPENMAUSBOT_BIN="$ROOMS_BIN" python3 -m runner.main rooms-setup \
    >>"$LOG_DIR/runner.log" 2>&1 </dev/null); then
    warn "chưa ghi được cấu hình cho OpenMausBot (lệnh 'python3 -m runner.main rooms-setup' lỗi; xem $LOG_DIR/runner.log) nên script không mở OpenMausBot. $ROOMS_OFF_NOTE"
    return 0
  fi
  mkdir -p "$ROOMS_DATA_DIR"
  (umask 077 && : >>"$ROOMS_LOG")
  chmod 600 "$ROOMS_LOG" 2>/dev/null || true
  user="${USER:-$(id -un)}"
  # Clean environment (env -i): only what the platform needs, the node 24 directory first on PATH. Local port
  # only: no tunnel, LAN, relay, domain or login option is ever passed.
  (cd "$ROOMS_DATA_DIR" && spawn openmausbot "$ROOMS_LOG" env -i HOME="$HOME" USER="$user" LOGNAME="$user" \
    SHELL=/bin/zsh LANG=en_US.UTF-8 TMPDIR="${TMPDIR:-/tmp}" \
    PATH="$node_dir:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
    OMB_SESSION_IDLE_MS=120000 \
    "$ROOMS_BIN" serve --port "$ROOMS_PORT" --data-dir "$ROOMS_DATA_DIR" --label thomhouse --no-open)
  if wait_for "$ROOMS_WAIT_S" port_busy "$ROOMS_PORT"; then
    ok "OpenMausBot đã chạy (PID $(pid_of openmausbot)), chỉ nghe ở 127.0.0.1:$ROOMS_PORT"
    rooms_node_dir="$node_dir"
    return 0
  fi
  pid="$(pid_of openmausbot)"
  if [[ -n "$pid" ]]; then
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  fi
  rm -f "$RUN_DIR/openmausbot.pid" "$RUN_DIR/openmausbot.start"
  warn "OpenMausBot chưa mở cổng $ROOMS_PORT sau $ROOMS_WAIT_S giây nên script đã dừng tiến trình đó. Log nằm ở $ROOMS_LOG; file này có mã ghép nối, anh không gửi file cho người khác. $ROOMS_OFF_NOTE"
  return 0
}
start_rooms

# ---------------------------------------------------------------- (g) runner and bridge
say "7/9 Runner và bridge"
# Menu slides as JPEG copies for the bridge (data/menu-images.json -> $BOT_HOME/menu-images). Builds only what is
# missing or outdated; a failure never stops the start: the bot then cannot attach menu images.
if python3 -I "$ROOT/scripts/build_menu_images.py" --home "$BOT_HOME" --quiet >>"$LOG_DIR/menu-images.log" 2>&1; then
  ok "ảnh menu sẵn sàng ở $BOT_HOME/menu-images"
else
  warn "chưa tạo được ảnh menu (xem $LOG_DIR/menu-images.log); bot vẫn chạy nhưng chưa gửi được ảnh menu"
fi

# The draft engine is the runner's own setting (THOMHOUSE_DRAFT_ENGINE in apps/runner/.env): this script never
# overrides it. When the platform is up, the runner gets the node directory, the data folder and the CLI the
# platform was started with, so its CLI calls reach that platform. Without the platform the runner starts exactly
# as before.
rooms_env=()
if [[ -n "$rooms_node_dir" ]]; then
  rooms_env=(OPENMAUSBOT_NODE_DIR="$rooms_node_dir" OPENMAUSBOT_DATA_DIR="$ROOMS_DATA_DIR" OPENMAUSBOT_BIN="$ROOMS_BIN")
fi

if is_running runner runner.main; then
  ok "runner đang chạy (PID $(pid_of runner))"
  warn_restart "Runner" "$RUNNER_ENV" "$runner_sum"
else
  (cd "$ROOT/apps/runner" && spawn runner "$LOG_DIR/runner.log" \
    env ${clean_env[@]+"${clean_env[@]}"} THOMHOUSE_BOT_HOME="$BOT_HOME" ${rooms_env[@]+"${rooms_env[@]}"} \
    python3 -m runner.main run)
  ok "runner đã chạy (PID $(pid_of runner))"
fi

if [[ "$MODE" == personal ]]; then
  if is_running bridge bridge.main; then
    ok "bridge đang chạy (PID $(pid_of bridge))"
    warn_restart "Bridge" "$BRIDGE_ENV" "$bridge_sum"
  else
    (cd "$ROOT/apps/zalo-bridge" && spawn bridge "$LOG_DIR/bridge.log" \
      env THOMHOUSE_BOT_HOME="$BOT_HOME" python3 -m bridge.main run)
    ok "bridge đã chạy (PID $(pid_of bridge))"
  fi
else
  ok "chế độ mock: không chạy bridge"
fi

# ---------------------------------------------------------------- (h) zalo-agent listener
say "8/9 Listener nhận tin Zalo"
need_login=0
if [[ "$MODE" == personal ]]; then
  if out="$(cd "$ROOT/apps/zalo-bridge" && THOMHOUSE_BOT_HOME="$BOT_HOME" python3 -m bridge.main listener start 2>>"$LOG_DIR/bridge.log")"; then
    code=0
  else
    code=$?
  fi
  case "$code" in
    0)
      case "$out" in
        *'"already_running": true'*) ok "listener đang chạy" ;;
        *) ok "listener đã chạy, tin khách gửi về $SERVER_URL/zalo/personal/webhook" ;;
      esac
      ;;
    3)
      need_login=1
      warn "tài khoản Zalo chưa đăng nhập; cách đăng nhập nằm ở cuối thông báo này"
      ;;
    4) warn "một daemon zalo-agent khác (không do bridge mở) đang giữ kết nối của tài khoản Zalo. Dừng daemon đó bằng: $ENGINE_BIN listen --stop, rồi chạy lại script này." ;;
    *) warn "chưa bật được listener (mã $code). Xem chi tiết: cd apps/zalo-bridge && python3 -m bridge.main doctor" ;;
  esac
else
  ok "chế độ mock: không chạy listener"
fi

# ---------------------------------------------------------------- (i) console
say "9/9 Console cho nhân viên"
if is_running console "$ROOT/apps/console/"; then
  ok "console đang chạy (PID $(pid_of console))"
elif port_busy "$CONSOLE_PORT"; then
  warn "cổng $CONSOLE_PORT đang có tiến trình khác; không mở console."
else
  (cd "$ROOT/apps/console" && spawn console "$LOG_DIR/console.log" "$VITE" --host 127.0.0.1 --port "$CONSOLE_PORT" --strictPort)
  if wait_for 30 console_up; then ok "console đã chạy (PID $(pid_of console))"; else warn "console chưa trả lời sau 30 giây; xem $LOG_DIR/console.log"; fi
fi

say ""
say "Chatbot thom house đang chạy trên máy này (ZALO_MODE=$MODE)."
say "  Console:      $CONSOLE_URL"
if [[ -n "$rooms_node_dir" ]]; then
  say "  OpenMausBot:  http://127.0.0.1:$ROOMS_PORT (chỉ mở trên máy này)"
fi
say "  Staff token:  dòng STAFF_TOKEN trong $ROOT/apps/server/.dev.vars (nhập vào màn hình Cài đặt của console)"
say "  Log:          $LOG_DIR"
say "  Kiểm tra:     cd $ROOT/apps/zalo-bridge && python3 -m bridge.main doctor"
say "  Dừng:         $ROOT/scripts/stop_local.sh"
if [[ "$need_login" == 1 ]]; then
  say ""
  say "Tài khoản Zalo chưa đăng nhập, nên listener chưa chạy và bridge chưa gửi được tin."
  say "Anh chạy lệnh dưới đây trong Terminal, rồi quét mã QR bằng app Zalo trên điện thoại:"
  say ""
  say "  $ENGINE_BIN login"
  say ""
  say "Đăng nhập xong, anh chạy lại scripts/start_local.sh để bật listener."
fi
