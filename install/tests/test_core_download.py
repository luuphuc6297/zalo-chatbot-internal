"""download.py: verified downloads through the fake curl, cache reuse, refusals (16.2.6, rev F11, F18)."""

from __future__ import annotations

import hashlib

from tests.support import InstallerTestCase
from thomhouse_installer import download
from thomhouse_installer.pins import PinError

URL = "https://nodejs.org/dist/v24.19.0/node-v24.19.0-darwin-arm64.tar.gz"
NAME = "node-v24.19.0-darwin-arm64.tar.gz"


class DownloadTest(InstallerTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.install_release()
        self.data = b"fake node tarball " * 1000
        (self.fixtures / NAME).write_bytes(self.data)
        self.sha = hashlib.sha256(self.data).hexdigest()
        self.ctx_ = self.ctx()

    def fetch(self, url: str = URL, sha: str | None = None, size: int | None = -1):
        return download.fetch(self.ctx_, url, self.sha if sha is None else sha,
                              len(self.data) if size == -1 else size, name="Node.js")

    def test_fixture_download(self) -> None:
        path = self.fetch()
        self.assertEqual(path, self.app_home / "cache" / "downloads" / f"{self.sha}.tar.gz")
        self.assertEqual(path.read_bytes(), self.data)
        curl = self.calls("curl")
        self.assertEqual(len(curl), 1)
        argv = curl[0]["argv"]
        for part in ("--proto", "=https", "--tlsv1.2", "-fL", "--retry", "3", "-C", "-", "-o"):
            self.assertIn(part, argv)
        self.assertEqual(argv[-1], URL)
        self.assertIn("127.0.0.1", curl[0]["env"]["no_proxy"])
        self.assertFalse(list((self.app_home / "cache" / "downloads").glob("*.part")))

    def test_checksum_mismatch_deletes_and_raises(self) -> None:
        self.behave(curl={"corrupt": [URL]})
        with self.assertRaises(download.DownloadError) as cm:
            self.fetch()
        self.assertEqual(cm.exception.kind, "checksum")
        self.assertEqual(cm.exception.key, "core.download_checksum")
        self.assertEqual(cm.exception.code, 1)
        self.assertEqual(list((self.app_home / "cache" / "downloads").iterdir()), [])

    def test_size_mismatch(self) -> None:
        self.behave(curl={"truncate": [URL]})
        with self.assertRaises(download.DownloadError) as cm:
            self.fetch()
        self.assertEqual(cm.exception.kind, "size")
        self.assertEqual(list((self.app_home / "cache" / "downloads").iterdir()), [])

    def test_not_https_refused_before_any_call(self) -> None:
        with self.assertRaises(download.DownloadError) as cm:
            self.fetch(url="http://nodejs.org/dist/x.tar.gz")
        self.assertEqual(cm.exception.kind, "not_https")
        self.assertEqual(cm.exception.fmt["host"], "nodejs.org")
        self.assertEqual(self.calls("curl"), [])

    def test_placeholder_hash_refused_before_any_call(self) -> None:
        for sha in ("", "…", "0" * 63):
            with self.assertRaises(PinError) as cm:
                download.fetch(self.ctx_, URL, sha, None, name="Python")
            self.assertEqual(cm.exception.code, 2)
            self.assertEqual(cm.exception.key, "core.pin_missing")
        with self.assertRaises(PinError):
            download.fetch(self.ctx_, URL, None, None, name="Python")  # type: ignore[arg-type]
        with self.assertRaises(PinError):
            download.fetch(self.ctx_, None, self.sha, None, name="Python")  # type: ignore[arg-type]
        self.assertEqual(self.calls("curl"), [])

    def test_network_and_http_errors(self) -> None:
        self.behave(curl={"fail": {URL: 7}})
        with self.assertRaises(download.DownloadError) as cm:
            self.fetch()
        self.assertEqual(cm.exception.kind, "network")
        self.assertEqual(cm.exception.key, "core.download_network")
        self.behave(curl={"fail": {URL: 22}})
        with self.assertRaises(download.DownloadError) as cm:
            self.fetch()
        self.assertEqual(cm.exception.kind, "http")

    def test_cached_file_reused_without_curl(self) -> None:
        first = self.fetch()
        before = len(self.calls("curl"))
        second = self.fetch()
        self.assertEqual(first, second)
        self.assertEqual(len(self.calls("curl")), before)

    def test_file_under_download_name_found_by_hash(self) -> None:
        downloads = self.app_home / "cache" / "downloads"
        downloads.mkdir(parents=True)
        (downloads / NAME).write_bytes(self.data)
        (downloads / "other.bin").write_bytes(b"something else")
        path = self.fetch()
        self.assertEqual(self.calls("curl"), [])
        self.assertEqual(path.read_bytes(), self.data)
        self.assertFalse((downloads / NAME).exists())
        self.assertTrue((downloads / "other.bin").exists())
        # Also without a known size.
        path.unlink()
        (downloads / NAME).write_bytes(self.data)
        self.assertEqual(self.fetch(size=None).read_bytes(), self.data)
        self.assertEqual(self.calls("curl"), [])

    def test_wrong_cache_file_replaced(self) -> None:
        downloads = self.app_home / "cache" / "downloads"
        downloads.mkdir(parents=True)
        (downloads / f"{self.sha}.tar.gz").write_bytes(b"damaged")
        path = self.fetch()
        self.assertEqual(path.read_bytes(), self.data)
        self.assertEqual(len(self.calls("curl")), 1)

    def test_complete_part_file_verified_without_curl(self) -> None:
        downloads = self.app_home / "cache" / "downloads"
        downloads.mkdir(parents=True)
        (downloads / f"{self.sha}.part").write_bytes(self.data)
        path = self.fetch()
        self.assertEqual(path.read_bytes(), self.data)
        self.assertEqual(self.calls("curl"), [])
