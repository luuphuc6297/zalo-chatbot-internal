"""Two-bot rooms, the parts around the engine (docs/contracts.md 14.6 and 14.8): the stdio tools server
room_tools.py end to end against the stub backend, the `rooms-setup` command and its files, the rooms settings, the
pin that keeps the direct engine on its eight tools, the room map file in `forget`, and the team file helpers."""

from __future__ import annotations

import ast
import json
import os
import stat
import subprocess
import sys
import time
import unittest
from pathlib import Path

from tests.helpers import PROFILE_RESULT, RUNNER_ID, TOKEN, RoomsTestCase, RunnerTestCase, make_job

from runner import mcp_proxy, room_setup as setup, room_tools
from runner.claude_runner import MCP_PROXY, ClaudeRunner, load_pool
from runner.config import Config, ConfigError, DEFAULT_OPENMAUSBOT_BIN
from runner.contract import TOOL_NAMES
from runner.poller import Runner
from runner.prompt import SHIPPED_TOOLS, mcp_tools, shipped_tools
from runner.sessions import SessionStore

APP = Path(__file__).resolve().parent.parent
TICKET = "tk_" + "0123456789abcdef" * 2
PROFILE = "get_customer_profile"


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def call(msg_id: int, name: str, arguments) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "method": "tools/call", "params": {"name": name, "arguments": arguments}}


def tool_result(msg: dict) -> tuple[object, bool]:
    res = msg["result"]
    return json.loads(res["content"][0]["text"]), res["isError"]


