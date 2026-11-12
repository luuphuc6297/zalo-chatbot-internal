#!/usr/bin/env bash
# Deploy the thom house bot server to Cloudflare and wire the Mac runner to it.
#
#   CLOUDFLARE_ACCOUNT_ID=<id> scripts/deploy_cloudflare.sh
#
# Reads Zalo credentials from .secrets/zalo.env (copy .secrets/zalo.env.example, fill it in yourself).
# Without that file the Worker is deployed with ZALO_MODE=mock so the public URLs exist for the Zalo
# developer console; rerun the script after filling the file to switch to ZALO_MODE=real.
# Generated tokens live in .secrets/prod.env (chmod 600). No secret is printed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVER="$ROOT/apps/server"
SECRETS="$ROOT/.secrets"
mkdir -p "$SECRETS" && chmod 700 "$SECRETS"
: "${CLOUDFLARE_ACCOUNT_ID:?set CLOUDFLARE_ACCOUNT_ID (see: pnpm -C apps/server exec wrangler whoami)}"
export CLOUDFLARE_ACCOUNT_ID
W() { (cd "$SERVER" && pnpm exec wrangler "$@"); }

# 1. D1 database (create once, then pin its id in wrangler.toml)
if grep -q 'database_id = "00000000-0000-0000-0000-000000000000"' "$SERVER/wrangler.toml"; then
  DBID="$(W d1 list --json | python3 -c 'import json,sys; print(next((d["uuid"] for d in json.load(sys.stdin) if d["name"]=="thomhouse-main"),""))')"
  if [ -z "$DBID" ]; then
    W d1 create thomhouse-main >/dev/null
    DBID="$(W d1 list --json | python3 -c 'import json,sys; print(next(d["uuid"] for d in json.load(sys.stdin) if d["name"]=="thomhouse-main"))')"
  fi
  sed -i '' "s/database_id = \"00000000-0000-0000-0000-000000000000\"/database_id = \"$DBID\"/" "$SERVER/wrangler.toml"
  echo "D1 thomhouse-main: $DBID"
fi
W d1 migrations apply thomhouse-main --remote

# 2. Tokens for the runner and the staff app (generated once)
if [ ! -f "$SECRETS/prod.env" ]; then
  umask 077
  printf 'RUNNER_TOKEN=%s\nSTAFF_TOKEN=%s\n' "$(openssl rand -hex 32)" "$(openssl rand -hex 32)" > "$SECRETS/prod.env"
fi
set -a; . "$SECRETS/prod.env"; set +a

MODE=mock
if [ -f "$SECRETS/zalo.env" ]; then set -a; . "$SECRETS/zalo.env"; set +a; fi
if [ -n "${ZALO_APP_ID:-}" ] && [ -n "${ZALO_APP_SECRET_KEY:-}" ] && [ -n "${ZALO_OA_SECRET_KEY:-}" ] && [ -n "${ZALO_OA_ID:-}" ]; then
  MODE=real
else
  [ -f "$SECRETS/zalo.env" ] && echo "note: .secrets/zalo.env is incomplete (need all four values); deploying in mock mode"
  ZALO_APP_ID=dev-app-id; ZALO_OA_ID=dev-oa-id; ZALO_OA_SECRET_KEY=dev-oa-secret; ZALO_APP_SECRET_KEY=dev-app-secret
fi
for k in RUNNER_TOKEN STAFF_TOKEN ZALO_APP_ID ZALO_OA_ID ZALO_OA_SECRET_KEY ZALO_APP_SECRET_KEY; do
  printf '%s' "${!k}" | W secret put "$k" >/dev/null
done

# 3. Deploy
OUT="$(W deploy --var "ZALO_MODE:$MODE" 2>&1)"
URL="$(printf '%s\n' "$OUT" | grep -Eo 'https://[a-zA-Z0-9.-]+\.workers\.dev' | head -1)"
[ -n "$URL" ] || { printf '%s\n' "$OUT" | tail -20; echo "deploy URL not found"; exit 1; }
printf 'SERVER_URL=%s\n' "$URL" > "$SECRETS/server-url.env"

# 4. Load the menu/catalog built into the Worker (data/services.json at build time)
curl -fsS -X POST "$URL/staff/catalog/load-embedded" -H "authorization: Bearer $STAFF_TOKEN" -H 'x-staff-id: deploy' >/dev/null

# 5. Runner config (Mac): server URL + runner token
umask 077
cat > "$ROOT/apps/runner/.env" <<EOF
SERVER_URL=$URL
RUNNER_TOKEN=$RUNNER_TOKEN
RUNNER_ID=studio-mac
EOF

# 6. OA authorization link (contains the staff key: kept in a file, not printed)
printf '%s/zalo/oauth/start?key=%s\n' "$URL" "$STAFF_TOKEN" > "$SECRETS/oauth-start-url.txt"

echo "Deployed: $URL (ZALO_MODE=$MODE)"
echo "Zalo developer console:"
echo "  Webhook URL:      $URL/zalo/webhook"
echo "  OAuth callback:   $URL/zalo/oauth/callback"
echo "Authorize the OA: open the URL stored in .secrets/oauth-start-url.txt"
echo "Staff app: server URL above, staff token in .secrets/prod.env"
