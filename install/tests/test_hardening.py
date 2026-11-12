"""Fixes from the security and recovery review of the core modules: the staff token never follows a redirect, and a
curl write error (a full disk) is not reported as a missing network."""

from __future__ import annotations

import http.server
import threading

from tests.support import InstallerTestCase
from thomhouse_installer import download, stack
from thomhouse_installer.text_vi import t


def _serve(handler_cls) -> tuple[http.server.HTTPServer, str]:
    server = http.server.HTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


class RedirectTest(InstallerTestCase):
    def test_token_never_follows_a_redirect(self) -> None:
        seen: list[tuple[str, str | None]] = []

        class Target(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                pass

            def do_GET(self) -> None:  # noqa: N802 - http.server hook
                seen.append((self.path, self.headers.get("Authorization")))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"roles": ["x"]}')

        target, target_url = _serve(Target)
        self.addCleanup(target.server_close)
        self.addCleanup(target.shutdown)
        port = target.server_address[1]

        class Redirector(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                pass

            def do_GET(self) -> None:  # noqa: N802 - http.server hook
                code = 307 if self.path.endswith("307") else 302
                self.send_response(code)
                self.send_header("Location", f"http://127.1:{port}/elsewhere")
                self.end_headers()

        redirector, url = _serve(Redirector)
        self.addCleanup(redirector.server_close)
        self.addCleanup(redirector.shutdown)
        ctx = self.ctx()
        with self.assertRaises(ValueError):
            stack.http_json(ctx, "GET", f"http://127.1:{port}/elsewhere", token="staff-SECRET")
        for path, code in (("/staff/roles", 302), ("/staff/roles/307", 307)):
            status, body = stack.http_json(ctx, "GET", url + path, token="staff-SECRET")
            self.assertEqual((status, body), (code, None))
        self.assertEqual(seen, [])
        self.assertEqual(stack.http_json(ctx, "GET", target_url + "/direct")[0], 200)  # a plain call still works
        self.assertEqual(seen, [("/direct", None)])


class DownloadDiskTest(InstallerTestCase):
    def test_curl_write_error_is_a_disk_error(self) -> None:
        self.install_release("1.4.0")
        self.behave(curl={"exit": 23})
        with self.assertRaises(download.DownloadError) as cm:
            download.fetch(self.ctx(), "https://nodejs.org/dist/v24.19.0/node.tar.gz", "a" * 64, 10, name="Node.js")
        self.assertEqual(cm.exception.kind, "disk")
        text = t(cm.exception.key, name="Node.js", host="nodejs.org", cmd="~/ThomHouse/bin/thomhouse continue")
        self.assertIn("không đủ chỗ trống", text)
        self.assertNotIn("mạng", text)

    def test_network_codes_unchanged(self) -> None:
        self.install_release("1.4.0")
        for code, kind in ((7, "network"), (22, "http"), (56, "network")):
            with self.subTest(code=code):
                self.behave(curl={"exit": code})
                with self.assertRaises(download.DownloadError) as cm:
                    download.fetch(self.ctx(), "https://nodejs.org/n.tar.gz", "b" * 64, 10, name="Node.js")
                self.assertEqual(cm.exception.kind, kind)