class RoomToolsTest(RunnerTestCase):
    """room_tools.py as the platform starts it: `python3 -I <file>`, THOMHOUSE_BOT_HOME in the environment, the
    bot's own folder as the working directory."""

    def setUp(self):
        super().setUp()
        self.tickets = self.home / "rooms" / "tickets"
        self.tickets.mkdir(parents=True)
        self.bot_dir = self.tmp / "workspaces" / "bot_lead"
        self.bot_dir.mkdir(parents=True)
        self.write_credentials()
        self.output = ""

    def write_credentials(self, **kw):
        creds = {"api_url": self.backend.url, "runner_id": RUNNER_ID, "token": TOKEN, **kw}
        (self.home / "rooms" / "credentials.json").write_text(json.dumps(creds))

    def write_ticket(self, ticket=TICKET, job_id="job_77", expires_in_ms=60_000, raw=None, **extra):
        record = {"job_id": job_id, "conversation_id": "cnv_abc", "expires_at": int(time.time() * 1000) + expires_in_ms,
                  **extra}
        (self.tickets / f"{ticket}.json").write_text(raw if raw is not None else json.dumps(record))

    def session(self, msgs, env=None) -> list[dict]:
        full_env = {"PATH": os.environ.get("PATH", ""), "THOMHOUSE_BOT_HOME": str(self.home), **(env or {})}
        stdin = "".join(json.dumps(m) + "\n" for m in msgs)
        p = subprocess.run([sys.executable, "-I", str(setup.ROOM_TOOLS)], input=stdin, capture_output=True, text=True,
                           env=full_env, cwd=self.bot_dir, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.output = p.stdout + p.stderr
        self.assertNotIn(TOKEN, self.output)            # the token is never in a tool result or an error text
        return [json.loads(l) for l in p.stdout.splitlines() if l.strip()]

    def list_tools(self, env=None) -> list[dict]:
        return self.session([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}], env=env)[0]["result"]["tools"]

    def call_logs(self) -> list[Path]:
        return sorted(self.tickets.glob("*.calls.jsonl"))

    def test_lists_nine_tools_each_with_a_required_ticket(self):
        out = self.session([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "ping"},
            {"jsonrpc": "2.0", "id": 4, "method": "resources/list"},
        ])
        self.assertEqual([m["id"] for m in out], [1, 2, 3, 4])          # the notification gets no answer
        self.assertEqual(out[0]["result"]["serverInfo"]["name"], "thom")
        self.assertEqual(out[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(out[2]["result"], {})
        self.assertEqual(out[3]["error"]["code"], -32601)

        tools = out[1]["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], [*TOOL_NAMES, PROFILE])
        self.assertEqual(room_tools.TOOL_NAMES, setup.ROOM_TOOL_NAMES)
        shipped = {t["name"]: t for t in shipped_tools()}
        for t in tools:
            with self.subTest(tool=t["name"]):
                schema, base = t["inputSchema"], shipped[t["name"]]["input_schema"]
                self.assertEqual(schema["type"], "object")
                self.assertEqual(schema["properties"]["ticket"]["type"], "string")
                self.assertTrue(schema["properties"]["ticket"]["description"])
                self.assertEqual(schema["required"], [*base["required"], "ticket"])
                self.assertEqual({k: v for k, v in schema["properties"].items() if k != "ticket"},
                                 base.get("properties") or {})
                self.assertIs(schema["additionalProperties"], False)
                self.assertEqual(t["description"], shipped[t["name"]]["description"])
        profile = tools[-1]["inputSchema"]
        self.assertEqual((sorted(profile["properties"]), profile["required"]), (["ticket"], ["ticket"]))
        self.assertEqual(self.backend.requests, [])

    def test_valid_ticket_forwards_the_call_without_the_ticket_field(self):
        self.write_ticket()
        out = self.session([
            call(1, "quote_price", {"ticket": TICKET, "service_id": "goi-dau"}),
            call(2, PROFILE, {"ticket": TICKET}),
        ])
        quote, quote_err = tool_result(out[0])
        self.assertFalse(quote_err)
        self.assertEqual(quote["price_text"], "199.000đ")
        self.assertEqual(tool_result(out[1]), (PROFILE_RESULT, False))

        req = self.backend.find("/runner/tools/quote_price")[0]
        self.assertEqual(req["body"], {"job_id": "job_77", "input": {"service_id": "goi-dau"}})
        self.assertEqual((req["auth"], req["runner_id"]), (f"Bearer {TOKEN}", RUNNER_ID))
        self.assertEqual(self.backend.find(f"/runner/tools/{PROFILE}")[0]["body"], {"job_id": "job_77", "input": {}})
        self.assertEqual(len(self.backend.requests), 2)
        self.assertNotIn(TICKET, json.dumps(self.backend.requests))    # the ticket never reaches the server

        log = self.tickets / f"{TICKET}.calls.jsonl"
        lines = [json.loads(l) for l in log.read_text().splitlines()]
        self.assertEqual([(l["tool"], l["is_error"], l["bot"]) for l in lines],
                         [("quote_price", False, "bot_lead"), (PROFILE, False, "bot_lead")])
        self.assertTrue(all(isinstance(l["at"], int) and sorted(l) == ["at", "bot", "is_error", "tool"] for l in lines))
        self.assertEqual(mode(log), 0o600)
        self.assertTrue((self.tickets / f"{TICKET}.json").exists())    # the runner deletes the ticket, not the tools

    def test_invalid_and_expired_tickets_forward_nothing(self):
        def tk(n: int) -> str:
            return f"tk_{n:032x}"

        self.write_ticket(tk(1), expires_in_ms=-1000)                                   # expired
        self.write_ticket(tk(2), job_id="")                                             # no job
        self.write_ticket(tk(3), raw="{broken")
        self.write_ticket(tk(4), raw=json.dumps(["job_77"]))
        self.write_ticket(tk(5), raw=json.dumps({"job_id": "job_77", "expires_at": "9999999999999"}))
        self.write_ticket(tk(6), raw=json.dumps({"job_id": "job_77", "expires_at": True}))
        self.write_ticket(tk(7), raw=json.dumps({"job_id": 77, "expires_at": 9_999_999_999_999}))
        self.write_ticket(tk(8), raw=json.dumps({"job_id": "job_77"}))
        (self.tickets / "tk_123.json").write_text(json.dumps({"job_id": "job_77", "expires_at": 9_999_999_999_999}))
        cases = {
            "missing": {"service_id": "goi-dau"},
            "not a string": {"ticket": 123},
            "empty": {"ticket": ""},
            "malformed": {"ticket": "tk_123"},
            "upper-case hex": {"ticket": "tk_" + "ABCDEF0123456789" * 2},
            "trailing text": {"ticket": tk(9) + "x"},
            "trailing newline": {"ticket": tk(9) + "\n"},
            "path": {"ticket": "../credentials"},
            "unknown": {"ticket": tk(9)},
            "expired": {"ticket": tk(1)},
            "no job id": {"ticket": tk(2)},
            "broken file": {"ticket": tk(3)},
            "file is a list": {"ticket": tk(4)},
            "expiry is a string": {"ticket": tk(5)},
            "expiry is a boolean": {"ticket": tk(6)},
            "job id is a number": {"ticket": tk(7)},
            "no expiry": {"ticket": tk(8)},
        }
        out = self.session([call(i, "quote_price", args) for i, args in enumerate(cases.values(), 1)]
                           + [call(99, PROFILE, "not an object")])
        self.assertEqual(len(out), len(cases) + 1)
        for name, msg in zip([*cases, "arguments are not an object"], out):
            with self.subTest(case=name):
                self.assertEqual(tool_result(msg), ({"error": "ticket_invalid"}, True))
        self.assertEqual(self.backend.requests, [])
        self.assertEqual(self.call_logs(), [])

    def test_ticket_expires_at_its_time(self):
        self.write_ticket(expires_in_ms=60_000)
        self.assertFalse(tool_result(self.session([call(1, PROFILE, {"ticket": TICKET})])[0])[1])
        self.write_ticket(expires_in_ms=0)
        self.assertEqual(tool_result(self.session([call(1, PROFILE, {"ticket": TICKET})])[0]),
                         ({"error": "ticket_invalid"}, True))
        self.assertEqual(len(self.backend.requests), 1)

    def test_credentials_come_from_the_file_never_from_the_environment(self):
        self.write_ticket()
        env = {"RUNNER_TOKEN": "env-token-must-not-be-used", "RUNNER_ID": "env-runner",
               "THOMHOUSE_API_URL": "http://127.0.0.1:9", "THOMHOUSE_JOB_ID": "job_env"}
        out = self.session([call(1, PROFILE, {"ticket": TICKET})], env=env)
        self.assertFalse(tool_result(out[0])[1])
        req = self.backend.requests[0]
        self.assertEqual((req["auth"], req["runner_id"]), (f"Bearer {TOKEN}", RUNNER_ID))
        self.assertEqual(req["body"]["job_id"], "job_77")

    def test_missing_credentials_are_a_tool_error_and_contact_nothing(self):
        self.write_ticket()
        creds = self.home / "rooms" / "credentials.json"
        for name, raw in (("no file", None), ("empty token", json.dumps({"api_url": self.backend.url,
                                                                           "runner_id": RUNNER_ID, "token": ""})),
                          ("broken file", "{broken"), ("a list", "[]")):
            with self.subTest(case=name):
                creds.unlink(missing_ok=True)
                if raw is not None:
                    creds.write_text(raw)
                out = self.session([call(1, "search_services", {"ticket": TICKET})])
                self.assertEqual(tool_result(out[0]),
                                 ({"error": "tool_unavailable", "code": "credentials_missing"}, True))
        self.assertEqual(self.backend.requests, [])
        lines = [json.loads(l) for l in self.call_logs()[0].read_text().splitlines()]
        self.assertEqual([(l["tool"], l["is_error"]) for l in lines], [("search_services", True)] * 4)

    def test_server_errors_are_tool_errors_without_the_token(self):
        self.write_ticket()
        self.write_credentials(token="wrong-secret-token")
        out = self.session([call(1, "search_services", {"ticket": TICKET})])
        self.assertEqual(tool_result(out[0]),
                         ({"error": "tool_unavailable", "code": "unauthorized", "http_status": 401}, True))
        self.assertNotIn("wrong-secret-token", self.output)
        self.assertNotIn(self.backend.url, self.output)

        self.write_credentials(api_url="http://127.0.0.1:9")
        out = self.session([call(1, "search_services", {"ticket": TICKET})])
        self.assertEqual(tool_result(out[0]), ({"error": "tool_unavailable", "code": "backend_unreachable"}, True))
        self.assertNotIn("127.0.0.1:9", self.output)

    def test_unknown_tool_is_refused_and_nothing_is_forwarded(self):
        self.write_ticket()
        out = self.session([call(1, "rm_rf", {"ticket": TICKET}),
                            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {}}])
        self.assertEqual(tool_result(out[0]), ({"error": "unknown_tool"}, True))
        self.assertEqual(tool_result(out[1]), ({"error": "unknown_tool"}, True))
        self.assertEqual(self.backend.requests, [])
        self.assertEqual(self.call_logs(), [])

    def test_server_definitions_in_the_rooms_folder_win_per_tool(self):
        new = {"name": "quote_price", "description": "MO TA MOI",
               "input_schema": {"type": "object", "properties": {"service_id": {"type": "string"}},
                                "required": ["service_id"], "additionalProperties": False}}
        extra = {"name": "rm_rf", "description": "x", "input_schema": {"type": "object"}}
        (self.home / "rooms" / "tools.json").write_text(json.dumps({"tools": [new, extra, "not a tool"]}))
        tools = self.list_tools()
        self.assertEqual([t["name"] for t in tools], [*TOOL_NAMES, PROFILE])
        by_name = {t["name"]: t for t in tools}
        self.assertEqual(by_name["quote_price"]["description"], "MO TA MOI")
        self.assertEqual(by_name["quote_price"]["inputSchema"]["required"], ["service_id", "ticket"])
        self.assertEqual(sorted(by_name["quote_price"]["inputSchema"]["properties"]), ["service_id", "ticket"])
        shipped = {t["name"]: t for t in shipped_tools()}
        self.assertEqual(by_name["search_services"]["description"], shipped["search_services"]["description"])

        (self.home / "rooms" / "tools.json").write_text("{broken")
        self.assertEqual([t["name"] for t in self.list_tools()], [*TOOL_NAMES, PROFILE])

    def test_tools_file_from_the_environment_replaces_both_sources(self):
        only = self.tmp / "only.json"
        only.write_text(json.dumps({"tools": [{"name": PROFILE, "description": "d", "input_schema": {"type": "object"}},
                                              {"name": "rm_rf", "description": "x"}]}))
        tools = self.list_tools(env={"THOMHOUSE_TOOLS_FILE": str(only)})
        self.assertEqual([(t["name"], t["inputSchema"]["required"]) for t in tools], [(PROFILE, ["ticket"])])

    def test_tools_server_is_one_file_on_the_standard_library(self):
        tree = ast.parse(setup.ROOM_TOOLS.read_text(encoding="utf-8"))
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0, "no relative import: the file is started on its own")
                modules.add((node.module or "").split(".")[0])
        self.assertLessEqual(modules - {"__future__"}, set(sys.stdlib_module_names))
        self.assertNotIn("runner", modules)


class RoomsSetupCommandTest(RoomsTestCase):
    """`python3 -m runner.main rooms-setup`: platform config.json and the credentials file."""

    EXISTING = {"port": 8799, "theme": "dark",
                "instances": {"thomhouse": {"driver": "claudeAgent", "config": {"configDir": "/x/scout"}},
                              "thom-old": {"driver": "claudeAgent"}},
                "mcpServers": {"thscout": {"command": "node", "args": ["scout.js"]},
                               "thom": {"command": "python3", "args": ["old.py"]}},
                "features": {"claudeUserMcp": True, "other": 1}}

    def cli(self, *args, **env):
        full = {**os.environ, "SERVER_URL": self.backend.url, "RUNNER_TOKEN": TOKEN, "RUNNER_ID": RUNNER_ID,
                "THOMHOUSE_BOT_HOME": str(self.home), "OPENMAUSBOT_DATA_DIR": str(self.platform_dir),
                "THOMHOUSE_DRAFT_ENGINE": "rooms", **env}
        return subprocess.run([sys.executable, "-m", "runner.main", *args], cwd=APP, env=full, capture_output=True,
                              text=True, timeout=60)

    def platform_config(self) -> dict:
        return json.loads((self.platform_dir / "config.json").read_text(encoding="utf-8"))

    def credentials(self) -> Path:
        return self.home / "rooms" / "credentials.json"

    def test_rooms_setup_writes_the_platform_config_and_the_credentials(self):
        config_path = self.platform_dir / "config.json"
        config_path.write_text(json.dumps(self.EXISTING))
        os.chmod(config_path, 0o644)
        p = self.cli("rooms-setup")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout), {"config": str(config_path), "credentials": str(self.credentials()),
                                                "instances": ["thom-a", "thom-b", "claude"], "mcp_server": "thom"})
        self.assertNotIn(TOKEN, p.stdout + p.stderr)

        conf = self.platform_config()
        self.assertEqual((conf["port"], conf["theme"]), (8799, "dark"))                # unknown keys are kept
        self.assertEqual(sorted(conf["instances"]), ["claude", "thom-a", "thom-b", "thomhouse"])
        self.assertEqual(conf["instances"]["thomhouse"], self.EXISTING["instances"]["thomhouse"])
        self.assertEqual(conf["instances"]["claude"], {"driver": "claudeAgent"})
        for label in ("a", "b"):
            self.assertEqual(conf["instances"][f"thom-{label}"],
                             {"driver": "claudeAgent", "displayName": f"thom house {label}",
                              "config": {"configDir": str(self.home / "accounts" / label), "tools": []}})
        self.assertEqual(conf["mcpServers"]["thscout"], self.EXISTING["mcpServers"]["thscout"])
        self.assertEqual(conf["mcpServers"]["thom"], {"command": sys.executable, "args": ["-I", str(setup.ROOM_TOOLS)],
                                                      "env": {"THOMHOUSE_BOT_HOME": str(self.home)}})
        self.assertTrue(setup.ROOM_TOOLS.is_absolute() and setup.ROOM_TOOLS.is_file())
        self.assertEqual(conf["features"], {"claudeUserMcp": False, "other": 1})
        self.assertNotIn(TOKEN, config_path.read_text())           # the token is not in the platform config

        self.assertEqual(json.loads(self.credentials().read_text()),
                         {"api_url": self.backend.url, "runner_id": RUNNER_ID, "token": TOKEN})
        self.assertEqual((mode(config_path), mode(self.credentials())), (0o600, 0o600))
        self.assertEqual((mode(self.home / "rooms"), mode(self.home / "rooms" / "tickets")), (0o700, 0o700))
        # atomic writes leave no temp file behind
        self.assertEqual(sorted(x.name for x in self.platform_dir.iterdir()), ["config.json", "fake-openmausbot.json"])
        self.assertEqual(sorted(x.name for x in (self.home / "rooms").iterdir()), ["credentials.json", "tickets", "work"])
        # offline: no call to the platform, to claude or to the server
        self.assertEqual((self.platform_calls(), self.claude_calls(), self.backend.requests), ([], [], []))

    def test_rooms_setup_can_run_again_and_follows_the_pool(self):
        self.assertEqual(self.cli("rooms-setup").returncode, 0)
        first = self.platform_config()
        self.assertEqual(sorted(first), ["features", "instances", "mcpServers"])        # no config.json before
        self.assertEqual(self.cli("rooms-setup").returncode, 0)
        self.assertEqual(self.platform_config(), first)

        accs = json.loads((self.home / "accounts.json").read_text())
        (self.home / "accounts.json").write_text(json.dumps([a for a in accs if a["label"] == "b"]))
        p = self.cli("rooms-setup")
        self.assertEqual(json.loads(p.stdout)["instances"], ["thom-b", "claude"])
        self.assertEqual(sorted(self.platform_config()["instances"]), ["claude", "thom-b"])

    def test_rooms_setup_refuses_a_platform_config_it_cannot_read(self):
        config_path = self.platform_dir / "config.json"
        for raw, message in (("{broken", "is not readable JSON"), ("[1, 2]", "must hold a JSON object")):
            with self.subTest(raw=raw):
                config_path.write_text(raw)
                p = self.cli("rooms-setup")
                self.assertEqual(p.returncode, 2)
                self.assertIn("config error:", p.stderr)
                self.assertIn(message, p.stderr)
                self.assertEqual(p.stdout, "")
                self.assertEqual(config_path.read_text(), raw)
                self.assertFalse(self.credentials().exists())
                self.assertNotIn(TOKEN, p.stderr)

    def test_rooms_setup_needs_the_runner_token(self):
        with self.assertRaisesRegex(setup.SetupError, "RUNNER_TOKEN"):
            setup.run_setup(self.rooms_config(runner_token=""), [])
        self.assertFalse((self.platform_dir / "config.json").exists())
        self.assertFalse((self.home / "rooms").exists())

    def test_platform_folder_defaults_to_the_bot_home(self):
        cfg = self.config()
        self.assertEqual(cfg.platform_data_dir, self.home / "openmausbot")
        self.assertEqual(cfg.rooms_dir, self.home / "rooms")
        out = setup.run_setup(cfg, load_pool(cfg.pool_path, cfg.home).accounts())
        self.assertEqual(out["config"], str(self.home / "openmausbot" / "config.json"))
        self.assertEqual(mode(self.home / "openmausbot" / "config.json"), 0o600)
        self.assertFalse((self.platform_dir / "config.json").exists())

    def test_platform_config_skips_bad_pool_rows_and_keeps_foreign_entries(self):
        cfg = self.rooms_config()
        accounts = [{"label": "vip 1", "config_dir": "/x/vip"}, {"label": ""}, "nonsense", {"label": "plain"}]
        conf = setup.platform_config(cfg, accounts, {"instances": "broken", "mcpServers": [], "features": None})
        self.assertEqual(sorted(conf["instances"]), ["claude", "thom-plain", "thom-vip-1"])
        self.assertEqual(conf["instances"]["thom-plain"]["config"], {"tools": []})
        self.assertEqual(sorted(conf["mcpServers"]), ["thom"])
        self.assertEqual(conf["features"], {"claudeUserMcp": False})
        kept = setup.platform_config(cfg, [], {"instances": {"claude": {"driver": "claudeAgent", "x": 1}}})
        self.assertEqual(kept["instances"], {"claude": {"driver": "claudeAgent", "x": 1}})


