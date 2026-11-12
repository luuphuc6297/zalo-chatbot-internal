#!/bin/bash
# Runtime bootstrap of a thom house release (docs/contracts.md 16.4.6, step 4 of 16.4.3). bash 3.2, stock tools.
#
#   bash releases/<ver>/install/bootstrap.sh --release-file FILE [--yes] [--skip-human] [--trust-channel]
#        [--menu FILE] [--move-in FILE]           run by the .command header, which holds the bootstrap lock
#   bash ~/ThomHouse/app/install/bootstrap.sh --python-only
#                                                  repair of the private Python on an installed device (check 5)
#
# It reads install/versions.env as text (never sourced), detects the four runtimes by running exactly the files
# the launcher uses (never a PATH lookup, rev check), prints one plan for the missing ones and asks once. On c it
# installs Python from cache/downloads or with curl, checks its SHA-256 and version, links runtime/python, and execs
# the Python CLI with the consented names; the PID stays the one in .bootstrap.lock.d/pid (rev F6). It never runs
# /usr/bin/python3. Its own commands use /usr/bin:/bin:/usr/sbin:/sbin; THOMHOUSE_TOOL_PATH replaces those folders
# in tests and is never set on a device.

set -u
umask 077
CALLER_PATH="${PATH:-}"
SYSTEM_PATH="${THOMHOUSE_TOOL_PATH:-/usr/bin:/bin:/usr/sbin:/sbin}"
PATH="$SYSTEM_PATH"
export PATH

say() { printf '%s\n' "$*"; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REL="$(cd "$HERE/.." && pwd)"

OPT_PY_ONLY=0
OPT_YES=0
OPT_SKIP_HUMAN=0
OPT_TRUST=0
OPT_MENU=""
OPT_MOVE_IN=""
RELEASE_FILE=""

usage() {
  say "Lệnh gõ chưa đúng. Cách gõ: bash ~/ThomHouse/app/install/bootstrap.sh --python-only"
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --python-only) OPT_PY_ONLY=1 ;;
    --yes) OPT_YES=1 ;;
    --skip-human) OPT_SKIP_HUMAN=1 ;;
    --trust-channel) OPT_TRUST=1 ;;
    --menu) [ $# -ge 2 ] || usage; OPT_MENU="$2"; shift ;;
    --move-in) [ $# -ge 2 ] || usage; OPT_MOVE_IN="$2"; shift ;;
    --release-file) [ $# -ge 2 ] || usage; RELEASE_FILE="$2"; shift ;;
    *) usage ;;
  esac
  shift
done

# ---------------------------------------------------------------- shared helpers (same in selfextract.sh.in)
expand_home() {
  case "$1" in
    "~") printf '%s' "$HOME" ;;
    "~/"*) printf '%s/%s' "$HOME" "${1#\~/}" ;;
    /*) printf '%s' "$1" ;;
    *) printf '%s/%s' "$PWD" "$1" ;;
  esac
}

tilde() {
  case "$1" in
    "$HOME") printf '~' ;;
    "$HOME"/*) printf '~%s' "${1#"$HOME"}" ;;
    *) printf '%s' "$1" ;;
  esac
}

VERSIONS_ENV=""
venv() {
  local line
  while IFS= read -r line; do
    case "$line" in
      "$1="*) printf '%s' "${line#*=}"; return 0 ;;
    esac
  done <<EOF
$VERSIONS_ENV
EOF
  printf '%s' "${2:-}"
}

first_version() { sed -n 's/[^0-9]*\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\).*/\1/p' | head -n 1; }

run_version() {
  [ -x "$1" ] || return 0
  "$1" --version 2>&1 </dev/null | first_version
}

num() {
  local n="${1%%[!0-9]*}"
  printf '%s' "${n:-0}"
}

