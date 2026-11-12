# apps/zalo-bridge — personal Zalo channel on the owner's Mac

Python 3.11+, stdlib only. The bridge connects the local server to the owner's **personal** Zalo account through
the unofficial engine `@ardennguyen/zalo-agent-cli` 2.5.9 (license CC-BY-NC-SA-4.0; this is a local,
non-commercial app). The Zalo OA path stays in the server code but is not used.

```
customer ──Zalo──> zalo-agent listen -d ──webhook (Bearer + HMAC)──> server POST /zalo/personal/webhook
server outbox (ZALO_MODE=personal, status queued) <──claim── bridge ──zalo-agent msg send──> customer
                                                   ──result (sent | failed | unknown)──>
```

The server owns the conversation logic (consent gate, debounce, drafts, checker, handoffs). The bridge only
moves outbox rows to Zalo and supervises the listener. Wire contract: `docs/contracts.md`, section 12
"Personal Zalo channel". Every result carries the claim's `attempt`; an idle claim waits the server's
`poll_after_ms` (2 s, or 5 s while `outbound_enabled=false`). Rows with `thread_type` other than 0 are reported
`failed` without sending.

## Run

`scripts/start_local.sh` does everything below and `scripts/stop_local.sh` stops it. By hand:

```bash
cd apps/zalo-bridge
cp .env.example .env                       # or: python3 -m bridge.main init-env (writes all three env files)
python3 -m bridge.main doctor              # engine, Zalo login, listener, server, token
python3 -m bridge.main listener start      # zalo-agent listen -d --filter user -e message --webhook ...
python3 -m bridge.main run                 # claim -> send -> result, forever; Ctrl-C finishes the current send
python3 -m bridge.main once                # one row, JSON summary
python3 -m bridge.main status              # GET /bridge/status
python3 -m bridge.main listener stop --only-ours
python3 -m bridge.main sync-labels [--dry-run]   # Zalo labels Khách hàng / Quản lý / Nhân viên -> contact roles
python3 -m bridge.main rooms-node          # directory of a node 24+ for the optional rooms platform (exit 1: none)
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t .
```

`run` also copies the Zalo labels to the server's contact roles (docs/contracts.md section 14.3) at start and every
`LABEL_SYNC_EVERY_S` seconds (default 900, 0 disables it), on its own thread with a 45 s engine timeout, so a slow or
failing sync never holds up a send. `sync-labels` does one sync by hand: it reads `zalo-agent --json label list`,
maps the three labels (whole label text, compared without accents and case) to `customer`, `manager`, `staff`, and
posts the complete list to `POST /staff/roles/import`. Nothing is posted when the engine fails or its output is not
understood, so the server never loses roles because of a bad read. It uses `STAFF_TOKEN` from the environment, else
from `apps/server/.dev.vars` (only for a local `SERVER_URL`), and prints counts only. Exit codes: 0 synced (or the
dry run read the labels), 1 engine or server failure, 2 no staff token.

The QR login is the one step only a person can do:
`<repo>/tools/zalo-agent/node_modules/.bin/zalo-agent login`.

## Modules

| File | Job |
|---|---|
| `bridge/config.py` | env + `.env` (env wins) |
| `bridge/api.py` | Bridge API client (urllib, `User-Agent: thomhouse-bridge/1.0`, `X-Bridge-Id`) |
| `bridge/engine.py` | runs `zalo-agent --json ...` with stdin closed, own process group, timeout, cleaned env |
| `bridge/sender.py` | `msg send -t 0 -- <threadId> <text>` and the sent / failed / unknown classification |
| `bridge/journal.py` | on-disk journal that makes every row go out at most once |
| `bridge/poller.py` | claim loop, pacing, backoff, login pause, result retries, signals |
| `bridge/listener.py` | `listener start/status/stop` around `zalo-agent listen` |
| `bridge/doctor.py` | health checks; the last one, `room_platform`, reports the optional rooms platform and warns only when the runner is set to `THOMHOUSE_DRAFT_ENGINE=rooms` and a part is missing |
| `bridge/envfiles.py` | `init-env`: `.dev.vars`, runner `.env`, bridge `.env` that agree; adds the room settings of docs/contracts.md 14.8 to the runner `.env` and `LABEL_SYNC_EVERY_S` to the bridge `.env` when they are missing (a commented key counts as present) |
| `bridge/labels.py` | label sync (`sync-labels`, and the periodic sync of `run`) |
| `bridge/rooms.py` | the optional rooms platform as seen from this machine: install path, node 24+ lookup (`PATH`, then `~/.nvm/versions/node`), port 8799 |