class RoomsConfigTest(RunnerTestCase):
    def load(self, **env) -> Config:
        base = {"RUNNER_TOKEN": "t", "THOMHOUSE_BOT_HOME": str(self.home)}
        return Config.load(env={**base, **env}, dotenv=self.tmp / "none")

    def test_defaults_keep_the_direct_engine(self):
        cfg = self.load()
        self.assertEqual((cfg.draft_engine, cfg.room_fallback), ("claude", "claude"))
        self.assertEqual((cfg.room_turn_timeout_s, cfg.room_observe_every_s), (240, 30))
        self.assertIs(cfg.room_require_profile_read, True)
        self.assertEqual((cfg.room_customer_model, cfg.openmausbot_node_dir), ("", ""))
        self.assertEqual(cfg.openmausbot_bin, DEFAULT_OPENMAUSBOT_BIN)
        self.assertIsNone(cfg.openmausbot_data_dir)
        self.assertEqual(cfg.platform_data_dir, self.home / "openmausbot")
        self.assertIsInstance(Runner(self.config()).claude, ClaudeRunner)      # no room engine by default
        self.assertIsNone(Runner(self.config()).start_observer())

    def test_rooms_settings_are_read_from_the_environment(self):
        cfg = self.load(THOMHOUSE_DRAFT_ENGINE=" Rooms ", OPENMAUSBOT_BIN="/opt/x/openmausbot",
                        OPENMAUSBOT_DATA_DIR="/data/omb", OPENMAUSBOT_NODE_DIR="/opt/node/bin",
                        ROOM_TURN_TIMEOUT_S="90", ROOM_OBSERVE_EVERY_S="0", ROOM_FALLBACK="FAIL",
                        ROOM_REQUIRE_PROFILE_READ="0", ROOM_CUSTOMER_MODEL=" claude-haiku-5-5 ")
        self.assertEqual((cfg.draft_engine, cfg.room_fallback), ("rooms", "fail"))
        self.assertEqual((cfg.openmausbot_bin, cfg.platform_data_dir), (Path("/opt/x/openmausbot"), Path("/data/omb")))
        self.assertEqual(cfg.openmausbot_node_dir, "/opt/node/bin")
        self.assertEqual((cfg.room_turn_timeout_s, cfg.room_observe_every_s), (90, 0))
        self.assertIs(cfg.room_require_profile_read, False)
        self.assertEqual(cfg.room_customer_model, "claude-haiku-5-5")
        self.assertEqual(self.load(ROOM_OBSERVE_EVERY_S="-5").room_observe_every_s, 0)

    def test_bad_rooms_settings_are_clear_errors(self):
        for env, message in (
            ({"THOMHOUSE_DRAFT_ENGINE": "room"}, "THOMHOUSE_DRAFT_ENGINE must be one of claude, rooms"),
            ({"THOMHOUSE_DRAFT_ENGINE": "openmausbot"}, "THOMHOUSE_DRAFT_ENGINE must be one of claude, rooms"),
            ({"ROOM_FALLBACK": "retry"}, "ROOM_FALLBACK must be one of claude, fail"),
            ({"ROOM_TURN_TIMEOUT_S": "0"}, "ROOM_TURN_TIMEOUT_S must be greater than 0"),
            ({"ROOM_TURN_TIMEOUT_S": "soon"}, "bad number in config"),
            ({"ROOM_OBSERVE_EVERY_S": "often"}, "bad number in config"),
            ({"ROOM_REQUIRE_PROFILE_READ": "maybe"}, "ROOM_REQUIRE_PROFILE_READ must be 1 or 0"),
        ):
            with self.subTest(env=env):
                with self.assertRaises(ConfigError) as ctx:
                    self.load(**env)
                self.assertIn(message, str(ctx.exception))
        with self.assertRaises(ConfigError):
            self.config(draft_engine="bogus")
        with self.assertRaises(ConfigError):
            self.config(room_fallback="bogus")

    def test_unknown_engine_stops_the_runner_at_startup(self):
        env = {**os.environ, "SERVER_URL": self.backend.url, "RUNNER_TOKEN": TOKEN, "RUNNER_ID": RUNNER_ID,
               "THOMHOUSE_BOT_HOME": str(self.home), "THOMHOUSE_DRAFT_ENGINE": "bogus"}
        self.backend.jobs.append(make_job())
        p = subprocess.run([sys.executable, "-m", "runner.main", "once"], cwd=APP, env=env, capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(p.returncode, 2)
        self.assertIn("config error: THOMHOUSE_DRAFT_ENGINE must be one of claude, rooms", p.stderr)
        self.assertEqual((self.backend.requests, self.claude_calls()), ([], []))


class DirectEngineToolsTest(RunnerTestCase):
    """The ninth tool belongs to the rooms only: the direct `claude -p` engine keeps its eight tools."""

    def proxy(self, msgs, **env) -> list[dict]:
        full = {"PATH": os.environ.get("PATH", ""), "THOMHOUSE_API_URL": self.backend.url, "RUNNER_TOKEN": TOKEN,
                "RUNNER_ID": RUNNER_ID, "THOMHOUSE_JOB_ID": "job_9", **env}
        stdin = "".join(json.dumps(m) + "\n" for m in msgs)
        p = subprocess.run([sys.executable, "-I", str(MCP_PROXY)], input=stdin, capture_output=True, text=True,
                           env=full, timeout=30)
        return [json.loads(l) for l in p.stdout.splitlines() if l.strip()]

    def test_shipped_schema_has_nine_tools_and_the_direct_filters_keep_eight(self):
        names = [t["name"] for t in shipped_tools()]
        self.assertEqual(names, [*TOOL_NAMES, PROFILE])
        self.assertEqual(len(TOOL_NAMES), 8)
        self.assertNotIn(PROFILE, TOOL_NAMES)
        self.assertEqual(mcp_proxy.TOOL_NAMES, TOOL_NAMES)
        self.assertEqual([t["name"] for t in mcp_tools(shipped_tools())], list(TOOL_NAMES))
        ninth = shipped_tools()[-1]["input_schema"]
        self.assertEqual((ninth["type"], ninth.get("properties") or {}, ninth["required"],
                          ninth["additionalProperties"]), ("object", {}, [], False))

    def test_direct_job_advertises_exactly_the_eight_old_tools(self):
        self.backend.jobs.append(make_job())
        out = Runner(self.config()).run_once()
        self.assertEqual(out["outcome"], "draft")
        prompt = self.backend.find("/runner/prompt", method="GET")
        self.assertTrue(prompt)                                       # the stub answered with all nine tools
        files = list(self.home.glob("prompt/*/tools.json"))
        self.assertEqual(len(files), 1)
        self.assertEqual([t["name"] for t in json.loads(files[0].read_text())["tools"]], list(TOOL_NAMES))
        flags = self.claude_calls()[0]["flags"]
        self.assertEqual(flags[flags.index("--allowedTools") + 1], "mcp__thom")
        self.assertNotIn(PROFILE, json.dumps(flags))
        self.assertFalse((self.home / "rooms").exists())              # the direct engine writes no rooms file
        # the proxy of that job, started with the cached tools file, lists the same eight
        listed = self.proxy([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}],
                            THOMHOUSE_TOOLS_FILE=str(files[0]))[0]["result"]["tools"]
        self.assertEqual([t["name"] for t in listed], list(TOOL_NAMES))

    def test_direct_tools_proxy_refuses_the_ninth_tool(self):
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, call(2, PROFILE, {})]
        for name, env in (("shipped file", {}), ("nine-tool file", {"THOMHOUSE_TOOLS_FILE": str(SHIPPED_TOOLS)})):
            with self.subTest(source=name):
                out = self.proxy(msgs, **env)
                self.assertEqual([t["name"] for t in out[0]["result"]["tools"]], list(TOOL_NAMES))
                self.assertTrue(out[1]["result"]["isError"])
        self.assertEqual(self.backend.requests, [])


