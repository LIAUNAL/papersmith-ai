"""`scripts/setup_env.py` bootstraps a pinned micromamba and verifies it first (#57).

The bootstrap used to download `releases/latest` and run it unverified, in CI
too. These tests serve bytes from a fake `urlopen` into a temporary
`MAMBA_ROOT`, so they touch neither the network nor the checkout's real
`.micromamba/`.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "setup_env.py"
SPEC = importlib.util.spec_from_file_location("setup_env_under_test", SCRIPT)
assert SPEC and SPEC.loader
setup_env = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup_env)

PAYLOAD = b"\x7fELF stand-in for the pinned micromamba\n" * 64
PLATFORMS = {
    ("Linux", "x86_64"): "linux-64",
    ("Linux", "aarch64"): "linux-aarch64",
    ("Darwin", "x86_64"): "osx-64",
    ("Darwin", "arm64"): "osx-arm64",
    ("Windows", "AMD64"): "win-64",
    ("Windows", "ARM64"): "win-arm64",
}


class _Failing(io.BytesIO):
    """A response whose connection drops after the first chunk."""

    def read(self, size: int = -1) -> bytes:
        if self.tell():
            raise OSError("connection reset")
        return super().read(size)


class PinnedBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name)
        self.requests: list[tuple[str, object]] = []
        for patch in (
            mock.patch.object(setup_env, "MAMBA_ROOT", self.root / ".micromamba"),
            mock.patch.object(setup_env, "platform_asset", return_value="linux-64"),
            mock.patch.object(setup_env.shutil, "which", return_value=None),
            mock.patch.object(Path, "home", return_value=self.root / "home"),
            mock.patch.object(setup_env.urllib.request, "urlopen", side_effect=self._offline),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.target = setup_env.micromamba_exe()

    def _offline(self, url, timeout=None):
        raise AssertionError(f"unexpected download of {url}")

    def serve(self, response: io.BytesIO):
        def urlopen(url, timeout=None):
            self.requests.append((url, timeout))
            return response

        return mock.patch.object(setup_env.urllib.request, "urlopen", side_effect=urlopen)

    def pin(self, payload: bytes):
        digest = hashlib.sha256(payload).hexdigest()
        return mock.patch.dict(setup_env.MICROMAMBA_SHA256, {"linux-64": digest})

    def leftovers(self) -> list[str]:
        folder = self.target.parent
        return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []

    def test_a_matching_download_is_put_in_place_executable(self) -> None:
        with self.pin(PAYLOAD), self.serve(io.BytesIO(PAYLOAD)):
            path = setup_env.bootstrap_micromamba()

        self.assertEqual(path, self.target)
        self.assertEqual(path.read_bytes(), PAYLOAD)
        if os.name != "nt":
            self.assertTrue(os.access(path, os.X_OK))
        self.assertEqual(self.leftovers(), [self.target.name])
        [(url, timeout)] = self.requests
        self.assertIn(f"/releases/download/{setup_env.MICROMAMBA_VERSION}/micromamba-linux-64", url)
        self.assertEqual(timeout, setup_env.MICROMAMBA_TIMEOUT)

    def test_a_mismatched_download_stops_the_install_and_leaves_nothing(self) -> None:
        pinned = setup_env.MICROMAMBA_SHA256["linux-64"]
        with self.serve(io.BytesIO(b"a substituted binary")):
            with self.assertRaises(SystemExit) as stop:
                setup_env.bootstrap_micromamba()

        self.assertIn(pinned, str(stop.exception.code))
        self.assertIn("Nothing was installed", str(stop.exception.code))
        self.assertEqual(self.leftovers(), [])

    def test_an_oversized_download_is_refused(self) -> None:
        with (
            self.pin(PAYLOAD),
            self.serve(io.BytesIO(PAYLOAD)),
            mock.patch.object(setup_env, "MICROMAMBA_MAX_BYTES", len(PAYLOAD) - 1),
        ):
            with self.assertRaises(SystemExit) as stop:
                setup_env.bootstrap_micromamba()

        self.assertIn("larger than", str(stop.exception.code))
        self.assertEqual(self.leftovers(), [])

    def test_an_interrupted_download_leaves_no_partial_file(self) -> None:
        with self.pin(PAYLOAD), self.serve(_Failing(PAYLOAD * 64)):
            with self.assertRaises(OSError):
                setup_env.bootstrap_micromamba()

        self.assertEqual(self.leftovers(), [])

    def test_the_pinned_binary_in_place_is_reused_without_a_download(self) -> None:
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(PAYLOAD)

        with self.pin(PAYLOAD):
            self.assertEqual(setup_env.find_micromamba(), self.target)
            self.assertEqual(setup_env.bootstrap_micromamba(), self.target)

        self.assertEqual(self.requests, [])

    def test_a_local_binary_that_is_not_the_pin_is_never_run_and_is_replaced(self) -> None:
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b"whatever releases/latest served before the pin")

        with self.pin(PAYLOAD), self.serve(io.BytesIO(PAYLOAD)):
            self.assertIsNone(setup_env.find_micromamba())
            setup_env.bootstrap_micromamba()

        self.assertEqual(self.target.read_bytes(), PAYLOAD)
        self.assertEqual(self.leftovers(), [self.target.name])

    def test_the_project_local_binary_is_pin_checked_even_when_path_finds_it(self) -> None:
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b"whatever releases/latest served before the pin")
        on_path = mock.patch.object(setup_env.shutil, "which", return_value=str(self.target))

        with self.pin(PAYLOAD), on_path, self.serve(io.BytesIO(PAYLOAD)):
            self.assertIsNone(setup_env.find_micromamba())
            setup_env.bootstrap_micromamba()
            self.assertEqual(setup_env.find_micromamba(), self.target)

        self.assertEqual(self.target.read_bytes(), PAYLOAD)

    def test_a_home_install_that_is_the_project_local_binary_is_pin_checked(self) -> None:
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b"whatever releases/latest served before the pin")
        alias = self.root / "home" / ".local" / "bin" / "micromamba"
        alias.parent.mkdir(parents=True)
        for kind, make in (("symlink", os.symlink), ("hardlink", os.link)):
            with self.subTest(kind):
                alias.unlink(missing_ok=True)
                try:
                    make(self.target, alias)
                except OSError as refused:  # e.g. symlinks need a privilege on Windows
                    self.skipTest(f"cannot make a {kind} here: {refused}")

                with self.pin(PAYLOAD):
                    self.assertIsNone(setup_env.find_micromamba())

    def test_a_second_bootstrap_cannot_touch_the_first_ones_verified_file(self) -> None:
        """Two installs at once used to share one `.part` path, so the bytes the
        first one verified were not necessarily the bytes it moved into place."""
        bodies = iter([PAYLOAD, b"a different, unverified binary"])
        real_download = setup_env._download
        nested = []

        def download(url, destination):
            digest = real_download(url, destination)
            if not nested:  # a second install runs while the first holds its verified file
                nested.append(destination)
                with self.assertRaises(SystemExit):
                    setup_env.bootstrap_micromamba()
            return digest

        with (
            self.pin(PAYLOAD),
            mock.patch.object(
                setup_env.urllib.request,
                "urlopen",
                side_effect=lambda url, timeout=None: io.BytesIO(next(bodies)),
            ),
            mock.patch.object(setup_env, "_download", side_effect=download),
        ):
            self.assertEqual(setup_env.bootstrap_micromamba(), self.target)

        self.assertEqual(self.target.read_bytes(), PAYLOAD)
        self.assertEqual(self.leftovers(), [self.target.name])

    def test_an_operator_micromamba_on_path_is_used_as_installed(self) -> None:
        with mock.patch.object(setup_env.shutil, "which", return_value="/opt/mm/bin/micromamba"):
            self.assertEqual(setup_env.find_micromamba(), Path("/opt/mm/bin/micromamba"))


class PinTableTests(unittest.TestCase):
    def test_every_supported_platform_has_a_pinned_digest(self) -> None:
        for (system, machine), asset in PLATFORMS.items():
            with self.subTest(asset=asset):
                with (
                    mock.patch.object(setup_env.platform, "system", return_value=system),
                    mock.patch.object(setup_env.platform, "machine", return_value=machine),
                ):
                    self.assertEqual(setup_env.platform_asset(), asset)
                self.assertRegex(setup_env.MICROMAMBA_SHA256[asset], r"^[0-9a-f]{64}$")
        self.assertEqual(set(setup_env.MICROMAMBA_SHA256), set(PLATFORMS.values()))
        self.assertEqual(len(set(setup_env.MICROMAMBA_SHA256.values())), len(PLATFORMS))

    def test_the_url_names_the_pinned_release_never_latest(self) -> None:
        self.assertRegex(setup_env.MICROMAMBA_VERSION, r"^\d+\.\d+\.\d+-\d+$")
        self.assertNotIn("latest", setup_env.MICROMAMBA_URL)
        url = setup_env.MICROMAMBA_URL.format(version="1.2.3-0", asset="osx-arm64")
        self.assertTrue(
            re.fullmatch(
                r"https://github\.com/mamba-org/micromamba-releases/releases/download/"
                r"1\.2\.3-0/micromamba-osx-arm64",
                url,
            ),
            url,
        )


if __name__ == "__main__":
    unittest.main()
