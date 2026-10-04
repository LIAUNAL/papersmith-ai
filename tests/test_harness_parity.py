"""Every harness the setup script serves must be visible in a fresh clone.

`scripts/setup-harnesses.sh` projects the canonical `skills/` tree into one
directory per harness. Those links are generated, so they are ignored -- but
ignoring the whole harness directory instead of just the link makes that
harness invisible to anyone who clones the repository. A collaborator then
sees three harness directories, concludes the fourth is unsupported, and is
reasonably right to: nothing in the tree says otherwise.

That is what happened to Pi, and the fix used to be a generated link. It is no
longer: Pi discovers project skills through `<cwd>/.pi/settings.json`, a
versioned file whose `"../skills"` entry resolves to the canonical tree with no
symlink and nothing to run first. So Pi left the link roster, and the guard had
to move to the invariant that still holds:

* every harness the setup script *does* serve has its generated link ignored
  and its directory carried by a committed file (the original claim, now over a
  roster of three);
* Pi, no longer in that roster, is covered by
  :meth:`HarnessParityTests.test_pi_is_discovered_without_a_generated_link` --
  its discovery path is a file, not a link.

The roster below is derived from the shell script's own `HARNESSES` array
rather than restated here, because a harness added to that array and not to
this file is exactly the drift these assertions exist to catch.
"""

import json
import re
import subprocess
import unittest
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parent.parent
SETUP = FORGE_ROOT / "scripts" / "setup-harnesses.sh"
GITIGNORE = FORGE_ROOT / ".gitignore"
PI_SETTINGS = FORGE_ROOT / ".pi" / "settings.json"
PI_APPEND = FORGE_ROOT / ".pi" / "APPEND_SYSTEM.md"
CANONICAL_SKILLS = FORGE_ROOT / "skills"

#: `  ".pi/skills:Pi"` -> ("\.pi/skills", "Pi"). Matched against the array the
#: script actually iterates, so the test cannot pass over a roster nobody uses.
ENTRY = re.compile(r'^\s*"([^":]+):([^"]+)"\s*$', re.MULTILINE)


def declared_harnesses() -> list[tuple[str, str]]:
    """Every `<relative skills dir>, <label>` pair the setup script serves."""
    source = SETUP.read_text(encoding="utf-8")
    block = re.search(r"HARNESSES=\((.*?)\n\)", source, re.DOTALL)
    if not block:
        raise AssertionError(
            f"no HARNESSES=( ... ) array found in {SETUP}; this test derives "
            "its roster from that array and has nothing to assert without it")
    return ENTRY.findall(block.group(1))


def is_ignored(relpath: str) -> bool:
    """True when `.gitignore` keeps `relpath` out of a fresh clone."""
    return subprocess.run(
        ["git", "check-ignore", "-q", relpath],
        cwd=FORGE_ROOT, capture_output=True).returncode == 0


class HarnessParityTests(unittest.TestCase):
    def test_the_roster_is_derived_and_not_empty(self) -> None:
        """Non-vacuity. A regex that stopped matching would make every
        assertion below pass over an empty list, and a roster that found no
        harnesses reads exactly like a repository with no drift.

        The bound is three, not four, because Pi left the roster when its
        discovery path stopped being a generated link -- that move is asserted
        in its own test below. The bound still has to be a real count: a
        vacuous roster is the failure mode this whole file exists to prevent.
        """
        found = declared_harnesses()
        self.assertGreaterEqual(
            len(found), 3,
            f"derived only {found} from {SETUP.name}; the assertions below "
            "would be checking nothing")

    def test_each_harness_ignores_its_generated_link_and_nothing_more(self) -> None:
        """The link is generated, so it is ignored. The directory holding it
        is not generated, and ignoring it hides the harness from the tree."""
        ignored = {line.strip() for line in GITIGNORE.read_text(encoding="utf-8").split("\n")}
        for rel, label in declared_harnesses():
            with self.subTest(harness=label):
                self.assertIn(
                    rel, ignored,
                    f"{label}'s generated link `{rel}` is not ignored; a "
                    "rebuilt symlink would show up as a repository change")
                parent = rel.split("/")[0]
                for shape in (parent, f"{parent}/"):
                    self.assertNotIn(
                        shape, ignored,
                        f"`{shape}` ignores {label}'s whole directory, not "
                        f"just its generated link. Nothing under it can be "
                        f"committed, so the directory does not exist in a "
                        f"fresh clone and {label} reads as unsupported")

    def test_each_harness_directory_travels_with_the_repository(self) -> None:
        """Ignoring only the link is permission, not presence. A directory
        with nothing committed in it still arrives absent."""
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=FORGE_ROOT,
            capture_output=True, text=True, check=True).stdout.split("\n")
        for rel, label in declared_harnesses():
            parent = rel.split("/")[0]
            with self.subTest(harness=label):
                carried = [p for p in tracked if p.startswith(f"{parent}/")]
                self.assertTrue(
                    carried,
                    f"{parent}/ holds no committed file, so it is absent from "
                    f"a fresh clone and a collaborator has no sign {label} is "
                    "a supported harness. One tracked file is enough, and it "
                    "should say why the directory looks empty")

    def test_pi_is_discovered_without_a_generated_link(self) -> None:
        """Pi is served by a versioned settings entry, not by a symlink.

        The setup script used to link `.pi/skills`, which meant a fresh clone
        found no Pi skills until somebody ran it by hand. `.pi/settings.json`
        replaces that link: its `"../skills"` entry resolves from the project
        `.pi/` directory to the canonical tree on its own. This guards the
        replacement the way the three assertions above guard the links -- with
        the discovery path present, committable, and pointing where the script
        points.
        """
        labels = [label for _, label in declared_harnesses()]
        self.assertNotIn(
            "Pi", labels,
            "Pi is back in the setup script's link roster; its discovery path "
            "is the settings entry asserted below, and a second mechanism for "
            "one job is what replaced the first")

        self.assertTrue(
            PI_SETTINGS.is_file(),
            f"{PI_SETTINGS} is absent; a fresh clone would load no Pi skills")
        self.assertFalse(
            is_ignored(".pi/settings.json"),
            ".pi/settings.json is ignored, so a fresh clone loses Pi's "
            "discovery path and Pi's skills go missing")

        payload = json.loads(PI_SETTINGS.read_text(encoding="utf-8"))
        entries = payload.get("skills")
        self.assertTrue(entries, f"{PI_SETTINGS} declares no skills path")
        for entry in entries:
            with self.subTest(entry=entry):
                self.assertEqual(
                    (PI_SETTINGS.parent / entry).resolve(), CANONICAL_SKILLS.resolve(),
                    f"{entry!r} does not resolve to the canonical skills tree")

        self.assertTrue(
            PI_APPEND.is_file(),
            f"{PI_APPEND} is absent; Pi has no entrypoint that replaces the "
            "unread `PI.md`")
        self.assertFalse(
            is_ignored(".pi/APPEND_SYSTEM.md"),
            ".pi/APPEND_SYSTEM.md is ignored, so the entrypoint Pi reads "
            "never reaches a fresh clone")


if __name__ == "__main__":
    unittest.main()