ver_ge() {
  local a1 a2 a3 b1 b2 b3
  [ -n "$1" ] || return 1
  IFS=. read -r a1 a2 a3 <<EOF
$1
EOF
  IFS=. read -r b1 b2 b3 <<EOF
$2
EOF
  a1="$(num "${a1:-}")"; a2="$(num "${a2:-}")"; a3="$(num "${a3:-}")"
  b1="$(num "${b1:-}")"; b2="$(num "${b2:-}")"; b3="$(num "${b3:-}")"
  [ "$a1" -gt "$b1" ] && return 0
  [ "$a1" -lt "$b1" ] && return 1
  [ "$a2" -gt "$b2" ] && return 0
  [ "$a2" -lt "$b2" ] && return 1
  [ "$a3" -ge "$b3" ]
}

host_of() { printf '%s' "$1" | sed -e 's#^[A-Za-z]*://##' -e 's#[/:].*##'; }

mb() {
  if [ -n "$1" ]; then printf '%s' $(( ($1 + 999999) / 1000000 )); else printf '?'; fi
}

ANSWER=""
ask_ck() {
  local line
  if [ "$1" = 1 ] && [ "$OPT_YES" = 1 ]; then
    say "Chương trình tự trả lời c vì lệnh có --yes."
    ANSWER=c
    return 0
  fi
  if [ ! -t 0 ]; then
    say "Không có ai gõ phím trong cửa sổ này, nên chương trình tự trả lời k."
    ANSWER=k
    return 0
  fi
  while :; do
    if ! IFS= read -r line; then
      say "Không có ai gõ phím trong cửa sổ này, nên chương trình tự trả lời k."
      ANSWER=k
      return 0
    fi
    line="$(printf '%s' "$line" | tr -d ' \t\r' | tr 'A-Z' 'a-z')"
    case "$line" in
      c | co | "có" | "Có") ANSWER=c; return 0 ;;
      "" | k | khong | "không" | "Không") ANSWER=k; return 0 ;;
    esac
    say "Anh gõ một trong các chữ c, k rồi Enter."
  done
}

build_env() {
  local u np name
  u="${USER:-$(id -un 2>/dev/null)}"
  np="${no_proxy:-${NO_PROXY:-}}"
  for name in 127.0.0.1 localhost ::1; do
    case ",$np," in
      *",$name,"*) ;;
      *) np="${np:+$np,}$name" ;;
    esac
  done
  ENV_ARGS=(HOME="$HOME" USER="$u" LOGNAME="$u" LANG=en_US.UTF-8 TERM="${TERM:-xterm-256color}"
    TMPDIR="${TMPDIR:-/tmp}"
    PATH="$APP_HOME/runtime/node/bin:$APP_HOME/runtime/python/bin:$APP_HOME/runtime/bin:$SYSTEM_PATH"
    THOMHOUSE_APP_HOME="$APP_HOME" THOMHOUSE_BOT_HOME="$BOT_HOME"
    DISABLE_UPDATES=1 ZALO_AGENT_NO_UPDATE_CHECK=1 WRANGLER_SEND_METRICS=false PROFILE_LLM_ENABLED=false)
  for name in http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY ZALO_CONFIG_DIR; do
    if [ -n "${!name:-}" ]; then ENV_ARGS+=("$name=${!name}"); fi
  done
  for name in $(compgen -e); do
    case "$name" in
      THOMHOUSE_APP_HOME | THOMHOUSE_BOT_HOME) ;;
      THOMHOUSE_*) ENV_ARGS+=("$name=${!name}") ;;
    esac
  done
  ENV_ARGS+=(no_proxy="$np" NO_PROXY="$np")
}

# ---------------------------------------------------------------- folders, lock, pins
APP_HOME="$(expand_home "${THOMHOUSE_APP_HOME:-$HOME/ThomHouse}")"
BOT_HOME="$(expand_home "${THOMHOUSE_BOT_HOME:-$HOME/.thomhouse-bot}")"
for folder in "$APP_HOME" "$BOT_HOME"; do
  case "$folder" in
    *[[:space:]]*)
      say "Thư mục $folder có dấu cách, nên chương trình không dùng thư mục đó."
      say "Anh chọn thư mục không có dấu cách."
      exit 3
      ;;
  esac
done
AH="$(tilde "$APP_HOME")"
LOCKD="$APP_HOME/.bootstrap.lock.d"
LOGS="$APP_HOME/logs"
RT="$APP_HOME/runtime"
DL="$APP_HOME/cache/downloads"