class ForgetRoomMapTest(RunnerTestCase):
    def setUp(self):
        super().setUp()
        self.rooms = self.home / "rooms"
        self.rooms.mkdir()
        for name in ("cnv_abc.json", "cnv_other.json", "state.json", "team.json"):
            (self.rooms / name).write_text("{}")

    def names(self) -> list[str]:
        return sorted(p.name for p in self.rooms.iterdir())

    def test_forget_removes_the_room_map_of_that_conversation_only(self):
        removed = SessionStore(self.home).forget_conversation("cnv_abc")
        self.assertEqual(removed, [self.rooms / "cnv_abc.json"])
        self.assertEqual(self.names(), ["cnv_other.json", "state.json", "team.json"])
        self.assertEqual(SessionStore(self.home).forget_conversation("cnv_abc"), [])    # nothing left to remove
        with self.assertRaises(ValueError):
            SessionStore(self.home).forget_conversation("../rooms/state")
        self.assertEqual(self.names(), ["cnv_other.json", "state.json", "team.json"])

    def test_forget_does_not_follow_a_symlinked_room_map(self):
        outside = self.tmp / "outside.json"
        outside.write_text("{}")
        (self.rooms / "cnv_link.json").symlink_to(outside)
        self.assertEqual(SessionStore(self.home).forget_conversation("cnv_link"), [])
        self.assertTrue(outside.exists() and (self.rooms / "cnv_link.json").is_symlink())

    def test_forget_command_counts_the_room_map(self):
        env = {**os.environ, "THOMHOUSE_BOT_HOME": str(self.home), "RUNNER_ID": RUNNER_ID}
        p = subprocess.run([sys.executable, "-m", "runner.main", "forget", "cnv_abc"], cwd=APP, env=env,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout), {"conversation_id": "cnv_abc", "removed_paths": 1})
        self.assertEqual(self.names(), ["cnv_other.json", "state.json", "team.json"])