## How a send is classified

| What zalo-agent did | Result posted |
|---|---|
| JSON with `message.msgId` | `sent` with `zalo_msg_id` (a split send also carries `part_msg_ids`, every part's msgId) |
| `{"error": ...}` saying not logged in; claiming then pauses `LOGIN_PAUSE_S` | `failed` (`not_logged_in: ...`) |
| `{"error": ...}` from Zalo, a usage error, invalid thread id, engine missing | `failed` |
| timeout, killed by a second Ctrl-C, transport error, partial split send, output that is not the expected JSON | `unknown` |
| zca-js errors raised after Zalo answered: `Failed to parse response data`, `Request failed with status code 5xx` | `unknown` |

The server never retries `unknown`; staff decides. The journal (`$THOMHOUSE_BOT_HOME/bridge/journal.jsonl`, no text
and no thread ids) records `sending` before zalo-agent starts. If the server hands out a row the journal already
has as `sent`, `unknown` or `sending`, the bridge re-posts that outcome (`sending` becomes `unknown`) and does not
send again, unless the claim item's `requeued_at` is later than the journal entry (staff pressed requeue in the console or called `POST /staff/outbox/:id/decide`): then the row is sent again. A `failed` row handed out again is sent again, because the server chose to retry it.

One bridge per state directory: `run` and `once` take an exclusive `flock` on `<state_dir>/bridge.lock` and exit 5
when another process holds it (two processes would each keep their own journal in memory and could send a row twice).
The server paces the account too: an hourly limit, a gap per thread and a maximum age for queued automatic rows
(docs/contracts.md section 12); a held-back claim answers `reason: "rate_limited"` and the bridge waits
`poll_after_ms`.

## Engine facts checked in the source (v2.5.9)

- `--json` prints one JSON value; most failures print `{"error": ...}` and still exit 0.
- A text `msg send` logs in over HTTP and sends over HTTP. It opens no WebSocket, so it runs beside the
  `listen` daemon. Only uploads go through the daemon channel. Each send therefore does its own HTTP login.
- Commander stops option parsing at `--` (checked with commander 14.0.3; the engine depends on `^15.0.0`).
- `listen -d` spawns the daemon with the parent's environment, so `ZALO_WEBHOOK_SECRET` reaches it without a flag.
  The engine signs with `Authorization: Bearer <secret>` and `X-Zalo-Signature: sha256=<HMAC of the body>`.
- `ZALO_AGENT_NO_UPDATE_CHECK=1` skips the npm version check before each command; the bridge sets it.

## Known limits

- Tests use a fake `zalo-agent` (`tests/fake_bin/zalo-agent`) and a fake server. The bridge has not run against
  the real engine, a real Zalo account or the real server build.
- The label sync was tested only against a stub server. Whether `zalo-agent label list` can run while the listener
  holds the account's session is not verified; an account with more than 5 000 labelled contacts cannot be synced as
  one complete list (nothing is posted). A personal id longer than 32 digits is skipped and counted.
- The listener is "ours" when the last `starting daemon:` line in the engine's `daemon.log` contains the bridge
  webhook URL. A daemon started another way is never stopped by the bridge.
- `msg send` with `-t 0` only: group threads are ignored by the webhook and never get outbox rows.
