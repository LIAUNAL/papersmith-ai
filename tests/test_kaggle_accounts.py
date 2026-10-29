"""Focused unit tests for the Kaggle credential store.

These cover the deterministic logic in ``accounts_cli.py`` — credential file
parsing, the store round-trip, alias rules, and the git-ignore precondition —
without touching the network. Validation itself is stubbed; what it does against
the live API is proven by adding a real credential, not by a unit test.

Run with any Python 3.10+ (the script is stdlib-only):
    python3 -m unittest tests.test_kaggle_accounts
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import inspect
import io
import json
import re
import stat
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from collections import Counter
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "skills/kaggle-accounts/scripts/accounts_cli.py"

# Doctrine, as a path the suite can read: `MaterializedTokenDoctrineTests`
# holds this document's materialized-token table to what `materialize`
# actually writes. Prose cannot be held to code; a table can.
SKILL_MD = REPOSITORY_ROOT / "skills/kaggle-accounts/SKILL.md"
SPEC = importlib.util.spec_from_file_location("accounts_cli", SCRIPT)
assert SPEC and SPEC.loader
ACCOUNTS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ACCOUNTS
SPEC.loader.exec_module(ACCOUNTS)


def write_credential(folder: Path, name: str, **fields: object) -> Path:
    path = folder / name
    path.write_text(json.dumps(fields), encoding="utf-8")
    return path



class ObjectiveFlowTests(unittest.TestCase):
    """The north: why this skill was invoked and where it has to arrive."""

    STAGES = ["taken-in", "proven", "decided"]

    def test_the_one_refusal_path_carries_it(self) -> None:
        source = Path(ACCOUNTS.__file__).read_text(encoding="utf-8")
        self.assertEqual(
            source.count('print(f"error: {exc}", file=sys.stderr)'), 1,
            "a second refusal path appeared and carries nothing")
        self.assertIn('"objective": OBJECTIVE_FLOW', source)

    def test_it_is_declared_ordered_and_closes_every_stage(self) -> None:
        flow = ACCOUNTS.OBJECTIVE_FLOW
        self.assertEqual([s["stage"] for s in flow["stages"]], self.STAGES)
        for stage in flow["stages"]:
            self.assertTrue(stage["establishes"] and stage["behindWhen"])

    def test_arrival_is_a_current_verdict_and_not_a_command_that_ran(self) -> None:
        """A stored credential is a claim and only the service settles it --
        and a verdict decays, so "it authenticated once" is not arrival."""
        self.assertIn("current verdict", ACCOUNTS.OBJECTIVE_FLOW["arrival"])

    def test_deciding_what_happens_to_a_failure_is_a_persons_stop(self) -> None:
        """A dead credential is reported and never removed here, deliberately.
        A session that runs validate, sees a failure and stops has not
        arrived -- and the north is what says so."""
        stops = " ".join(ACCOUNTS.OBJECTIVE_FLOW["humanStops"])
        self.assertIn("stopped working", stops)
        self.assertIn("consent", stops.lower())

    def test_the_doctrine_states_the_same_stages(self) -> None:
        skill = SKILL_MD.read_text(encoding="utf-8")
        start = skill.index("## The objective flow")
        table = skill[start:skill.index("**Arrival:**", start)]
        rows = [line for line in table.splitlines() if line.startswith("| `")]
        self.assertEqual([line.split("`")[1] for line in rows], self.STAGES)


class ReadCredentialsTests(unittest.TestCase):
    def test_reads_username_and_key_from_a_kaggle_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_credential(Path(tmp), "kaggle.json", username=" diego ", key=" abc123 ")
            (entry,) = ACCOUNTS.read_credentials(str(path))
            self.assertEqual((entry["username"], entry["key"]), ("diego", "abc123"))

    def test_rejects_a_missing_file(self) -> None:
        with self.assertRaisesRegex(ACCOUNTS.CredentialError, "not found"):
            ACCOUNTS.read_credentials("/nonexistent/kaggle.json")

    def test_rejects_unparseable_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "kaggle.json"
            path.write_text("not json at all", encoding="utf-8")
            with self.assertRaisesRegex(ACCOUNTS.CredentialError, "not valid JSON"):
                ACCOUNTS.read_credentials(str(path))

    def test_rejects_a_json_object_missing_either_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            no_key = write_credential(Path(tmp), "a.json", username="diego")
            no_user = write_credential(Path(tmp), "b.json", key="abc123")
            blank = write_credential(Path(tmp), "c.json", username="diego", key="   ")
            for path, expected in ((no_key, "'key'"), (no_user, "'username'"), (blank, "'key'")):
                with self.assertRaisesRegex(ACCOUNTS.CredentialError, expected):
                    ACCOUNTS.read_credentials(str(path))


class CredentialListTests(unittest.TestCase):
    """A hand-written `.txt` of accounts — one `username key` per line."""

    def test_reads_every_line_whatever_separator_was_used(self) -> None:
        entries = ACCOUNTS.parse_credential_lines(
            "one, KEY1\ntwo: KEY2\nthree KEY3\nfour\tKEY4\n")
        self.assertEqual([(e["username"], e["key"]) for e in entries],
                         [("one", "KEY1"), ("two", "KEY2"), ("three", "KEY3"), ("four", "KEY4")])

    def test_skips_blank_lines_and_comments_so_a_list_can_be_annotated(self) -> None:
        entries = ACCOUNTS.parse_credential_lines("# personal\n\none, KEY1\n\n# lab\ntwo, KEY2\n")
        self.assertEqual([e["username"] for e in entries], ["one", "two"])

    def test_a_bad_line_is_its_own_problem_and_does_not_fail_the_file(self) -> None:
        # The point of a list is that the good rows survive the bad ones.
        entries = ACCOUNTS.parse_credential_lines("one, KEY1\nnonsense\ntwo, KEY2\n")
        self.assertEqual([e["username"] for e in entries if not e["problem"]], ["one", "two"])
        (bad,) = [e for e in entries if e["problem"]]
        self.assertEqual(bad["label"], "line 2")

    def test_never_quotes_the_offending_line_back(self) -> None:
        # Half of a malformed credential line is still a key.
        (bad,) = ACCOUNTS.parse_credential_lines("user KEY_THAT_LEAKED extra\n")
        self.assertIsNotNone(bad["problem"])
        self.assertNotIn("KEY_THAT_LEAKED", bad["problem"])

    def test_numbers_lines_by_the_file_not_by_the_credentials_in_it(self) -> None:
        # "line 4" has to mean the fourth line of what the user opens in an editor.
        entries = ACCOUNTS.parse_credential_lines("# note\n\none, KEY1\ntwo, KEY2\n")
        self.assertEqual([e["label"] for e in entries], ["line 3", "line 4"])

    def test_underscores_in_a_key_survive_undecoration(self) -> None:
        # Markdown italicises with `_` and Kaggle tokens contain it. Stripping it
        # turns a good key into a 401 that reads as an expired token and sends
        # somebody to regenerate one that was working.
        (entry,) = ACCOUNTS.parse_credential_lines("- **SampleAccount**: `KGAT_86ed_f00`\n")
        self.assertEqual((entry["username"], entry["key"]), ("SampleAccount", "KGAT_86ed_f00"))

    def test_reads_a_markdown_table(self) -> None:
        entries = ACCOUNTS.parse_credential_lines(
            "# Cuentas\n\n| Usuario | Token |\n|---|---|\n| one | KEY_1 |\n| two | KEY_2 |\n")
        self.assertEqual([(e["username"], e["key"]) for e in entries],
                         [("one", "KEY_1"), ("two", "KEY_2")])

    def test_the_table_header_is_skipped_by_its_structure_not_by_its_words(self) -> None:
        # The row before `|---|---|` is a header whatever it is called.
        entries = ACCOUNTS.parse_credential_lines(
            "| cuenta | api |\n|---|---|\n| one | KEY_1 |\n")
        self.assertEqual([e["username"] for e in entries], ["one"])

    def test_reads_a_bullet_list(self) -> None:
        entries = ACCOUNTS.parse_credential_lines("## Kaggle\n\n- one: KEY_1\n* two, KEY_2\n")
        self.assertEqual([(e["username"], e["key"]) for e in entries],
                         [("one", "KEY_1"), ("two", "KEY_2")])

    def test_a_md_is_read_as_a_list_like_a_txt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "API_Token.md"
            path.write_text("| one | KEY_1 |\n", encoding="utf-8")
            (entry,) = ACCOUNTS.read_credentials(str(path))
            self.assertEqual(entry["username"], "one")

    def test_an_explicit_delimiter_beats_whitespace_so_a_field_can_hold_a_space(self) -> None:
        # Splitting on every separator at once means a field can never contain
        # one. The comma the person typed says where the boundary is.
        for line, expected in (
            ("Jane Doe, KEY_1", ["Jane Doe", "KEY_1"]),
            ("| Jane Doe | KEY_1 |", ["Jane Doe", "KEY_1"]),
            ("- Jane Doe: KEY_1", ["Jane Doe", "KEY_1"]),
            ("Jane Doe\tKEY_1", ["Jane Doe", "KEY_1"]),
        ):
            self.assertEqual(ACCOUNTS.split_credential_line(line), expected, line)

    def test_whitespace_still_splits_a_line_with_no_delimiter_in_it(self) -> None:
        self.assertEqual(ACCOUNTS.split_credential_line("diego KEY_1"), ["diego", "KEY_1"])

    def test_a_name_with_a_space_is_named_as_a_display_name_not_as_bad_punctuation(self) -> None:
        # It is not a typo: it is the other name Kaggle shows, and telling
        # somebody their fields are miscounted sends them to fix the wrong thing.
        (entry,) = ACCOUNTS.parse_credential_lines("Jane Doe, KEY_1\n")
        self.assertIsNone(entry["username"])
        self.assertIn("display name", entry["problem"])
        self.assertNotIn("field(s)", entry["problem"])

    def test_a_rejected_username_never_carries_its_key_along(self) -> None:
        (entry,) = ACCOUNTS.parse_credential_lines("Jane Doe, KEY_THAT_LEAKED\n")
        self.assertIsNone(entry["key"])
        self.assertNotIn("KEY_THAT_LEAKED", entry["problem"])

    def test_a_txt_holding_nothing_usable_is_refused_as_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cuentas.txt"
            path.write_text("# solo comentarios\n\n", encoding="utf-8")
            with self.assertRaisesRegex(ACCOUNTS.CredentialError, "no credentials"):
                ACCOUNTS.read_credentials(str(path))


class StoreTests(unittest.TestCase):
    def test_a_missing_store_reads_as_empty_rather_than_failing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ACCOUNTS.load_store(Path(tmp) / "accounts.json")
            self.assertEqual(store["accounts"], [])

    def test_a_corrupt_store_fails_closed_instead_of_reading_as_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "accounts.json"
            path.write_text("{ truncated", encoding="utf-8")
            with self.assertRaisesRegex(ACCOUNTS.StoreError, "not valid JSON"):
                ACCOUNTS.load_store(path)

    def test_a_store_without_an_accounts_list_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "accounts.json"
            path.write_text(json.dumps({"version": 1}), encoding="utf-8")
            with self.assertRaisesRegex(ACCOUNTS.StoreError, "credential store"):
                ACCOUNTS.load_store(path)

    def test_saving_round_trips_and_leaves_the_file_owner_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store" / "accounts.json"
            (path.parent).mkdir()
            (path.parent / ".gitignore").write_text("*\n", encoding="utf-8")
            written = {
                "version": 1,
                "accounts": [{"alias": "personal", "username": "diego", "key": "abc123"}],
            }
            ACCOUNTS.save_store(written, path)
            self.assertEqual(ACCOUNTS.load_store(path)["accounts"], written["accounts"])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_saving_leaves_no_temporary_file_behind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "accounts.json"
            (Path(tmp) / ".gitignore").write_text("*\n", encoding="utf-8")
            ACCOUNTS.save_store({"version": 1, "accounts": []}, path)
            self.assertEqual([p.name for p in Path(tmp).iterdir() if p.name.startswith(".accounts-")], [])


class IgnorePreconditionTests(unittest.TestCase):
    """The store sits inside the repo, so the ignore rule is the protection."""

    def test_the_real_store_path_is_ignored_by_git(self) -> None:
        # Guards the arrangement itself: if the .gitignore ever stops covering
        # the store, this fails here rather than in a commit that leaks a token.
        ACCOUNTS.assert_ignored(ACCOUNTS.STORE_PATH)

    def test_writing_is_refused_where_git_would_track_the_file(self) -> None:
        tracked = REPOSITORY_ROOT / "tests" / "not-a-real-store.json"
        with self.assertRaisesRegex(ACCOUNTS.StoreError, "would track"):
            ACCOUNTS.assert_ignored(tracked)
        self.assertFalse(tracked.exists())


class DiscoverTests(unittest.TestCase):
    """Adding is a pick, so something has to enumerate the choices first."""

    def test_finds_kaggle_json_files_and_names_the_account_in_each(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_credential(Path(tmp), "kaggle.json", username="diego", key="K1")
            write_credential(Path(tmp), "kaggle (1).json", username="milab", key="K2")
            found = ACCOUNTS.discover_credentials([tmp])
            self.assertEqual(sorted(u for e in found for u in e["usernames"]),
                             ["diego", "milab"])
            self.assertTrue(all(not e["problems"] for e in found))

    def test_reports_an_unreadable_candidate_instead_of_hiding_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "kaggle.json").write_text("garbage", encoding="utf-8")
            (entry,) = ACCOUNTS.discover_credentials([tmp])
            self.assertEqual(entry["usernames"], [])
            self.assertIn("not valid JSON", entry["problems"][0])

    def test_a_txt_list_is_only_looked_for_in_the_inbox(self) -> None:
        # Reading every text file in somebody's Downloads to see what is inside
        # is not a thing to do quietly; the inbox is the folder that opts in.
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "cuentas.txt").write_text("one, KEY1\n", encoding="utf-8")
            self.assertEqual(ACCOUNTS.discover_credentials([tmp]), [])
            original, ACCOUNTS.INBOX_DIR = ACCOUNTS.INBOX_DIR, Path(tmp)
            try:
                (entry,) = ACCOUNTS.discover_credentials([tmp])
                self.assertEqual(entry["usernames"], ["one"])
            finally:
                ACCOUNTS.INBOX_DIR = original

    def test_ignores_unrelated_json_and_missing_folders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_credential(Path(tmp), "settings.json", username="diego", key="K1")
            self.assertEqual(ACCOUNTS.discover_credentials([tmp, tmp + "/nope"]), [])

    def test_the_same_file_reached_twice_is_offered_once(self) -> None:
        # Two search folders can resolve to the same place; the same credential
        # listed twice would read as two accounts to add.
        with tempfile.TemporaryDirectory() as tmp:
            write_credential(Path(tmp), "kaggle.json", username="diego", key="K1")
            found = ACCOUNTS.discover_credentials([tmp, tmp + "/"])
            self.assertEqual(len(found), 1)

    def test_never_carries_the_key_out_of_the_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            write_credential(Path(tmp), "kaggle.json", username="diego", key="SECRET")
            self.assertNotIn("SECRET", json.dumps(ACCOUNTS.discover_credentials([tmp])))


class InboxTests(unittest.TestCase):
    """The folder that exists so the user has somewhere to put the download."""

    def test_the_inbox_ships_already_ignored_by_git(self) -> None:
        # It lives inside the repository, so the ignore rule is the whole
        # protection — and it has to hold before the first token lands, not after.
        self.assertTrue(ACCOUNTS.INBOX_DIR.is_dir())
        self.assertIs(ACCOUNTS.is_ignored(ACCOUNTS.INBOX_DIR / "kaggle.json"), True)
        self.assertIs(ACCOUNTS.is_ignored(ACCOUNTS.INBOX_DIR / "kaggle (1).json"), True)

    def test_the_inbox_gitignore_itself_stays_tracked(self) -> None:
        self.assertIs(ACCOUNTS.is_ignored(ACCOUNTS.INBOX_DIR / ".gitignore"), False)

    def test_is_searched_for_candidates(self) -> None:
        self.assertIn(str(ACCOUNTS.INBOX_DIR), ACCOUNTS.CREDENTIAL_SEARCH_DIRS)

    def test_recognises_what_came_from_the_inbox_and_what_did_not(self) -> None:
        self.assertTrue(ACCOUNTS.in_inbox(ACCOUNTS.INBOX_DIR / "kaggle.json"))
        self.assertFalse(ACCOUNTS.in_inbox(Path.home() / "Downloads" / "kaggle.json"))
        # The inbox folder itself is not a file inside it.
        self.assertFalse(ACCOUNTS.in_inbox(ACCOUNTS.INBOX_DIR))

    def test_shows_inbox_paths_by_that_name(self) -> None:
        self.assertEqual(
            ACCOUNTS.display_path(ACCOUNTS.INBOX_DIR / "kaggle.json"), "kaggle-inbox/kaggle.json")


class InteractiveEntryTests(unittest.TestCase):
    """The way in when no file exists — and the one place it must not work."""

    def test_refuses_when_stdin_is_not_a_terminal(self) -> None:
        # Run from an agent's shell there is nobody to type and nothing to
        # suppress the echo, so it must fail rather than find a way.
        with self.assertRaisesRegex(ACCOUNTS.UsageError, "real terminal"):
            ACCOUNTS.read_credential_interactively()

    def test_there_is_no_flag_that_takes_a_key_on_the_command_line(self) -> None:
        # A secret in argv is in the process list and the shell history. If this
        # ever fails, someone added the convenience that undoes the whole design.
        source = Path(ACCOUNTS.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"--key"', source)


class UsernameTests(unittest.TestCase):
    def test_accepts_ordinary_kaggle_usernames(self) -> None:
        for username in ("diego", "diego-lab", "diego_2", "d.p"):
            self.assertTrue(ACCOUNTS.USERNAME_PATTERN.match(username), username)

    def test_rejects_what_could_not_be_a_username(self) -> None:
        for username in ("", "with space", "slash/es", "a" * 65):
            self.assertFalse(ACCOUNTS.USERNAME_PATTERN.match(username), username)

    def test_an_account_is_its_username_with_no_second_name_for_it(self) -> None:
        # Two ways to refer to one account means one of them is always wrong.
        source = Path(ACCOUNTS.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"--alias"', source)
        self.assertNotIn('a["alias"]', source)


class ValidateTests(unittest.TestCase):
    """Which authentication scheme a credential is offered under.

    Two Kaggle token formats are live at once and they do not authenticate the
    same way, so the cost of getting this wrong is a working account reported
    as expired — the one verdict this command must never invent.
    """

    def run_validate(self, *outcomes: object) -> list[str]:
        """Validate against a scripted sequence of attempts, returning schemes."""
        tried: list[str] = []
        remaining = list(outcomes)

        def attempt(scheme: str, credential: str) -> None:
            tried.append(scheme)
            outcome = remaining.pop(0)
            if outcome is not None:
                raise outcome

        with unittest.mock.patch.object(ACCOUNTS, "_attempt", attempt):
            ACCOUNTS.validate("diego", "key")
        return tried

    def test_a_classic_key_is_proven_by_basic_and_asks_nothing_further(self) -> None:
        self.assertEqual(self.run_validate(None), ["Basic"])

    def test_a_token_basic_refuses_is_retried_as_a_bearer(self) -> None:
        rejected = ACCOUNTS.CredentialError("Kaggle rejected it (HTTP 401) — expired")
        self.assertEqual(self.run_validate(rejected, None), ["Basic", "Bearer"])

    def test_refused_under_both_schemes_is_a_refusal(self) -> None:
        rejected = ACCOUNTS.CredentialError("Kaggle rejected it (HTTP 401) — expired")
        with self.assertRaises(ACCOUNTS.CredentialError):
            self.run_validate(rejected, rejected)

    def test_an_unreachable_kaggle_is_not_retried_into_a_second_outage(self) -> None:
        # A dropped connection says nothing about the credential, so there is
        # nothing for a second scheme to learn — and the retry would double the
        # wait before the user is told the network is what failed.
        unreachable = ACCOUNTS.CredentialError("could not reach Kaggle to validate it")
        with self.assertRaises(ACCOUNTS.CredentialError):
            self.run_validate(unreachable)


class ValidateOneAccountTests(unittest.TestCase):
    """`validate --account <username> --json` -- the read-only probe
    `remote_cli preflight` runs per worker: it re-checks only the named
    stored accounts, takes in nothing from the inbox and writes nothing."""

    def _run(self, accounts: list[str], ok: set[str]) -> tuple[int, dict, list]:
        store = {"version": 1, "accounts": [{"username": "diego", "key": "K1"},
                                            {"username": "sofia", "key": "K2"}]}
        checked: list[str] = []

        def validate(username: str, key: str) -> None:
            checked.append(username)
            if username not in ok:
                raise ACCOUNTS.CredentialError("Kaggle rejected it (HTTP 401)")

        def forbidden(*args, **kwargs):
            raise AssertionError("validate --account wrote or read the inbox")

        buffer = io.StringIO()
        with unittest.mock.patch.object(ACCOUNTS, "load_store", lambda: store), \
                unittest.mock.patch.object(ACCOUNTS, "validate", validate), \
                unittest.mock.patch.object(ACCOUNTS, "save_store", forbidden), \
                unittest.mock.patch.object(ACCOUNTS, "inbox_files", forbidden), \
                contextlib.redirect_stdout(buffer):
            code = ACCOUNTS.cmd_validate(argparse.Namespace(
                files=[], interactive=False, account=accounts, json=True))
        return code, json.loads(buffer.getvalue()), checked

    def test_only_the_named_account_is_checked_and_nothing_is_written(self) -> None:
        code, payload, checked = self._run(["diego"], ok={"diego"})
        self.assertEqual(code, 0)
        self.assertEqual(checked, ["diego"])
        self.assertEqual(payload, {"accounts": [{"username": "diego", "ok": True,
                                                 "detail": "ok"}]})
        self.assertNotIn("K1", json.dumps(payload))

    def test_a_rejected_or_unstored_account_fails(self) -> None:
        code, payload, _ = self._run(["sofia", "nobody"], ok=set())
        self.assertEqual(code, 1)
        rows = {row["username"]: row for row in payload["accounts"]}
        self.assertFalse(rows["sofia"]["ok"])
        self.assertIn("401", rows["sofia"]["detail"])
        self.assertFalse(rows["nobody"]["ok"])
        self.assertIn("not stored", rows["nobody"]["detail"])

    def test_json_without_account_is_refused_before_anything_is_read(self) -> None:
        """`--json` is only defined with `--account`; without it the command
        used to run the interactive-format validate and exit 0."""
        def forbidden(*args, **kwargs):
            raise AssertionError("validate --json read the store or the inbox")

        out, err = io.StringIO(), io.StringIO()
        with unittest.mock.patch.object(ACCOUNTS, "load_store", forbidden), \
                unittest.mock.patch.object(ACCOUNTS, "inbox_files", forbidden), \
                unittest.mock.patch.object(sys, "argv", ["accounts_cli.py", "validate", "--json"]), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ACCOUNTS.main()
        self.assertNotEqual(code, 0)
        self.assertIn("JSON_NEEDS_ACCOUNT", err.getvalue())
        self.assertEqual(out.getvalue(), "")

    def test_the_parser_accepts_account_and_json_on_validate(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"--account"', source)


class DiscoverCommandTests(unittest.TestCase):
    def test_marks_which_found_accounts_are_already_stored(self) -> None:
        # The command reports over the store, which the parsing tests never
        # reach: a discover that crashes here takes the opening question with it.
        candidate = {"path": "kaggle-inbox/list.md", "usernames": ["diego", "sofia"],
                     "problems": []}
        with unittest.mock.patch.object(
            ACCOUNTS, "load_store", lambda: {"accounts": [{"username": "diego"}]}
        ), unittest.mock.patch.object(
            ACCOUNTS, "discover_credentials", lambda: [candidate]
        ):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = ACCOUNTS.cmd_discover(argparse.Namespace(json=True))

        self.assertEqual(code, 0)
        (entry,) = json.loads(buffer.getvalue())["candidates"]
        self.assertEqual(
            entry["accounts"],
            [{"username": "diego", "stored": True}, {"username": "sofia", "stored": False}],
        )
        self.assertIn("1 already stored", entry["note"])


class MaterializeCommandTests(unittest.TestCase):
    """`materialize` — the one non-interactive way a stored credential
    leaves this file, as a FILE handed to a destination, never as a printed
    value. Reuses `save_store()`'s exact atomic shape at a NEW destination,
    so what these tests are really asking is whether that reuse actually
    holds somewhere the store's own writes never touch. C1.

    The file written is a plain-text token — no JSON wrapper, no
    `username` field — because that is the shape Kaggle's own client reads
    off `KAGGLE_API_TOKEN`: a path, whose contents (stripped) are the
    token itself.
    """

    def _materialize(
        self, worker: str, into: Path, *, accounts: list[dict] | None = None,
    ) -> tuple[int, str]:
        store = {
            "version": 1,
            "accounts": accounts if accounts is not None else [
                {"username": worker, "key": "K-not-a-real-key"}
            ],
        }
        buffer = io.StringIO()
        with unittest.mock.patch.object(ACCOUNTS, "load_store", lambda: store):
            with contextlib.redirect_stdout(buffer):
                code = ACCOUNTS.cmd_materialize(
                    argparse.Namespace(worker=worker, into=str(into), json=True)
                )
        return code, buffer.getvalue()

    def test_writes_the_config_atomically_owner_only_under_a_gitignored_destination(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = (Path(tmp) / "creds" / "w1").resolve()
            dest.mkdir(parents=True)
            (dest / ".gitignore").write_text("*\n", encoding="utf-8")

            code, out = self._materialize("w1", dest)

            self.assertEqual(code, 0)
            token_path = dest / "token"
            self.assertTrue(token_path.exists())
            self.assertEqual(stat.S_IMODE(token_path.stat().st_mode), 0o600)
            # Plain text, nothing else: no JSON wrapper, no `username`
            # field — this is the exact shape Kaggle's client reads a
            # token's contents as (stripped).
            self.assertEqual(token_path.read_text(encoding="utf-8").strip(), "K-not-a-real-key")

            payload = json.loads(out)
            self.assertEqual(payload, {"worker": "w1", "tokenPath": str(token_path)})
            # A destination is printed, never a value — the whole point of
            # this command.
            self.assertNotIn("K-not-a-real-key", out)
            self.assertEqual(
                [p.name for p in dest.iterdir() if p.name.startswith(".kaggle-")], []
            )

    def test_refuses_a_destination_with_no_ignore_precondition_and_writes_nothing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Deliberately no `.gitignore` reachable from this destination.
            dest = Path(tmp) / "unsafe" / "w1"

            with self.assertRaisesRegex(ACCOUNTS.StoreError, "gitignore"):
                self._materialize("w1", dest)

            # A refusal must leave nothing behind — not even an empty
            # scaffold directory the credential was never actually put in.
            self.assertFalse(dest.exists())

    def test_refuses_an_unknown_worker_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "creds" / "ghost"

            with self.assertRaisesRegex(ACCOUNTS.UsageError, "no such account"):
                self._materialize(
                    "ghost", dest, accounts=[{"username": "w1", "key": "K1"}]
                )

            self.assertFalse(dest.exists())


class RemoveCommandTests(unittest.TestCase):
    """`remove` deletes what it says it deletes.

    Reachable red: before this change it deleted the store entry and left
    `store/workers/<username>/token` behind — a live credential for an
    account this store no longer admits to holding, sitting at the exact
    path the consuming skill's `materialize` contract names. The store
    said the account was gone; the filesystem disagreed.
    """

    def _remove(
        self, usernames: list[str], store_dir: Path, accounts: list[dict]
    ) -> tuple[int, dict, str]:
        store = {"version": 1, "accounts": accounts}
        saved: dict = {}
        buffer = io.StringIO()
        with unittest.mock.patch.object(ACCOUNTS, "load_store", lambda: store), \
                unittest.mock.patch.object(
                    ACCOUNTS, "save_store", lambda payload: saved.update(payload)
                ), \
                unittest.mock.patch.object(ACCOUNTS, "STORE_DIR", store_dir):
            with contextlib.redirect_stdout(buffer):
                code = ACCOUNTS.cmd_remove(argparse.Namespace(usernames=usernames))
        return code, saved, buffer.getvalue()

    @staticmethod
    def _materialized(store_dir: Path, username: str, key: str) -> Path:
        token_path = store_dir / "workers" / username / "token"
        token_path.parent.mkdir(parents=True)
        token_path.write_text(key + "\n", encoding="utf-8")
        return token_path

    def test_removing_an_account_deletes_the_credential_materialize_wrote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store_dir = Path(tmp) / "store"
            token_path = self._materialized(store_dir, "w1", "K-not-a-real-key")
            kept = self._materialized(store_dir, "w2", "K-also-not-a-real-key")

            code, saved, out = self._remove(
                ["w1"],
                store_dir,
                [{"username": "w1", "key": "K-not-a-real-key"},
                 {"username": "w2", "key": "K-also-not-a-real-key"}],
            )

            self.assertEqual(code, 0)
            self.assertFalse(token_path.exists())
            self.assertFalse(token_path.parent.exists())
            self.assertEqual([a["username"] for a in saved["accounts"]], ["w2"])
            # The account that stays keeps the credential it materialized.
            self.assertTrue(kept.exists())
            self.assertNotIn("K-not-a-real-key", out)

    def test_an_account_that_never_materialized_one_is_removed_without_complaint(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store_dir = Path(tmp) / "store"

            code, saved, out = self._remove(
                ["w1"], store_dir, [{"username": "w1", "key": "K-not-a-real-key"}]
            )

            self.assertEqual(code, 0)
            self.assertEqual(saved["accounts"], [])
            self.assertIn("Removed 1", out)

    def test_a_refused_batch_deletes_no_credential_at_all(self) -> None:
        """The same all-or-nothing rule the store entries already had: a
        typo that deletes only the names it happened to match is worse than
        deleting nothing.
        """
        with tempfile.TemporaryDirectory() as tmp:
            store_dir = Path(tmp) / "store"
            token_path = self._materialized(store_dir, "w1", "K-not-a-real-key")

            with self.assertRaisesRegex(ACCOUNTS.UsageError, "no such account"):
                self._remove(
                    ["w1", "ghost"],
                    store_dir,
                    [{"username": "w1", "key": "K-not-a-real-key"}],
                )

            self.assertTrue(token_path.exists())


class MaterializedTokenDoctrineTests(unittest.TestCase):
    """`SKILL.md` must state the byte shape `materialize` writes, and the
    suite holds that statement to what the command actually does.

    Why this exists at all: `materialize` appeared NOWHERE in this skill's
    doctrine. The shape it writes was stated only in a docstring and a
    test, and the skill that consumes it stated a different shape in its
    own doctrine — so the producer and the consumer disagreed for as long
    as they did because there was no place the two could be compared. A
    prose paragraph would not have fixed that; a table each row of which is
    re-derived from a real `materialize` run does.

    The enumeration below lives here rather than in `accounts_cli.py`
    because nothing in the command needs it — every entry is bound to an
    assertion made against a genuinely materialized file, so a row cannot
    be added without writing the check that proves it, and a check cannot
    exist without a row naming it.
    """

    HEADER = "| # | id | Property | Held to code by |"

    CHECKS = (
        "destination",
        "content",
        "trailing-newline",
        "encoding",
        "file-mode",
        "directory-mode",
        "atomicity",
        "removal",
    )

    KEY = "K-not-a-real-key"

    def _table_rows(self) -> list:
        text = SKILL_MD.read_text(encoding="utf-8")
        lines = text.split("\n")
        try:
            start = next(
                i for i, line in enumerate(lines) if line.strip() == self.HEADER
            )
        except StopIteration:
            self.fail(
                f"kaggle-accounts/SKILL.md has no materialized-token table: the "
                f"exact header {self.HEADER!r} was not found"
            )
        rows = []
        for line in lines[start + 1:]:
            stripped = line.strip()
            if not stripped.startswith("|"):
                break
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if all(set(cell) <= {"-", ":"} and cell for cell in cells):
                continue
            rows.append(cells)
        return rows

    @contextlib.contextmanager
    def _materialized(self):
        """One real `materialize` run, into a temp store the command
        believes is its own. Every check below reads this same file.
        """
        with tempfile.TemporaryDirectory() as tmp:
            store_dir = Path(tmp) / "store"
            dest = store_dir / "workers" / "w1"
            dest.mkdir(parents=True)
            (dest / ".gitignore").write_text("*\n", encoding="utf-8")
            store = {"version": 1, "accounts": [{"username": "w1", "key": self.KEY}]}
            buffer = io.StringIO()
            with unittest.mock.patch.object(ACCOUNTS, "load_store", lambda: store), \
                    unittest.mock.patch.object(ACCOUNTS, "STORE_DIR", store_dir):
                with contextlib.redirect_stdout(buffer):
                    code = ACCOUNTS.cmd_materialize(
                        argparse.Namespace(worker="w1", into=None, json=True)
                    )
                self.assertEqual(code, 0)
                yield store_dir, json.loads(buffer.getvalue())

    def _check_destination(self, store_dir: Path, payload: dict) -> None:
        expected = store_dir / "workers" / "w1" / "token"
        self.assertEqual(Path(payload["tokenPath"]), expected)
        with unittest.mock.patch.object(ACCOUNTS, "STORE_DIR", store_dir):
            self.assertEqual(ACCOUNTS.worker_token_path("w1"), expected)

    def _check_content(self, store_dir: Path, payload: dict) -> None:
        text = Path(payload["tokenPath"]).read_text(encoding="utf-8")
        self.assertEqual(text.strip(), self.KEY)
        # Nothing else: no JSON wrapper, no `username` field.
        self.assertNotIn("username", text)
        self.assertNotIn("{", text)

    def _check_trailing_newline(self, store_dir: Path, payload: dict) -> None:
        self.assertTrue(
            Path(payload["tokenPath"]).read_text(encoding="utf-8").endswith("\n")
        )

    def _check_encoding(self, store_dir: Path, payload: dict) -> None:
        raw = Path(payload["tokenPath"]).read_bytes()
        self.assertEqual(raw.decode("utf-8"), self.KEY + "\n")

    def _check_file_mode(self, store_dir: Path, payload: dict) -> None:
        mode = stat.S_IMODE(Path(payload["tokenPath"]).stat().st_mode)
        self.assertEqual(mode, 0o600)

    def _check_directory_mode(self, store_dir: Path, payload: dict) -> None:
        mode = stat.S_IMODE(Path(payload["tokenPath"]).parent.stat().st_mode)
        self.assertEqual(mode, 0o700)

    def _check_atomicity(self, store_dir: Path, payload: dict) -> None:
        dest = Path(payload["tokenPath"]).parent
        self.assertEqual(
            [p.name for p in dest.iterdir() if p.name.startswith(".kaggle-")], []
        )
        source = inspect.getsource(ACCOUNTS.cmd_materialize)
        self.assertIn("mkstemp", source)
        self.assertIn("os.replace", source)

    def _check_removal(self, store_dir: Path, payload: dict) -> None:
        token_path = Path(payload["tokenPath"])
        self.assertTrue(token_path.exists())
        store = {"version": 1, "accounts": [{"username": "w1", "key": self.KEY}]}
        with unittest.mock.patch.object(ACCOUNTS, "load_store", lambda: store), \
                unittest.mock.patch.object(ACCOUNTS, "save_store", lambda payload: None), \
                unittest.mock.patch.object(ACCOUNTS, "STORE_DIR", store_dir):
            with contextlib.redirect_stdout(io.StringIO()):
                ACCOUNTS.cmd_remove(argparse.Namespace(usernames=["w1"]))
        self.assertFalse(token_path.exists())

    def test_the_table_documents_exactly_the_properties_held_to_code(self) -> None:
        documented = [row[1].strip("`") for row in self._table_rows()]
        undocumented = [c for c in self.CHECKS if c not in documented]
        self.assertEqual(
            undocumented, [],
            f"proven by this suite and absent from SKILL.md's table: {undocumented}",
        )
        invented = [c for c in documented if c not in self.CHECKS]
        self.assertEqual(
            invented, [],
            f"documented in SKILL.md's table and proven nowhere: {invented}",
        )
        self.assertEqual(documented, list(self.CHECKS), "the table's order is the contract")

    def test_every_row_names_a_property_and_where_it_is_held(self) -> None:
        rows = self._table_rows()
        for row in rows:
            self.assertEqual(len(row), 4, row)
            for cell in row:
                self.assertTrue(cell, row)

    def test_every_documented_property_holds_against_a_real_materialize(self) -> None:
        with self._materialized() as (store_dir, payload):
            for row_id in self.CHECKS:
                with self.subTest(property=row_id):
                    check = getattr(self, "_check_" + row_id.replace("-", "_"))
                    check(store_dir, payload)

    def test_the_doctrine_names_the_command_and_what_reads_what_it_writes(self) -> None:
        """The gap this change closes is total: `materialize` was not named
        anywhere in this document, so the one command another skill depends
        on was invisible to the doctrine that governs this one.
        """
        text = SKILL_MD.read_text(encoding="utf-8")
        self.assertIn("materialize", text)
        lowered = text.lower()
        self.assertIn("stripped", lowered)
        self.assertIn("value", lowered)


class AccountVocabularyLeakTests(unittest.TestCase):
    """A tenth guard, in the family of `remote-execution`'s eight
    `*_module_names_no_service` tests plus its `TargetVocabularyLeakTests`
    (`tests/test_remote_execution.py`). Those forbid naming a SERVICE outside
    `adapters/kaggle.py`, and naming this forge's own TARGET product anywhere
    in the skill. Neither one polices a third, independent axis: this
    *machine's* real Kaggle account names — the vocabulary that leaked at
    `accounts_cli.py:251`, where `split_credential_line`'s docstring named a
    real account's display-name prefix as its worked example.

    Design: this machine's own sanctioned account listing, not a hardcoded
    list. `accounts_cli.py list --json` is the store's own sanctioned
    surface — usernames only, never a key — so the forbidden set is derived
    live rather than copied by hand. That means an account added tomorrow is
    covered automatically, and removing one here needs no edit to this test.
    The tradeoff is the one a hardcoded list does not have: the store lives
    under `skills/kaggle-accounts/store/`, which is gitignored, so a
    checkout with no accounts ever stored yields an empty forbidden set. This
    test SKIPS rather than passes when that happens, so "0 accounts to check"
    is visibly distinct in the run summary (`skipped=1`) from "N accounts
    checked, none leaked" — a pass here is never proof of a clean tree on a
    machine that never authenticated one.

    Past the literal usernames, this generalizes the same way
    `TargetVocabularyLeakTests` generalized a target's product name past its
    exact spelling
    — but only when the generalization is corroborated by the store itself.
    Two or more stored usernames that share a digit-stripped stem (`Mira-
    dor51` and `Mirador50` both stem to `Mirador`) prove that the
    stem is the human-meaningful, reused part, the same way multiple real
    spellings of one product proved that one was. A singleton account's stem
    is deliberately NOT added on its own — `Mateo9901` stems to `Mateo`, a
    common first name, and banning it unconditionally would flag ordinary
    prose (a citation, an example name) that has nothing to do with this
    leak. That is narrower than exhaustive: an account whose exact spelling
    is disguised in a way no other stored account corroborates (as `Mira-
    dor XX` disguised `Mirador51`/`Mirador50` before this test
    existed) would slip through unless a sibling account happens to share
    its stem. (The four names above are invented stand-ins, not this
    machine's real stored usernames — this class's own file is now IN
    SCOPE below, so it cannot spell the real ones here without tripping
    itself.)

    Scoped to every tracked file under `skills/` AND `tests/` — this test's
    own file lives under `tests/`, so unlike `TargetVocabularyLeakTests` it
    DOES scan itself, which is why the account names above are invented
    rather than real. The scope widened past `.py` on 2026-09-25, after a
    real account name reached a `SKILL.md` and a `references/usage.md` —
    neither a Python source — while this guard was only ever pointed at
    `skills/**/*.py`, and a matching gap left every non-`.py` fixture and
    docstring under `tests/` unscanned too. `openspec/changes/archive/` is
    excluded on purpose, not by omission: those are archived change
    reports, this repository's own historical record, and this
    repository's doctrine holds that a change is undeclared, never
    deleted — a guard that reddens on that history would demand rewriting
    the record just to stay green, which inverts the doctrine instead of
    enforcing it. See `_tracked_skill_scripts` for the exact pathspec.
    """

    def _stored_usernames(self) -> list[str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "list", "--json"],
            capture_output=True, text=True, check=True,
        )
        return [a["username"] for a in json.loads(result.stdout)["accounts"]]

    def _forbidden_literals(self, usernames: list[str]) -> set[str]:
        stems = [re.sub(r"\d+$", "", u) for u in usernames]
        stem_counts = Counter(s.lower() for s in stems)
        shared_stems = {s.lower() for s in stems if stem_counts[s.lower()] >= 2}
        return {u.lower() for u in usernames} | shared_stems

    def test_no_skill_source_names_a_real_account_of_this_machine(self) -> None:
        usernames = self._stored_usernames()
        if not usernames:
            self.skipTest(
                "no accounts stored on this machine (store is gitignored and "
                "empty here) — nothing to check, not a proven-clean tree"
            )
        forbidden = self._forbidden_literals(usernames)
        scripts = self._tracked_skill_scripts()
        self.assertTrue(scripts, "no tracked skill sources found to scan")
        for script in scripts:
            try:
                source = script.read_text(encoding="utf-8").lower()
            except UnicodeDecodeError:
                # Not valid UTF-8 (a binary fixture such as
                # tests/fixtures/e2e/paper.pdf) -- best-effort decode rather
                # than letting the guard crash instead of reporting a leak.
                # See the docstring on this method for why that tradeoff is
                # accepted rather than excluding the file outright.
                source = script.read_bytes().decode(
                    "utf-8", errors="replace"
                ).lower()
            for leaked in forbidden:
                self.assertNotIn(leaked, source, f"{leaked!r} in {script}")

    @staticmethod
    def _tracked_skill_scripts() -> list[Path]:
        """The tracked sources this repository is responsible for.

        Scoped to `skills/` AND `tests/` — every tracked file in either
        tree, not only `*.py`. It used to be `skills/**/*.py` alone; that
        missed `tests/` entirely (this very file included) and missed every
        non-Python file (a `SKILL.md`, a `references/usage.md`) in the tree
        it did scan. A real account name reached both kinds of gap before
        this widened.

        Deliberately `git ls-files` rather than `rglob("*")`: a skill may
        keep its own `.venv`, and walking the tree reaches vendored
        third-party code — including fixtures that are not valid UTF-8 at
        all. `git ls-files` only ever lists what this repository actually
        versions, so it never walks into a `.venv` or `node_modules` in the
        first place; a dependency naming something is not this skill
        leaking it. What we version is what we are responsible for. A
        tracked fixture CAN still be binary or non-UTF-8 (see
        `tests/fixtures/e2e/paper.pdf`), so the caller above still guards
        the read against `UnicodeDecodeError` rather than assuming one.

        `openspec/changes/archive/` is excluded EXPLICITLY here, not merely
        left out because it falls outside `skills/`/`tests/`: this pathspec
        is the one place that boundary is spelled out, so a later widening
        of the include list (say, adding `openspec/` for some unrelated
        reason) does not silently re-open 20 leaked occurrences across 8
        archived change reports. Archived changes are this repository's
        historical record, and this repository's doctrine holds that a
        change is undeclared, never deleted — rewriting that record to
        satisfy this guard would be backwards.
        """
        listed = subprocess.run(
            [
                "git", "ls-files", "-z", "--",
                "skills", "tests",
                ":!:openspec/changes/archive",
            ],
            cwd=REPOSITORY_ROOT, capture_output=True, text=True, check=True,
        )
        return sorted(REPOSITORY_ROOT / name
                      for name in listed.stdout.split("\0") if name)


if __name__ == "__main__":
    unittest.main()
