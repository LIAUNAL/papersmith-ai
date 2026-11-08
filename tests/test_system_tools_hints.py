"""What a workspace needs from the system, reported where it can act on it.

`smith status` used to say "OCR Engine Missing" whenever `llama-server` was not
on PATH, although `setup_env.py install` puts it in the workspace environment.
`smith doctor` said "install TeX Live/MacTeX or poppler" without the command;
it now names the one for the platform it runs on."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from papersmith.core import doctor, status


class OcrEngineTests(unittest.TestCase):
    def test_the_workspace_environment_counts_as_having_the_ocr_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / ".micromamba" / "envs" / "papersmith" / "bin" / "llama-server"
            binary.parent.mkdir(parents=True)
            binary.write_text("#!/bin/sh\n")
            binary.chmod(0o755)
            with mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):
                os.environ.pop("LLAMA_CPP_BINARY", None)
                self.assertTrue(status._runtime_status(root)["llama_server"])

    def test_no_engine_anywhere_still_reads_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):
            os.environ.pop("LLAMA_CPP_BINARY", None)
            self.assertFalse(status._runtime_status(Path(tmp))["llama_server"])


class TexHintTests(unittest.TestCase):
    def rows(self, platform: str) -> dict[str, str]:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(doctor, "find_tool", return_value=None), \
                mock.patch.object(doctor.sys, "platform", platform):
            return {row["item"]: row["detail"] for row in doctor.tool_rows(Path(tmp))}

    def test_linux_names_the_apt_packages(self) -> None:
        hint = self.rows("linux")["TeX engine"]
        self.assertIn("sudo apt install latexmk texlive-latex-recommended texlive-latex-extra "
                      "texlive-pictures texlive-fonts-recommended texlive-science", hint)

    def test_macos_names_mactex(self) -> None:
        self.assertIn("brew install --cask mactex-no-gui", self.rows("darwin")["TeX engine"])

    def test_the_rasterizer_hint_names_poppler(self) -> None:
        self.assertIn("sudo apt install poppler-utils", self.rows("linux")["rasterizer"])
        self.assertIn("brew install poppler", self.rows("darwin")["rasterizer"])


if __name__ == "__main__":
    unittest.main()
