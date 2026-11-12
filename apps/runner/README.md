# apps/runner — model runner on the studio Mac

Python 3.11+, stdlib only, no pip installs. The runner polls the Cloudflare backend over outbound HTTPS, drafts
replies with `claude -p` on the owner's Claude subscription pool (`scripts/runner/claude_pool.py`, reused), and
posts drafts or failures back. It never sends anything to Zalo. Design: `design/subscription-runner.md`; wire
contract: `docs/contracts.md` ("Runner API").

```bash
cd apps/runner
cp .env.example .env                      # SERVER_URL, RUNNER_TOKEN (or Keychain), RUNNER_ID
python3 ../../scripts/runner/claude_pool.py add <label>   # once per account, then log it in
python3 -m runner.main status             # pool + login status, posted to /runner/status
python3 -m runner.main once               # claim and process one job
python3 -m runner.main run                # poll forever; Ctrl-C finishes running jobs, Ctrl-C again kills them
python3 -m runner.main forget cnv_...     # delete a conversation's workdir, session files and room map file
python3 -m runner.main rooms-setup        # two-bot rooms: write the platform config.json and the credentials file
python3 -m unittest discover -s tests -t .
```

## Modules

| File | Job |
|---|---|
| `runner/config.py` | env + `.env` (+ Keychain token) |
| `runner/api.py` | Runner API client (urllib) |
| `runner/poller.py` | claim loop, heartbeats, concurrency cap, backoff, shutdown, status + manual account switch |
| `runner/claude_runner.py` | flags/env of `scripts/eval/run_eval_cli.py`, calls `claude_pool.run`, error kinds, resume retry |
| `runner/prompt.py` | `GET /runner/prompt` cache by `prompt_hash`, user text for one turn |
| `runner/sessions.py` | per-conversation workdir (internal `cnv_` id), session aging, deletion of session files |
| `runner/mcp_proxy.py` | stdio MCP server started by `claude -p`; forwards tool calls to `POST /runner/tools/:name` |
| `runner/tools-schema.json` | fallback copy of the tools: the eight business tools of the direct engine plus `get_customer_profile`, which only the rooms tools server lists |
| `runner/room_engine.py` | two-bot rooms engine: one room turn per job on the rooms platform, validation of the reply, fallback to the direct engine, observation loop |
| `runner/room_setup.py` | `rooms-setup` (platform `config.json`, `rooms/credentials.json`) and the team file with the Vietnamese instructions of the two bots |
| `runner/room_tools.py` | stdio MCP server started by the rooms platform; nine tools, each call checked against a per-turn ticket, then forwarded to `POST /runner/tools/:name` |

## Error kinds sent to `/fail`

| What happened | `error_kind` |
|---|---|
| every tried account hit its limit / lost its login / is blocked | `limited` / `login_expired` / `blocked` |
| no account usable, or tried accounts failed for different reasons | `no_account` (runner also stops claiming) |
| `claude -p` ran past `CLAUDE_TIMEOUT_S` (process group killed) | `timeout` |
| `--resume` failed, retried once with a new session, retry failed too | `session_broken` (`session_broken: true`) |
| other `is_error` / non-zero exit on a new session | `model_error` |
| empty result / `stop_reason: refusal` | `empty_output` / `refusal` |
| runner stopped while the job ran (second Ctrl-C) | `cancelled` |
| anything else, including `claude` missing from PATH | `internal` |

A heartbeat answer `cancel: true` or a lost lease kills the call and posts nothing.

## Two-bot rooms (`THOMHOUSE_DRAFT_ENGINE=rooms`)

Contract: `docs/contracts.md` section 14.8; operator commands: `docs/run-local.md`; guide for the owner (Vietnamese):
`docs/rooms.md`. Rooms run only when this setting is `rooms` and the server flag `rooms_enabled` is `true`. The
default engine is `claude`; any other value than `claude` or
`rooms` stops the runner at startup with `config error: THOMHOUSE_DRAFT_ENGINE must be one of claude, rooms`.

With `rooms`, a job is answered inside a room of the rooms platform (OpenMausBot, `tools/openmausbot`) by two
bots: "Bot dịch vụ" (lead, the eight business tools) and "Bot khách hàng" (customer profile, the one tool
`get_customer_profile`). One turn:

1. read `POST /runner/rooms/feed` for the conversation; `enabled: false`, or an answer without an entry for this
   conversation (the server finds it not eligible for a room: not a one-to-one personal chat, no consent, a minor,
   an internal contact), means the direct engine runs, whatever `ROOM_FALLBACK` says;
2. write `rooms/team.json` and run `team apply` when the definition of the two bots changed (reply rules, pool
   account, model) or the conversation has no room yet; the team file creates the room `zalo-<cnv id>`. When the
   reply rules are in `CLAUDE.md` (see below), copy that file into the lead bot's platform workspace;
3. a new room is seeded once with the earlier messages of the conversation, as text no bot answers;
4. write the ticket `rooms/tickets/tk_<32 hex>.json` bound to the leased job;
5. send the turn message that calls the lead bot, then acknowledge the copied rows (`POST /runner/rooms/ack`).
   The message says whether a bot message has already reached the customer, so the lead introduces itself as
   the AI assistant only in its first reply, as the direct engine does; the room map keeps that answer
   (`bot_replied`);