leave() {
  if [ -f "$LOCKD/pid" ] && [ "$(tr -cd 0-9 <"$LOCKD/pid")" = "$$" ]; then rm -rf "$LOCKD"; fi
  exit "$1"
}

VERSIONS_ENV="$(cat "$REL/install/versions.env" 2>/dev/null)"
if [ -z "$VERSIONS_ENV" ]; then
  say "File cài đặt bị hỏng hoặc đã bị sửa nên chương trình chưa cài gì. Anh chép lại file rồi chạy lại."
  leave 3
fi
VERSION="$(sed -n 's/.*"version"[^"]*"\([0-9][0-9.]*\)".*/\1/p' "$REL/VERSION.json" 2>/dev/null | head -n 1)"

if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = 1 ]; then
  PLAT=darwin_arm64
  TRIPLE=aarch64-apple-darwin
else
  PLAT=darwin_x64
  TRIPLE=x86_64-apple-darwin
fi
PY_VERSION="$(venv PY_VERSION)"
PY_URL="$(venv "PY_URL_$PLAT")"
PY_SHA="$(venv "PY_SHA256_$PLAT")"
PY_BYTES="$(venv "PY_BYTES_$PLAT")"
NODE_VERSION="$(venv NODE_VERSION)"
NODE_URL="$(venv "NODE_URL_$PLAT")"
NODE_SHA="$(venv "NODE_SHA256_$PLAT")"
NODE_BYTES="$(venv "NODE_BYTES_$PLAT")"
PNPM_VERSION="$(venv PNPM_VERSION)"
PNPM_BYTES="$(venv PNPM_BYTES)"
CLAUDE_VERSION="$(venv CLAUDE_VERSION)"
CLAUDE_MIN="$(venv CLAUDE_MIN "$CLAUDE_VERSION")"
CLAUDE_URL="$(venv CLAUDE_INSTALLER_URL https://claude.ai/install.sh)"
CLAUDE_MB="$(venv CLAUDE_APPROX_MB)"

if [ "$OPT_PY_ONLY" = 1 ]; then
  CMD="bash $AH/app/install/bootstrap.sh --python-only"
elif [ -n "$RELEASE_FILE" ]; then
  CMD="bash $RELEASE_FILE"
else
  CMD="bash thomhouse-$VERSION.command"
fi

# ---------------------------------------------------------------- detection at the launcher's locations
pnpm_version() {
  [ -x "$RT/bin/pnpm" ] || return 0
  /usr/bin/env PATH="$RT/node/bin:$PATH" "$RT/bin/pnpm" --version 2>&1 </dev/null | first_version
}

NEED=""
if [ "$OPT_PY_ONLY" = 1 ]; then
  NEED="python"
else
  [ "$(run_version "$RT/python/bin/python3")" = "$PY_VERSION" ] || NEED="$NEED python"
  [ "$(run_version "$RT/node/bin/node")" = "$NODE_VERSION" ] || NEED="$NEED node"
  [ "$(pnpm_version)" = "$PNPM_VERSION" ] || NEED="$NEED pnpm"
  ver_ge "$(run_version "$HOME/.local/bin/claude")" "$CLAUDE_MIN" || NEED="$NEED claude_code"
fi
NEED="${NEED# }"

needs() {
  case " $NEED " in *" $1 "*) return 0 ;; esac
  return 1
}