class TeamFileTest(RoomsTestCase):
    def test_lead_instructions_fit_the_platform_cap(self):
        soul, claude_md = setup.lead_instructions("QUY TAC NGAN")
        self.assertEqual((soul, claude_md), ("QUY TAC NGAN\n\n" + setup.LEAD_RULES, None))
        self.assertEqual(setup.lead_instructions("  "), (setup.LEAD_RULES, None))

        long_prompt = "Quy tắc trả lời khách. " * 2000                  # about 56 KB in UTF-8
        soul, claude_md = setup.lead_instructions(long_prompt)
        self.assertEqual(soul, setup.LEAD_RULES + setup.LEAD_RULES_IN_PROJECT_FILE)
        self.assertEqual(claude_md, f"{setup.RULES_MARKER}\n\n{long_prompt.strip()}\n")
        self.assertLessEqual(len(soul.encode("utf-8")), setup.SOUL_MAX_BYTES)
        self.assertIn(setup.RULES_SENTINEL, soul)
        self.assertIn(setup.RULES_MARKER, soul)
        self.assertNotIn(setup.RULES_SENTINEL, setup.LEAD_RULES)

        # the cap counts bytes, not characters: 9,000 three-byte characters do not fit
        self.assertIsNotNone(setup.lead_instructions("ạ" * 9000)[1])
        fits = "x" * (setup.SOUL_MAX_BYTES - len(("\n\n" + setup.LEAD_RULES).rstrip().encode("utf-8")))
        self.assertIsNone(setup.lead_instructions(fits)[1])
        self.assertIsNotNone(setup.lead_instructions(fits + "x")[1])

    def test_instruction_texts_carry_the_room_rules(self):
        lead, customer = setup.LEAD_RULES, setup.CUSTOMER_SOUL
        for text in ('"Bot khách hàng"', "[phiếu: MÃ]", "coordinate_bots", "chép nguyên văn", "truyền ticket",
                     "đúng MỘT câu trả lời cuối cùng", "Không nêu con số chi tiêu", "không viết tên của bot nào",
                     "Không viết mã phiếu", "Mã nằm trong tin nhắn của khách", "mcp__thom__quote_price"):
            self.assertIn(text, lead)
        for text in ('"Bot dịch vụ"', "mcp__thom__get_customer_profile", "[phiếu: MÃ]", "Xưng hô", "Tình trạng",
                     "Lần gần nhất", "Nhịp thường lệ", "Dịch vụ hay dùng", "Mức chi tiêu: nói bằng lời",
                     "Quyền lợi chưa dùng", "Gợi ý cho câu trả lời lần này", "Chưa có dữ liệu về khách này",
                     "Không bịa", "Không giao việc cho bot khác", "Không ghi con số tiền nào"):
            self.assertIn(text, customer)
        self.assertLess(len(customer.encode("utf-8")), setup.SOUL_MAX_BYTES)
        self.assertNotIn("@Bot", lead + customer)                      # an at-sign with a bot name wakes that bot

    def test_team_file_options(self):
        cfg = self.rooms_config(room_customer_model="claude-haiku-5-5", effort="turbo", model="claude-opus-5-5")
        doc, claude_md = setup.build_team(cfg, "thom-b", "QUY TAC")
        self.assertIsNone(claude_md)
        self.assertNotIn("rooms", doc)                                 # no conversation: bots and team only
        self.assertNotIn("prune", doc)
        self.assertEqual(doc["defaults"], {"team": "thom house", "model": "thom-b/claude-opus-5-5",
                                           "approval": "full", "computer": "off", "browser": False})
        lead, customer = doc["bots"]
        self.assertEqual(customer["model"], "thom-b/claude-haiku-5-5")
        self.assertNotIn("model", lead)
        self.assertEqual(lead["soul"], "QUY TAC\n\n" + setup.LEAD_RULES)

        with_room, _ = setup.build_team(self.rooms_config(effort="high"), "thom-a", "QUY TAC", "cnv_x1")
        self.assertEqual(with_room["defaults"]["effort"], "high")
        self.assertEqual([r["name"] for r in with_room["rooms"]], ["zalo-cnv_x1"])
        self.assertNotIn("model", with_room["bots"][1])

    def test_names(self):
        self.assertEqual(setup.room_name("cnv_abc"), "zalo-cnv_abc")
        self.assertEqual(setup.instance_name("a"), "thom-a")
        self.assertEqual(setup.instance_name("vip 1/x"), "thom-vip-1-x")
        self.assertEqual(setup.instance_name("mai.vy_2-b"), "thom-mai.vy_2-b")


if __name__ == "__main__":
    unittest.main()
