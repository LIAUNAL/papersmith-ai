"""Two derived-vocabulary guards, held to both halves of their job.

`AccountVocabularyLeakTests` (tests/test_kaggle_accounts.py) and
`ForgeVocabularyDerivedGuardTests` (tests/test_proposal_implementation.py)
each derive a denylist from something on disk -- this machine's stored
account usernames, the targets under `implementations/` -- and object when a
tracked file names it. Both once read an ordinary word as identity: an
account stem shared by two stored usernames happened to be an ordinary
Spanish noun in shipped contract prose, and a target's module basenames came
apart into everyday English words the forge uses in hundreds of files.

Every case here drives the guard through the same methods its real test
calls, against invented names and scratch files only. A guard that stops
reporting a real leak fails here exactly as loudly as one that reports
ordinary prose. No name below belongs to any real account or target.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_kaggle_accounts as accounts_suite  # noqa: E402
import test_proposal_implementation as forge_suite  # noqa: E402

ACCOUNT_TEST = "test_no_skill_source_names_a_real_account_of_this_machine"

#: Invented accounts shaped like the real failure: two usernames whose shared
#: digit-stripped stem is an ordinary Spanish noun, plus a singleton.
INVENTED_ACCOUNTS = ["Cosecha51", "Cosecha50", "Ostrander7"]


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        digest.update(str(path.relative_to(root)).encode())
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


class AccountGuardKeepsIdentityAndAdmitsProseTests(unittest.TestCase):
    """The account guard, run as its real test runs, over scratch files."""

    def run_guard(self, *texts: str) -> unittest.TestResult:
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        files = []
        for index, text in enumerate(texts):
            path = scratch / f"document_{index}.md"
            path.write_text(text, encoding="utf-8")
            files.append(path)
        before = _tree_digest(scratch)
        # Read off the module, never bound to a global here: a TestCase class
        # in this module's namespace would be collected and run a second time.
        guard = accounts_suite.AccountVocabularyLeakTests
        case = guard(ACCOUNT_TEST)
        result = unittest.TestResult()
        with unittest.mock.patch.object(
                guard, "_stored_usernames",
                return_value=list(INVENTED_ACCOUNTS)) as stored, \
                unittest.mock.patch.object(
                    guard, "_tracked_skill_scripts",
                    return_value=files):
            case.run(result)
        self.assertEqual(stored.call_count, 1,
                         "the guard must read the store exactly once")
        self.assertEqual(_tree_digest(scratch), before,
                         "the guard is read-only over what it scans")
        self.assertEqual(result.errors, [], "the guard crashed instead of judging")
        self.assertEqual(result.skipped, [], "the guard skipped with accounts stored")
        return result

    def assert_rejects(self, text: str, word: str) -> None:
        result = self.run_guard(text)
        self.assertEqual(len(result.failures), 1, f"{text!r} was accepted")
        self.assertIn(repr(word), result.failures[0][1])

    def assert_accepts(self, text: str) -> None:
        result = self.run_guard(text)
        self.assertEqual(result.failures, [], f"{text!r} was rejected")

    def test_a_shared_stem_in_ordinary_prose_is_not_an_account(self):
        self.assert_accepts("La cosecha de datos se publica cada trimestre.\n")
        self.assert_accepts("Cosecha, siembra y riego: tres etapas.\n")
        self.assert_accepts("enunciando su propia **cosecha** antes\n")

    def test_a_singleton_stem_is_never_banned_on_its_own(self):
        self.assert_accepts("Ostrander et al. report the same bound.\n")

    def test_an_exact_username_is_still_caught_anywhere(self):
        self.assert_rejects("logged in as Cosecha51 yesterday\n", "cosecha51")
        self.assert_rejects("home is /Users/ostrander7/work\n", "ostrander7")

    def test_a_disguised_display_prefix_is_still_caught(self):
        self.assert_rejects("`Cosecha XX, KGAT_…` came apart\n", "cosecha")
        self.assert_rejects("written as cosecha## in the inbox\n", "cosecha")
        self.assert_rejects("a third account, Cosecha_<n>\n", "cosecha")

    def test_an_unstored_sibling_handle_is_caught_by_its_stem(self):
        self.assert_rejects("ask Cosecha52 for the quota\n", "cosecha")
        self.assert_rejects("ping @cosecha about it\n", "cosecha")

    def test_a_stem_on_a_credential_line_is_caught(self):
        self.assert_rejects("Cosecha, KGAT_0123456789abcdef\n", "cosecha")
        self.assert_rejects(
            "cosecha | 0123456789abcdef0123456789abcdef\n", "cosecha")


class ForgeRuleBReadsCompoundsNotTheirPartsTests(unittest.TestCase):
    """Rule B, over a scratch target whose module and notebook basenames are
    built from ordinary words, and a scratch forge that either borrows the
    basename or only speaks the ordinary words composing it."""

    def setUp(self):
        self.guard = forge_suite.ForgeVocabularyDerivedGuardTests(
            "test_rule_b_finds_no_target_vocabulary_in_the_forge")
        self.addCleanup(self.guard.doCleanups)
        base = Path(tempfile.mkdtemp())
        self.guard.addCleanup(shutil.rmtree, base, ignore_errors=True)
        target = base / "Quarry_Survey"
        package = target / "src" / "quarry_survey"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "paddock.py").write_text("VALUE = 1\n", encoding="utf-8")
        (package / "lantern_ledger.py").write_text("VALUE = 2\n",
                                                   encoding="utf-8")
        notebooks = target / "Quarry" / self.guard.NOTEBOOK_CATEGORY
        notebooks.mkdir(parents=True)
        (notebooks / "Wick_Ledger.ipynb").write_text("{}\n", encoding="utf-8")
        self.targets = base
        self.denylist = self.guard.derived_denylist(
            base, forge_root=self.guard.scratch_forge())

    def leaks_of(self, comment: str) -> dict:
        forge = self.guard.scratch_forge()
        (forge / "scripts" / "probe.py").write_text(
            f"# {comment}\nVALUE = 1\n", encoding="utf-8")
        before = _tree_digest(self.targets)
        found = self.guard.leaks(self.denylist, forge)
        self.assertEqual(_tree_digest(self.targets), before,
                         "rule B reads target names and never writes")
        return found

    def test_the_denylist_holds_compounds_and_single_names_not_parts(self):
        for word in ("lantern_ledger", "wick_ledger", "paddock",
                     "quarry", "quarry_survey"):
            self.assertIn(word, self.denylist)
        for word in ("lantern", "ledger", "wick"):
            self.assertNotIn(word, self.denylist)

    def test_ordinary_words_composing_a_basename_are_accepted(self):
        self.assertEqual(
            self.leaks_of("keep the lantern lit while the ledger closes"), {})
        self.assertEqual(self.leaks_of("a two-word wick ledger in prose"), {})

    def test_the_borrowed_basename_is_rejected_in_any_casing(self):
        self.assertEqual(self.leaks_of("copied from lantern_ledger"),
                         {"scripts/probe.py": ["lantern_ledger"]})
        self.assertEqual(self.leaks_of("rendered by WICK_LEDGER"),
                         {"scripts/probe.py": ["wick_ledger"]})

    def test_target_identity_and_single_word_modules_stay_guarded(self):
        self.assertEqual(self.leaks_of("staged in the paddock"),
                         {"scripts/probe.py": ["paddock"]})
        self.assertEqual(self.leaks_of("ported from Quarry_Survey"),
                         {"scripts/probe.py": ["quarry_survey"]})
        self.assertEqual(self.leaks_of("the quarry notebooks"),
                         {"scripts/probe.py": ["quarry"]})


if __name__ == "__main__":
    unittest.main()