# ---------------------------------------------------------------- the plan and the one question (16.4.7)
if [ -n "$NEED" ]; then
  say "Máy cần thêm các phần mềm dưới đây. Chương trình cài chúng cho riêng chatbot,"
  say "không cần mật khẩu máy và không sửa cài đặt của Terminal:"
  if needs python; then
    say "  - Python $PY_VERSION: tải từ $(host_of "$PY_URL"), $(mb "$PY_BYTES") MB, đặt vào $AH/runtime"
  fi
  if needs node; then
    say "  - Node.js $NODE_VERSION: tải từ $(host_of "$NODE_URL"), $(mb "$NODE_BYTES") MB, đặt vào $AH/runtime"
  fi
  if needs pnpm; then
    say "  - pnpm $PNPM_VERSION: tải từ registry.npmjs.org, $(mb "$PNPM_BYTES") MB, đặt vào $AH/runtime"
  fi
  if needs claude_code; then
    LINE="  - Claude Code $CLAUDE_VERSION: chương trình cài của Anthropic (claude.ai),"
    say "$LINE khoảng $CLAUDE_MB MB, vào ~/.local"
    OTHER="$(PATH="$CALLER_PATH" command -v claude 2>/dev/null)"
    if [ -n "$OTHER" ] && [ "$OTHER" != "$HOME/.local/bin/claude" ]; then
      say "    Máy đã có một bản Claude Code khác; chatbot dùng bản riêng này, bản kia giữ nguyên."
    fi
  fi
  say "Anh gõ c rồi Enter để cài, hoặc gõ k rồi Enter để dừng."
  ask_ck 1
  if [ "$ANSWER" != c ]; then
    say "Chương trình chưa cài phần mềm nào; mã chương trình đã chép vào $AH."
    say "Chatbot chỉ chạy với đúng các bản dưới đây:"
    if needs python; then
      say "  - Python $PY_VERSION: $PY_URL"
      say "    SHA-256 $PY_SHA"
    fi
    if needs node; then
      say "  - Node.js $NODE_VERSION: $NODE_URL"
      say "    SHA-256 $NODE_SHA"
    fi
    if needs pnpm; then
      say "  - pnpm $PNPM_VERSION: cần mạng tới registry.npmjs.org; không cài tay được."
    fi
    if needs claude_code; then
      say "  - Claude Code $CLAUDE_VERSION: anh tự cài bằng lệnh dưới đây rồi chạy lại lệnh cài:"
      say "    curl -fsSL $CLAUDE_URL | bash -s $CLAUDE_VERSION"
    fi
    if needs python || needs node; then
      say "Với Python và Node.js, anh có thể tải file ở máy khác và chép vào $AH/cache/downloads/,"
      say "rồi chạy lại lệnh cài; chương trình kiểm mã từng file trước khi dùng."
    fi
    leave 4
  fi
fi

# ---------------------------------------------------------------- Python (step 4)
sha_of() { shasum -a 256 "$1" 2>/dev/null | cut -d' ' -f1; }

download_failed() {
  local name="Python $PY_VERSION" host
  host="$(host_of "$PY_URL")"
  if [ "$1" = 22 ]; then
    say "Máy chủ $host chưa trả file $name. Anh chờ một lúc rồi chạy lại: $CMD"
  elif [ "$1" = 23 ]; then
    say "Ổ đĩa của máy không đủ chỗ trống để tải $name."
    say "Anh xóa bớt tệp rồi chạy lại: $CMD"
  else
    say "Chưa tải được $name từ $host vì máy không kết nối được mạng."
    say "Anh kiểm tra mạng rồi chạy lại: $CMD"
  fi
  leave 1
}

bad_download() {
  rm -f "$1"
  say "File Python $PY_VERSION tải về không đúng mã kiểm tra nên chương trình đã xóa file đó."
  say "Anh chạy lại: $CMD"
  leave 1
}

python_archive() {
  local target f base rc
  target="$DL/$PY_SHA.tar.gz"
  mkdir -p "$DL" "$LOGS"
  chmod 700 "$APP_HOME/cache" "$DL" "$LOGS" 2>/dev/null
  if [ -f "$target" ] && [ "$(sha_of "$target")" = "$PY_SHA" ]; then
    ARCHIVE="$target"
    return 0
  fi
  for f in "$DL"/*; do
    [ -f "$f" ] && [ ! -L "$f" ] || continue
    base="${f##*/}"
    case "$base" in .* | *.part) continue ;; esac
    if printf '%s' "$base" | grep -Eq '^[0-9a-f]{64}\.' && [ "${base#"$PY_SHA"}" = "$base" ]; then continue; fi
    if [ "$(sha_of "$f")" = "$PY_SHA" ]; then
      mv -f "$f" "$target"
      ARCHIVE="$target"
      return 0
    fi
  done
  case "$PY_URL" in
    https://*) ;;
    *)
      say "Địa chỉ tải Python $PY_VERSION không dùng https nên chương trình không tải. Anh báo người gửi file."
      leave 1
      ;;
  esac
  curl --proto =https --tlsv1.2 -fL --retry 3 -C - -o "$DL/$PY_SHA.part" "$PY_URL" >>"$LOGS/runtimes.log" 2>&1
  rc=$?
  [ "$rc" = 0 ] || download_failed "$rc"
  if [ -n "$PY_BYTES" ] && [ "$(wc -c <"$DL/$PY_SHA.part" | tr -cd 0-9)" != "$PY_BYTES" ]; then
    bad_download "$DL/$PY_SHA.part"
  fi
  [ "$(sha_of "$DL/$PY_SHA.part")" = "$PY_SHA" ] || bad_download "$DL/$PY_SHA.part"
  mv -f "$DL/$PY_SHA.part" "$target"
  ARCHIVE="$target"
}