6. wait for the lead bot's reply and validate it (no ticket, no bot name, no at-sign mention, written by the
   lead bot, profile read through the ticket);
7. post the reply as the draft with `session_id` `room.<cnv id>`, then delete the ticket.

Any failure of a room turn (platform error, timeout, rejected reply) runs the direct `claude -p` engine for the
same job. A `room.` session id is not resumed, and the history comes from the seed feed. After
`THOMHOUSE_DRAFT_ENGINE` is set back to `claude`, the direct engine does not resume a `room.` session id either: it
starts a new session and reports `session_restarted`. `ROOM_FALLBACK=fail`
posts a failure instead. A cancelled job or a lost lease interrupts the room job and posts nothing.

The observation loop (`ROOM_OBSERVE_EVERY_S`, 0 turns it off) copies messages that need no reply into the
rooms as text without a bot mention, so the bots keep the context. It shares a per-conversation lock with
draft turns. While the server answers `enabled: false` (flag `rooms_enabled` off, or migration 0010 missing) a
tick does nothing and the loop asks again after max(`ROOM_OBSERVE_EVERY_S`, 300 s), so turning the flag on needs no
runner restart.

Run `python3 -m runner.main rooms-setup` before the platform starts and after every change of the account
pool (`scripts/start_local.sh` runs it each time it starts the platform; restart the platform after a pool change,
since it is not known whether the platform reloads its config). It needs the runner token, exits 2 and leaves the
file untouched when an existing `config.json` is not a JSON object, works offline and writes, both with mode 0600:

- `<OPENMAUSBOT_DATA_DIR>/config.json`: one instance `thom-<label>` per pool account plus `claude`,
  `mcpServers.thom` (this repository's `runner/room_tools.py`), `features.claudeUserMcp: false`. Unknown keys,
  other instances and other MCP servers of an existing file are kept.
- `$THOMHOUSE_BOT_HOME/rooms/credentials.json`: backend URL, runner id and token, read only by
  `room_tools.py`. The token is not in the platform config and not in a bot's environment.

Files under `$THOMHOUSE_BOT_HOME/rooms`: `credentials.json`, `team.json`, `state.json` (what was applied),
`tools.json` (the server's current tool definitions), `<cnv id>.json` (room map, removed by `forget`),
`tickets/`, `work/lead` and `work/customer` (the bots' working folders; `work/lead/CLAUDE.md` holds the reply
rules when they are longer than the platform's 24,000 byte limit for bot instructions).

The platform runs a bot's room turn in `<OPENMAUSBOT_DATA_DIR>/workspaces/<bot id>`, not in the bot's configured
folder, so a room turn never reads `work/lead/CLAUDE.md`. After every `team apply`, and before a turn when the text
or the lead bot's id changed, the runner looks the lead bot's id up (`bots --json`; `<OPENMAUSBOT_DATA_DIR>/bots.json`,
read only, when the CLI fails) and writes the same text to `workspaces/<lead bot id>/CLAUDE.md` (mode 0600; a folder
it creates gets 0700). The file is not rewritten when it already holds the same text. A copy of the rules (a file
that starts with the rules header) in any other workspace, such as the customer bot's, is removed. A lead bot that
cannot be found is a room failure: the direct engine answers and the next turn applies the team again.

`claude_pool.py` writes `accounts.json` and `account-state.json` atomically with mode 0600. `last_error` holds only
an error kind (`limited`, `login_expired`, `blocked`, `timeout`, `cli_error`, `parse_error`), never the CLI's output,
which can echo customer text; a raw text left by an older version is reduced to its kind on the next write.

Settings: `OPENMAUSBOT_BIN`, `OPENMAUSBOT_DATA_DIR` (default `$THOMHOUSE_BOT_HOME/openmausbot`),
`OPENMAUSBOT_NODE_DIR`, `ROOM_TURN_TIMEOUT_S` (240), `ROOM_OBSERVE_EVERY_S` (30), `ROOM_FALLBACK` (`claude`),
`ROOM_REQUIRE_PROFILE_READ` (1), `ROOM_CUSTOMER_MODEL` (empty: same model as the lead bot). The header of
`runner/config.py` describes each one.

## Known limits

- Tests use a fake `claude` (`tests/fake_bin/claude`) and a stub backend; the runner has not run against the real
  server or the real `claude` yet.
- The rooms engine is tested with a fake platform CLI (`tests/fake_bin/openmausbot`). Against the real platform
  only the generated team file was checked, with `team apply --dry-run`; no real room turn has run yet.
- `forget` removes the runner's room map file. The room on the platform, which holds copied customer text, is
  not deleted by the runner.
- Session files are deleted only under `$THOMHOUSE_BOT_HOME/sessions`. An account added with `add-default` keeps
  its sessions in `~/.claude/projects`, which the runner never touches.
- When the runner itself restarts a session the server handed out (20 customer messages, 24 h idle, catalog
  change, broken resume), the job carries no `history`, so the new session sees only what the job payload has.
