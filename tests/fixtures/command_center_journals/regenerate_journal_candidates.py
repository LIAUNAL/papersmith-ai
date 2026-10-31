"""Rebuilds journal-candidates-fallback.json from the real journal CLI against the fake servers.

Run from the repository root:

    .micromamba/envs/papersmith/bin/python tests/fixtures/command_center_journals/regenerate_journal_candidates.py

It is a fallback run: the fake OpenAlex answers 429, `--source auto` continues with Crossref,
Europe PMC, DOAJ and the imported SJR file, and `--include-unknown-quartile` keeps the journals
without a quartile. The only hand-made part is the hostile example work, which the panel's
escaping tests need; the run date, temporary paths and the fake server's port are pinned so the
file is stable.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tests.test_journal_finder import CLI, FIXTURES, SCRUBBED, FakeApi  # noqa: E402

TARGET = Path(__file__).with_name("journal-candidates-fallback.json")
HOSTILE_WORK = {"title": "<img src=x onerror=alert(1)>", "year": 2024, "doi": '10.1000/"><script>alert(2)</script>'}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="journal-candidates-") as holder:
        tmp = Path(holder)
        (tmp / "ws" / "paper").mkdir(parents=True)
        shutil.copy(FIXTURES / "paper_main.tex", tmp / "ws" / "paper" / "main.tex")
        shutil.copy(FIXTURES / "refs.bib", tmp / "ws" / "paper" / "refs.bib")
        api = FakeApi(script={"/openalex/works": [(429, 86400)]})
        env = {k: v for k, v in os.environ.items() if k not in SCRUBBED}
        env.update(api.env)
        env.update({
            "PAPERSMITH_SJR_DIR": str(tmp / "sjr"), "PAPERSMITH_JOURNAL_CACHE_DIR": str(tmp / "cache"),
            "PAPERSMITH_HTTP_BACKOFF": "0", "PAPERSMITH_OPENALEX_MIN_INTERVAL": "0",
            "PAPERSMITH_CROSSREF_MIN_INTERVAL": "0", "PAPERSMITH_FALLBACK_MIN_INTERVAL": "0",
            "HOME": str(tmp / "home"),
        })

        def run(*args: str) -> None:
            done = subprocess.run([sys.executable, str(CLI), *args], env=env, capture_output=True, text=True)
            if done.returncode:
                raise SystemExit(done.stdout + done.stderr)

        run("sjr-import", "--file", str(FIXTURES / "scimagojr-2019.csv"))
        run("search", "--workspace", str(tmp / "ws"), "--quartiles", "Q1-Q4", "--include-unknown-quartile")
        api.close()
        text = (tmp / "ws" / "paper" / "journal-candidates.json").read_text(encoding="utf-8")
        # The run's temporary paths and the fake server's port would make the file differ on every run.
        for folder in {str(tmp), str(tmp.resolve())}:
            text = text.replace(folder, "/home/user/.cache/papersmith")
        document = json.loads(text.replace(f"127.0.0.1:{api.port}", "api.example"))
    document["generated_at"] = "2026-10-31T12:00:00+00:00"
    document["candidates"][0]["similar_works"].insert(0, HOSTILE_WORK)
    TARGET.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
