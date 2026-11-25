"""Build shim: refresh the bundled kit before setuptools assembles the wheel.

The kit (``src/papersmith/_kit``) is a generated snapshot of the framework's
copy-on-init assets. Refreshing it here means ``pipx install .`` always ships
a kit that matches the checkout, with no manual step to forget.

Caztor (``src/papersmith/_caztor``, the PDF tab's LaTeX editor) is not built
here: building it runs ``npm`` and needs Node.js 26, which an ordinary install
from a checkout must not depend on. A checkout runs ``caztor/`` itself once
``npm run setup:caztor`` has set it up; ``scripts/build-caztor.py --require``
packages it for a release (the publishing workflow), and the wheel carries
whatever ``_caztor`` that left.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).resolve().parent


class BuildPyWithKit(build_py):
    def run(self) -> None:
        build_kit = ROOT / "scripts" / "build-kit.py"
        if build_kit.is_file():
            subprocess.run(
                [sys.executable, str(build_kit), "--quiet"],
                cwd=ROOT,
                check=True,
            )
        super().run()


setup(cmdclass={"build_py": BuildPyWithKit})