wrong_python() {
  local name="Python $PY_VERSION"
  say "$name vừa cài không chạy đúng bản đã ghi trong file cài, nên chương trình đã xóa bản đó."
  say "Anh báo người gửi file."
  leave 1
}

install_python() {
  local dest tmpx
  if [ -z "$PY_URL" ] || [ "${#PY_SHA}" != 64 ] || [ -n "$(printf '%s' "$PY_SHA" | tr -d 0-9a-f)" ]; then
    say "File cài thiếu thông tin phiên bản của Python, nên chương trình dừng ở đây. Anh báo người gửi file."
    leave 2
  fi
  dest="$RT/python-$PY_VERSION-$TRIPLE"
  mkdir -p "$RT" "$LOGS"
  if [ "$(run_version "$dest/bin/python3")" != "$PY_VERSION" ]; then
    python_archive
    tmpx="$RT/.tmp-python-$PY_VERSION"
    rm -rf "$tmpx"
    mkdir -p "$tmpx"
    if ! tar -xzf "$ARCHIVE" -C "$tmpx" 2>>"$LOGS/runtimes.log" || [ ! -d "$tmpx/python" ]; then
      rm -rf "$tmpx"
      say "Chưa cài được Python $PY_VERSION; chi tiết ở ~/ThomHouse/logs/runtimes.log."
      say "Anh chạy lại: $CMD"
      leave 1
    fi
    if [ "$(run_version "$tmpx/python/bin/python3")" != "$PY_VERSION" ]; then
      rm -rf "$tmpx"
      rm -f "$ARCHIVE"
      wrong_python
    fi
    rm -rf "$dest"
    mv "$tmpx/python" "$dest" || leave 1
    rm -rf "$tmpx"
  fi
  ln -sfh "python-$PY_VERSION-$TRIPLE" "$RT/python" || leave 1
  if [ "$(run_version "$RT/python/bin/python3")" != "$PY_VERSION" ]; then
    rm -rf "$dest"
    wrong_python
  fi
}

if needs python; then
  install_python
fi

if [ "$OPT_PY_ONLY" = 1 ]; then
  say "Đã cài Python $PY_VERSION cho chatbot."
  exit 0
fi

# ---------------------------------------------------------------- exec the Python CLI, same PID
CONSENTED="$(printf '%s' "$NEED" | tr ' ' ',')"
set -- install --from-bootstrap
[ -n "$CONSENTED" ] && set -- "$@" --consented "$CONSENTED"
[ -n "$RELEASE_FILE" ] && set -- "$@" --release-file "$RELEASE_FILE"
[ "$OPT_YES" = 1 ] && set -- "$@" --yes
[ "$OPT_SKIP_HUMAN" = 1 ] && set -- "$@" --skip-human
[ "$OPT_TRUST" = 1 ] && set -- "$@" --trust-channel
[ -n "$OPT_MENU" ] && set -- "$@" --menu "$OPT_MENU"
[ -n "$OPT_MOVE_IN" ] && set -- "$@" --move-in "$OPT_MOVE_IN"
build_env
exec /usr/bin/env -i "${ENV_ARGS[@]}" "$RT/python/bin/python3" -I "$REL/install/thomhouse.py" "$@"
