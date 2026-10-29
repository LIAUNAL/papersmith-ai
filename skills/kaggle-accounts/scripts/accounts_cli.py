#!/usr/bin/env python3
"""Kaggle credentials: prove they work, keep the ones that do, drop the rest.

The user supplies the credentials by hand — a `kaggle.json` downloaded from
Kaggle, or a `.txt`/`.md` list with one `username key` per line, left in the inbox. That
being manual is what this is *for*: the work worth automating is not moving a
file, it is answering **does this account actually authenticate**, which is a
question only Kaggle can answer and one that stops being true over time.

So there are two operations and no more. ``validate`` re-checks every stored
account and takes in whatever is new, keeping only what authenticates.
``remove`` deletes what you no longer want. Everything else — ``list``,
``discover`` — exists to build the choices for those two.

Validating is not a setup step. Tokens get expired and rotated, and an account
that quietly stopped working does not fail when you add it; it fails hours later
in the middle of a run. That is why the stored accounts are re-checked every
time, not just the new ones.

An account is its Kaggle username. There is no alias: a second name for the same
thing buys nothing and gives you two ways to refer to one account, one of which
is always the wrong one.

The store lives inside the repository, so a `.gitignore` is the only thing
standing between a token and a public commit. That makes the ignore rule a
**precondition**, not a courtesy: before writing, this asks git whether the
store path is genuinely ignored, and refuses to write if it is not. Checking the
effective answer beats checking that a file exists, because an ignore rule can
be present and still not match.

Keys are write-only from the outside. ``list`` reports usernames and never the
key, so an agent driving this CLI can offer you a choice of accounts without the
secret ever crossing into its context. Whatever launches the runs reads the
store directly.

A fourth command, ``materialize``, exists for code rather than a human at a
terminal: it writes one worker's stored credential to a plain-text token
file, atomically, and prints back where — never what. Nothing about it opens
a question; it is the one non-interactive way a credential this store
already holds reaches a file another process's own client can point itself
at.

Usage:
    python accounts_cli.py validate                 # re-check the store, take in the inbox
    python accounts_cli.py validate <file>…         # check these instead
    python accounts_cli.py validate --interactive   # run this one yourself, in a terminal
    python accounts_cli.py remove <username>…
    python accounts_cli.py list [--json]
    python accounts_cli.py discover [--json]
    python accounts_cli.py materialize --worker <username> [--into <dir>] --json

Exit codes: 0 everything checked out, 1 at least one account failed or was
rejected (the rest are stored), 2 usage/store/environment error (nothing was
written).
"""
from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

# .../skills/kaggle-accounts/scripts/accounts_cli.py
SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
STORE_NAME = "store"
STORE_FILE = "accounts.json"
# Both paths derive from the two declarations above, so the names the command
# center reads are the ones this CLI actually writes to. The declaration exists
# for the same reason `INBOX_NAME` does in remote-execution: a reader that
# restates the path puts one target's vocabulary into a file every workspace
# receives, and the skill that owns the store stops being its source of truth.
STORE_DIR = SKILL_ROOT / STORE_NAME
STORE_PATH = STORE_DIR / STORE_FILE

# Any authenticated endpoint proves the credential; this is the cheapest one.
# Kaggle answers 401 both anonymously and with a bad key, so 200 is the only
# thing that means "this credential is real".
VALIDATION_URL = "https://www.kaggle.com/api/v1/competitions/list?page=1"
VALIDATION_TIMEOUT = 20


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Follow no redirect: the validation request carries the credential, and a
    redirect would hand it to whatever host `Location` names. Returning `None`
    makes urllib raise the 3xx as an `HTTPError` (#106). This script ships to
    workspaces and imports nothing from papersmith, so `smith mcp kaggle`
    keeps its own copy of this handler."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# The only opener a request carrying a Kaggle credential goes through.
_OPENER = urllib.request.build_opener(_RefuseRedirects)

STORE_VERSION = 1
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# A folder that exists for this, so the flow does not depend on where a browser
# happens to save things. It ships already ignored by git.
#
# At the repository root, beside `guidance/` and `proposals/`, and not buried in
# the skill: a folder the user is asked to drop a file into has to be a folder
# they can find. The store stays inside the skill — nobody opens that one.
INBOX_NAME = "kaggle-inbox"
INBOX_DIR = REPO_ROOT / INBOX_NAME

# Where a downloaded credential actually lands. Direct children only: walking a
# home directory to find a two-field JSON file is slow, and reading every JSON
# somebody owns to see what is inside it is not a thing to do quietly.
CREDENTIAL_SEARCH_DIRS = (str(INBOX_DIR), "~/Downloads", "~/Desktop", "~/.kaggle", ".")
CREDENTIAL_GLOB = "kaggle*.json"
# A hand-written list of accounts, looked for in the inbox only. `.md` because
# that is what people actually reach for when writing a small table by hand.
INBOX_LIST_GLOBS = ("*.txt", "*.md")


TOKEN_FILENAME = "token"
WORKERS_DIRNAME = "workers"


def worker_token_path(worker: str) -> Path:
    """Where `materialize` puts one worker's credential when no `--into`
    overrides it — stated once, here, because two commands depend on it
    being the same place.

    `materialize` writes it and `remove` deletes it; a second spelling of
    this path in either one is how `remove` came to leave a live credential
    behind for an account the store no longer held.
    """
    return STORE_DIR / WORKERS_DIRNAME / worker / TOKEN_FILENAME


class UsageError(Exception):
    """The invocation itself is wrong; nothing was touched."""


class StoreError(Exception):
    """The store cannot be read or cannot be written safely."""


class CredentialError(Exception):
    """One credential was rejected; the rest of the batch still applies."""


# --- store -----------------------------------------------------------------


def load_store(path: Path | None = None) -> dict:
    """Read the store, or return an empty one. Raises `StoreError` if corrupt.

    Fail closed on a malformed file: treating unreadable JSON as "no accounts"
    would make the next `add` overwrite credentials that are still in there.
    """
    path = STORE_PATH if path is None else path
    if not path.exists():
        return {"version": STORE_VERSION, "accounts": []}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise StoreError(f"{path} is not valid JSON: {exc.msg} (line {exc.lineno})")
    except OSError as exc:
        raise StoreError(f"{path} could not be read: {exc.strerror}")
    if not isinstance(data, dict) or not isinstance(data.get("accounts"), list):
        raise StoreError(f"{path} is not a credential store (expected an 'accounts' list)")
    for entry in data["accounts"]:
        if not isinstance(entry, dict) or not entry.get("username"):
            raise StoreError(f"{path} holds an entry with no username")
    return data


def is_ignored(path: Path) -> bool | None:
    """Whether git would ignore this path. `None` when git could not answer.

    Asks for the effective answer rather than trusting that a `.gitignore`
    exists — a rule can be present and still fail to match the path it was
    written for.
    """
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", str(path)],
            cwd=SKILL_ROOT,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    # 0 = ignored, 1 = not ignored, anything else (not a repository, for
    # instance) is git declining to answer, not evidence of exposure.
    return {0: True, 1: False}.get(result.returncode)


def assert_ignored(path: Path) -> None:
    """Refuse to write a secret into a path git would track. Raises `StoreError`.

    The store is deliberately inside the repository, which means the ignore rule
    is the entire protection — so it is checked before writing, not assumed.
    """
    answer = is_ignored(path)
    if answer is False:
        raise StoreError(
            f"git would track {path} — restore {path.parent}/.gitignore before storing a token here"
        )
    if answer is None and not (path.parent / ".gitignore").exists():
        # No git to ask: fall back to the weaker check rather than refusing to
        # work outside a checkout.
        raise StoreError(
            f"{path.parent}/.gitignore is missing — restore it before storing a token here"
        )


def save_store(store: dict, path: Path | None = None) -> None:
    """Write the store atomically with owner-only permissions.

    Atomic because a truncated write costs every credential in the file, not
    just the one being added.
    """
    path = STORE_PATH if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    assert_ignored(path)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".accounts-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(store, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise StoreError(f"{path} could not be written: {exc.strerror}")


# --- credentials -----------------------------------------------------------


#: `user, key` on one line. Comma, colon, semicolon, tab or spaces — whichever
#: the person writing the list happened to use, because a list of accounts is
#: typed by hand and a separator is not a thing to be strict about.
CREDENTIAL_SEPARATOR = re.compile(r"[\s,;:]+")

#: Markdown a hand-written list arrives wearing. Nobody writing accounts into a
#: `.md` types bare lines — they type a bullet list or a table, and a parser that
#: only understands bare lines calls all of it malformed.
LIST_MARKER = re.compile(r"^[-*+]\s+")
TABLE_SEPARATOR = re.compile(r"^\|?[\s:|-]+\|?$")
#: Backticks and asterisks only. NOT `_`: markdown italicises with it, but
#: Kaggle tokens contain it, and stripping it turns a good key into a 401 that
#: looks like an expired token and sends somebody to regenerate a working one.
#: Corrupting a secret quietly is worse than failing to undecorate it.
MARKDOWN_DECORATION = re.compile(r"[`*]")


def username_problem(username: str) -> str | None:
    """Why this cannot be a Kaggle username, or `None` if it can.

    A name with a space is the case worth naming out loud, because it is not a
    typo — it is the **display name**, which is a different thing from the
    username and sits right next to it in Kaggle's own UI. Reporting that as
    "wrong number of fields" sends somebody to fix their punctuation when what
    is wrong is which of two names they copied.

    And it cannot be repaired later. A prefixed bearer token authenticates
    without Kaggle ever saying who it belongs to, so a display name stored as a
    username is simply wrong from then on, with nothing to catch it.
    """
    if " " in username:
        return (f"{username!r} has a space, so it is a display name — Kaggle usernames "
                "have none. Use the one in your profile URL (kaggle.com/<username>)")
    if not USERNAME_PATTERN.match(username):
        return f"{username!r} is not a usable Kaggle username"
    return None


def split_credential_line(line: str) -> list[str]:
    """The fields on one line, whether it is bare, a bullet, or a table row.

    An explicit delimiter wins over whitespace, and that ordering is the whole
    point. Splitting on any of them at once means a field can never *contain*
    one — so `Jane Doe, KGAT_…` came apart into three fields and was
    reported as malformed, when the person writing it had already said where the
    boundary was by putting a comma there. A delimiter someone typed is a
    statement; a space is a guess. Take the statement.
    """
    def clean(field: str) -> str:
        return MARKDOWN_DECORATION.sub("", field).strip()

    if "|" in line:
        return [clean(cell) for cell in line.strip().strip("|").split("|") if cell.strip()]
    bare = LIST_MARKER.sub("", line.strip())
    for delimiter in ("\t", ",", ";", ":"):
        if delimiter in bare:
            return [clean(field) for field in bare.split(delimiter)]
    return [clean(field) for field in CREDENTIAL_SEPARATOR.split(bare)]


def parse_credential_lines(text: str) -> list[dict]:
    """One credential per line: `username <sep> key`.

    Blank lines and `#` headings are skipped, so a list can be annotated — which
    is what people do with a file holding several accounts. Bullets and table
    pipes are stripped, because a `.md` is where somebody writes a small table by
    hand and being strict about its punctuation would reject the whole file.

    A malformed line becomes its own entry with a `problem` rather than an
    exception. The whole point of a list is that the good rows survive the bad
    ones; failing the file would throw away four working credentials because
    somebody left a stray word on line three.
    """
    lines = text.splitlines()
    entries: list[dict] = []
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or TABLE_SEPARATOR.match(stripped):
            continue
        # A row followed by `|---|---|` is the table's header, not an account.
        # Read from the structure rather than guessed at from the words in it.
        following = lines[number].strip() if number < len(lines) else ""
        if "|" in stripped and TABLE_SEPARATOR.match(following) and "|" in following:
            continue
        entry: dict = {"label": f"line {number}", "username": None, "key": None,
                       "problem": None}
        parts = [part for part in split_credential_line(stripped) if part]
        if len(parts) != 2:
            # Never quote the line back: half of it is a key, and echoing it
            # into a report is the leak this whole flow is built to avoid.
            entry["problem"] = f"expected `username key`, found {len(parts)} field(s)"
        else:
            username, key = parts
            entry["problem"] = username_problem(username)
            if entry["problem"] is None:
                entry["username"], entry["key"] = username, key
        entries.append(entry)
    return entries


def read_credentials(raw: str) -> list[dict]:
    """Every credential in a file — a `kaggle.json`, or a `.txt` list.

    Kaggle hands out one credential per downloaded JSON, but somebody managing
    several accounts writes them down in a list. Both arrive here; the caller
    validates each entry and keeps what passes.

    Raises `CredentialError` only for a failure of the file itself. Anything
    wrong with a single credential travels as that entry's `problem`, so one bad
    row never costs the rows around it.
    """
    path = Path(raw).expanduser()
    if not path.exists():
        raise CredentialError("file not found")
    if path.is_dir():
        raise CredentialError("is a directory, not a credential file")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        detail = getattr(exc, "strerror", None) or "not text"
        raise CredentialError(f"could not be read: {detail}")

    if path.suffix.lower() != ".json":
        entries = parse_credential_lines(text)
        if not entries:
            raise CredentialError("holds no credentials")
        return entries

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise CredentialError("not valid JSON — expected the kaggle.json Kaggle downloads")
    if not isinstance(data, dict):
        raise CredentialError("not a kaggle.json (expected a JSON object)")
    username, key = data.get("username"), data.get("key")
    if not isinstance(username, str) or not username.strip():
        raise CredentialError("no 'username' field")
    if not isinstance(key, str) or not key.strip():
        raise CredentialError("no 'key' field")
    return [{"label": path.name, "username": username.strip(), "key": key.strip(),
             "problem": None}]


def read_credential_interactively() -> tuple[str, str]:
    """Take a credential from a terminal prompt. Raises `UsageError`.

    The file flow cannot serve every case: the token may live in a password
    manager, or the download may be long gone. Without this, the only way left
    is pasting the key into a conversation, where it stays permanently — so
    refusing the paste while offering no alternative just moves the leak.

    Typed into this process's terminal, the key is in no message, no argv, and
    no shell history. There is deliberately no `--key` flag: a secret on a
    command line is in the process list and in `~/.zsh_history`, which is the
    same leak wearing a different hat.

    Refuses when stdin is not a terminal. Run from an agent's shell there is
    nobody to type and nothing to suppress the echo, which is exactly the
    situation this exists to avoid — so it fails instead of finding a way.
    """
    if not sys.stdin.isatty():
        raise UsageError(
            "--interactive needs a real terminal. Run it yourself in your shell, "
            "not through an agent — that is the whole point of the flag."
        )
    username = input("Kaggle username: ").strip()
    if not username:
        raise UsageError("no username given")
    key = getpass.getpass("Kaggle API key (input hidden): ").strip()
    if not key:
        raise UsageError("no key given")
    return username, key


def display_path(path: Path) -> str:
    """`kaggle-inbox/kaggle.json` or `~/Downloads/kaggle.json`, never absolute."""
    for root, prefix in ((INBOX_DIR, INBOX_NAME), (Path.home(), "~")):
        try:
            inside = path.resolve().relative_to(root.resolve())
        except (ValueError, OSError):
            continue
        # `relative_to` gives "." for the folder itself, which would render as
        # "inbox/." in the very message that tells the user where to put a file.
        return prefix if str(inside) == "." else f"{prefix}/{inside}"
    return str(path)


def in_inbox(path: Path) -> bool:
    """Whether a file came from the folder that exists to hand credentials over."""
    try:
        return INBOX_DIR.resolve() in path.resolve().parents
    except OSError:
        return False


def discover_credentials(folders: list[str] | None = None) -> list[dict]:
    """Candidate `kaggle.json` files, each with the account it holds.

    Asking "what is the path?" makes the user go find something the machine can
    see, and a mistyped path is a question asked twice. This finds the
    candidates so the choice can be a selection.

    Reporting the **username** of each file is the part that matters: Kaggle
    names every download `kaggle.json`, so three of them in one folder are
    indistinguishable by filename, and picking between identical names is not a
    choice. The key is read and dropped — it never leaves this process.
    """
    seen: set[Path] = set()
    found: list[dict] = []
    for folder in (folders or CREDENTIAL_SEARCH_DIRS):
        directory = Path(folder).expanduser()
        if not directory.is_dir():
            continue
        # A `.txt` full of accounts is only looked for in the inbox. Reading
        # every text file in somebody's Downloads to see whether it happens to
        # contain credentials is not a thing to do quietly; the inbox is the
        # folder that exists to say "this one is for you".
        patterns = [CREDENTIAL_GLOB]
        if directory.resolve() == INBOX_DIR.resolve():
            patterns.extend(INBOX_LIST_GLOBS)
        for path in sorted(p for pattern in patterns for p in directory.glob(pattern)):
            resolved = path.resolve()
            if resolved in seen or not path.is_file():
                continue
            seen.add(resolved)
            entry: dict = {"path": str(path), "display": display_path(path),
                           "usernames": [], "problems": []}
            try:
                for credential in read_credentials(str(path)):
                    if credential["problem"]:
                        entry["problems"].append(f"{credential['label']}: {credential['problem']}")
                    else:
                        entry["usernames"].append(credential["username"])
            except CredentialError as exc:
                entry["problems"].append(str(exc))
            found.append(entry)
    return found


def _attempt(scheme: str, credential: str) -> None:
    """One authenticated request. Raises `CredentialError`, or returns on 200."""
    request = urllib.request.Request(
        VALIDATION_URL,
        headers={
            "Authorization": f"{scheme} {credential}",
            "User-Agent": "papersmith-kaggle-accounts",
        },
    )
    try:
        with _OPENER.open(request, timeout=VALIDATION_TIMEOUT) as response:
            if response.status != 200:
                raise CredentialError(f"Kaggle answered HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise CredentialError("Kaggle rejected it (HTTP 401) — wrong username or expired token")
        if exc.code == 403:
            raise CredentialError("authenticated but forbidden (HTTP 403) — the account is restricted")
        raise CredentialError(f"Kaggle answered HTTP {exc.code}")
    except urllib.error.URLError as exc:
        raise CredentialError(f"could not reach Kaggle to validate it ({exc.reason}) — not saved")
    except TimeoutError:
        raise CredentialError(f"Kaggle did not answer within {VALIDATION_TIMEOUT}s — not saved")


def validate(username: str, key: str) -> None:
    """Prove the credential against the live API. Raises `CredentialError`.

    Two token formats are live at once, and they do not authenticate the same
    way. The classic 32-hex key is the password half of Basic `username:key`.
    The newer prefixed token is a bearer token that carries its own identity and
    is refused by Basic. Trying only one of them reports a working account as
    expired, which is the exact failure this whole command exists to catch, so
    a 401 from the first is a reason to try the other rather than a verdict.

    A network failure is reported as its own outcome. Discarding a good
    credential because the connection dropped, and saying it was invalid, would
    send the user to regenerate a token that was never the problem.
    """
    basic = base64.b64encode(f"{username}:{key}".encode()).decode()
    try:
        _attempt("Basic", basic)
    except CredentialError as rejected:
        # Only an outright rejection is worth a second attempt. A timeout or an
        # unreachable host says nothing about the credential, and retrying it
        # under another scheme would turn one network outage into two.
        if "401" not in str(rejected):
            raise
        _attempt("Bearer", key)


# --- commands --------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    accounts = load_store()["accounts"]
    if args.json:
        print(json.dumps(
            {"accounts": [{"username": a["username"]} for a in accounts]},
            indent=2,
        ))
        return 0
    if not accounts:
        print("No accounts stored.")
        return 0
    print(f"{len(accounts)} account(s):")
    for account in sorted(accounts, key=lambda a: a["username"]):
        print(f"  {account['username']}")
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    """List candidate credential files so adding can be a pick, not a path."""
    stored = {a["username"] for a in load_store()["accounts"]}
    found = discover_credentials()
    for entry in found:
        entry["accounts"] = [
            {"username": username, "stored": username in stored}
            for username in entry["usernames"]
        ]
        known = [a for a in entry["accounts"] if a["stored"]]
        parts = []
        if entry["usernames"]:
            parts.append(", ".join(entry["usernames"]))
        if known:
            parts.append(f"{len(known)} already stored — adding again replaces the key")
        parts.extend(entry["problems"])
        entry["note"] = "; ".join(parts) or "nothing usable in it"
    # The inbox is inside the repository, so its ignore rule is what keeps a
    # dropped token out of a commit. Say so loudly rather than assume it holds.
    exposed = INBOX_DIR.is_dir() and not is_ignored(INBOX_DIR / "kaggle.json")
    warning = (f"{display_path(INBOX_DIR)} is not ignored by git — restore its .gitignore "
               "before dropping a token there") if exposed else None

    if args.json:
        print(json.dumps({"candidates": found, "inboxWarning": warning}, indent=2))
        return 0
    if warning:
        print(f"warning: {warning}", file=sys.stderr)
    if not found:
        print(f"Nothing found. Drop a kaggle.json, or a .txt with one "
              f"`username key` per line, into {display_path(INBOX_DIR)}/ and run this again.")
        return 0
    width = max(len(e["display"]) for e in found)
    print(f"{len(found)} candidate credential file(s):")
    for entry in found:
        print(f"  {entry['display']:<{width}}  {entry['note']}")
    return 0


def report_source_files(tally: dict) -> None:
    """Consume the inbox files that gave up everything they held; report the rest.

    The inbox is a folder for handing credentials over, so a file with nothing
    left to give has no reason to stay: the same token in two plaintext places
    is exposure with nothing bought.

    Only when **every** credential in it was stored. Deleting a list because
    four of its five rows worked would take the fifth — the one that still needs
    a retry — with it.

    Only the inbox, too. A file the user keeps elsewhere is theirs: say it still
    holds tokens and leave the deleting to them.
    """
    for path, (held, stored) in sorted(tally.items()):
        if not stored:
            continue
        if not in_inbox(path):
            print(f"{path} still holds its token(s); delete it once you are done.")
        elif stored < held:
            print(f"Kept {display_path(path)}: {held - stored} of {held} did not go in.")
        else:
            try:
                path.unlink()
                print(f"Consumed {display_path(path)} — the keys are in the store now.")
            except OSError as exc:
                print(f"Could not delete {display_path(path)} ({exc.strerror}); it still holds the token(s).")


def inbox_files() -> list[Path]:
    """Whatever the user left in the inbox for this run."""
    return [Path(entry["path"]) for entry in discover_credentials([str(INBOX_DIR)])]


def cmd_validate(args: argparse.Namespace) -> int:
    """Make the store true: re-check what is in it, take in what is new.

    Both halves are the same act. A stored credential is not permanently good —
    tokens get expired and rotated, and an account that quietly stopped working
    fails in the middle of a run rather than here. So validating is something to
    do again, not once at setup, and re-checking the store is the half that has
    to keep happening.

    With no argument it also takes in whatever is sitting in the inbox. That
    folder means "these are for you"; a `kaggle.json` in `~/Downloads` is
    reported by `discover` and taken only when named, because finding a file
    somewhere in a home directory is not the same as being handed it.
    """
    if args.interactive and args.files:
        raise UsageError("--interactive takes no file arguments")
    if getattr(args, "json", False) and not getattr(args, "account", None):
        # Refused before anything is read: `--json` is defined only for the
        # read-only `--account` probe, and a caller that asked for JSON and
        # got the human report (exit 0) would read it as a verdict.
        raise UsageError("JSON_NEEDS_ACCOUNT: --json is only defined with --account "
                         "<username>; run `validate --account <username> --json`, or "
                         "`validate` without --json for the human report")
    if getattr(args, "account", None):
        if args.interactive or args.files:
            raise UsageError("--account re-checks stored accounts only; it takes no file "
                             "arguments and no --interactive")
        return _validate_stored(args.account, as_json=bool(getattr(args, "json", False)))

    store = load_store()
    by_username = {a["username"]: a for a in store["accounts"]}
    checked: list[str] = []
    failures = 0

    # 1. What is already stored. A dead credential is reported, never silently
    #    dropped: removing an account is the user's other option, not a side
    #    effect of asking whether it still works.
    for account in sorted(store["accounts"], key=lambda a: a["username"]):
        try:
            validate(account["username"], account["key"])
            checked.append(f"  {account['username']} — ok")
        except CredentialError as exc:
            failures += 1
            checked.append(f"  {account['username']} — NOT working: {exc}")

    # 2. What is new.
    if args.interactive:
        sources: list[str | None] = [None]
    else:
        sources = list(args.files) or [str(p) for p in inbox_files()]

    added: list[str] = []
    tally: dict[Path, list[int]] = {}
    for raw in sources:
        if raw is None:
            username, key = read_credential_interactively()
            credentials = [{"label": "typed", "username": username, "key": key, "problem": None}]
        else:
            try:
                credentials = read_credentials(raw)
            except CredentialError as exc:
                failures += 1
                added.append(f"  {display_path(Path(raw))} — {exc}")
                continue
            tally[Path(raw)] = [len(credentials), 0]

        for credential in credentials:
            where = (f"{display_path(Path(raw))}, {credential['label']}" if raw
                     else "the credential you typed")
            try:
                if credential["problem"]:
                    raise CredentialError(credential["problem"])
                username, key = credential["username"], credential["key"]
                if not USERNAME_PATTERN.match(username):
                    raise CredentialError(f"{username!r} is not a usable Kaggle username")
                validate(username, key)
            except CredentialError as exc:
                failures += 1
                added.append(f"  {where} — rejected: {exc}")
                continue
            existing = by_username.get(username)
            if existing is not None:
                # Say "replaced" only when something actually changed. A list
                # left in the inbox is re-read every run, so the common case is
                # the same key arriving again, and calling that a rotation reads
                # as a token having changed when none did.
                same = existing["key"] == key
                existing["key"] = key
                added.append(f"  {username} — {'already stored' if same else 'key replaced'}")
            else:
                entry = {"username": username, "key": key}
                store["accounts"].append(entry)
                by_username[username] = entry
                added.append(f"  {username} — stored")
            if raw is not None:
                tally[Path(raw)][1] += 1

    if checked:
        print(f"Checked {len(checked)} stored account(s):")
        print("\n".join(checked))
    if added:
        print(f"From what you left to validate:")
        print("\n".join(added))
    save_store(store)
    report_source_files(tally)
    if not checked and not added:
        print(f"Nothing to validate. Drop a kaggle.json, or a .txt with one "
              f"`username key` per line, into {INBOX_NAME}/ and run this again.")
    return 1 if failures else 0


def _validate_stored(usernames: list[str], *, as_json: bool) -> int:
    """Re-check only the named stored accounts: the read-only probe a
    pre-launch check runs. Takes in nothing from the inbox and writes
    nothing, so it needs none of `validate`'s consent; it prints a verdict
    per account and never a key."""
    by_username = {a["username"]: a for a in load_store()["accounts"]}
    rows = []
    for username in usernames:
        account = by_username.get(username)
        if account is None:
            rows.append({"username": username, "ok": False,
                         "detail": "not stored; take its credential in with validate"})
            continue
        try:
            validate(account["username"], account["key"])
            rows.append({"username": username, "ok": True, "detail": "ok"})
        except CredentialError as exc:
            rows.append({"username": username, "ok": False, "detail": str(exc)})
    if as_json:
        print(json.dumps({"accounts": rows}, indent=2))
    else:
        for row in rows:
            print(f"  {row['username']} — {'ok' if row['ok'] else 'NOT working: ' + row['detail']}")
    return 0 if all(row["ok"] for row in rows) else 1


def cmd_materialize(args: argparse.Namespace) -> int:
    """Write one worker's live credential to a plain-text token file, atomically.

    The one command in this file that ever lets a stored credential leave
    this process — and even here, only as a FILE, handed to a destination
    that has already proven it is safe to hold one. Everything this prints
    is a destination, never a value: a caller learns WHERE a credential
    landed, not what it says.

    The file holds nothing but the token itself — no `username` field, no
    JSON wrapper. Kaggle's own client reads `KAGGLE_API_TOKEN` as a path,
    treats whatever text is at that path (stripped) as the token, and
    authenticates it through its modern token path. The legacy `kaggle.json`
    container (`{"username": ..., "key": ...}`) routes an access token
    through a Basic-auth path a bearer token was never meant for, and Kaggle
    answers that with 401 regardless of how valid the token is — so this
    command emits the shape Kaggle's client actually expects for the token
    format this store holds.

    Non-interactive by construction: there is no prompt, no confirmation,
    no branch that ever asks a human anything. The "one interactive
    question" doctrine that shapes `validate --interactive` governs the
    human consent surface this file opens, not the total count of commands
    it exposes — `list` and `discover` already answer without asking, and
    this is a third.

    Reuses `save_store()`'s own atomic shape exactly, because a half-written
    token file would be exactly the failure that shape already prevents
    for the store itself: `mkstemp` inside the destination, `os.fchmod` to
    owner-only BEFORE any byte is written, then `os.replace` — so a reader
    either finds the previous file or the new one, never a partial one.
    """
    store = load_store()
    account = next(
        (a for a in store["accounts"] if a["username"] == args.worker), None
    )
    if account is None:
        raise UsageError(f"no such account: {args.worker}")

    token_path = (
        Path(args.into).expanduser().resolve() / TOKEN_FILENAME
        if args.into
        else worker_token_path(args.worker)
    )
    dest_dir = token_path.parent
    # The same precondition the store itself enforces before it ever writes
    # a token to disk, checked again here because THIS destination has
    # never been proven safe before — a caller passing `--into` names a
    # path this file has no reason to trust just because the store's own
    # ignore rule holds. Checked BEFORE the directory is created: a refusal
    # must leave nothing behind, not even an empty scaffold directory —
    # `git check-ignore` matches a pattern against a path regardless of
    # whether anything exists there yet, so this ordering costs the
    # default (store-relative) destination nothing.
    assert_ignored(token_path)
    dest_dir.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(dir=str(dest_dir), prefix=".kaggle-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(account["key"])
            fh.write("\n")
        os.replace(tmp, token_path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise StoreError(f"{token_path} could not be written: {exc.strerror}")
    dest_dir.chmod(0o700)

    if args.json:
        print(json.dumps({"worker": args.worker, "tokenPath": str(token_path)}))
    else:
        print(str(token_path))
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    """Delete accounts from the store, and with them whatever `materialize`
    already wrote to disk for those accounts.

    Deleting the store entry alone used to leave a live credential at
    `store/workers/<username>/token` — the exact path the consuming skill
    is pointed at — so an account this file said it no longer held stayed
    usable by anything that had already been handed that path. The token
    file goes first, before the store is saved: a failure there must leave
    the store describing what is actually on disk, and a store already
    saved cannot be un-saved.
    """
    store = load_store()
    present = {a["username"] for a in store["accounts"]}
    unknown = [username for username in args.usernames if username not in present]
    if unknown:
        # Refuse the whole batch: a typo that silently removes only the names it
        # happened to match is a worse outcome than removing nothing.
        raise UsageError(f"no such account: {', '.join(unknown)}")

    targets = set(args.usernames)
    materialized = []
    for username in sorted(targets):
        token_path = worker_token_path(username)
        try:
            token_path.unlink()
        except FileNotFoundError:
            continue  # nothing was ever materialized for this one
        except OSError as exc:
            raise StoreError(
                f"{token_path} could not be deleted: {exc.strerror}; nothing "
                "was removed from the store"
            )
        materialized.append(username)
        try:
            token_path.parent.rmdir()
        except OSError:
            # Something else lives in that worker's directory. Leaving it
            # is correct; the credential itself is already gone.
            pass

    store["accounts"] = [a for a in store["accounts"] if a["username"] not in targets]
    save_store(store)
    print(f"Removed {len(targets)}: {', '.join(sorted(targets))}")
    if materialized:
        # A destination, never a value — the same rule `materialize` prints by.
        print(
            f"Deleted the credential file previously materialized for: "
            f"{', '.join(materialized)}"
        )
    return 0


#: WHY THIS SKILL WAS INVOKED, AND WHERE IT HAS TO ARRIVE.
#:
#: Declared, invariant, and independent of what the store holds. `list` answers
#: *which accounts are there*; this answers *what is this for*, which a listing
#: never implies -- an account is in the store because somebody put it there,
#: not because it works.
#:
#: **Arrival is every account carrying a CURRENT verdict, not a command that
#: ran.** That is the whole of it: a stored credential is a claim, and the only
#: thing that settles it is the service. And a verdict decays -- tokens are
#: rotated and expired -- so "it authenticated once" is not the arrival either.
#: A session that runs `validate`, sees a failure reported, and stops has not
#: arrived: a dead credential is reported and never removed here, deliberately,
#: because removing it is the user's other option and not a side effect of
#: asking whether it still works.
OBJECTIVE_FLOW = {
    "purpose": (
        "have every credential this project holds proven against the service "
        "that decides -- not stored, not once-working, currently proven"),
    "stages": [
        {"stage": "taken-in",
         "establishes": "what the user handed over is in the store, one row at "
                        "a time, so a bad row never costs the rows around it",
         "behindWhen": "the inbox gave up everything it held and was consumed, "
                       "or kept because rows are still in it"},
        {"stage": "proven",
         "establishes": "each stored account was asked of the service, under "
                        "whichever of the two token schemes it actually uses",
         "behindWhen": "every account carries a verdict from this run"},
        {"stage": "decided",
         "establishes": "what happens to the ones that stopped working, which "
                        "is the user's call and never a side effect of asking",
         "behindWhen": "this is the arrival; it is behind nobody"},
    ],
    "arrival": (
        "every account carrying a current verdict, and the failures answered "
        "for rather than merely reported"),
    "humanStops": [
        "consenting to validate at all, because it writes: it stores "
        "credentials and consumes the inbox",
        "deciding what happens to an account that stopped working",
    ],
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the Kaggle credentials this project uses.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="show stored accounts (never their keys)")
    p_list.add_argument("--json", action="store_true", help="machine-readable output")
    p_list.set_defaults(func=cmd_list)

    p_discover = sub.add_parser("discover", help="find kaggle.json files to offer as choices")
    p_discover.add_argument("--json", action="store_true", help="machine-readable output")
    p_discover.set_defaults(func=cmd_discover)

    p_validate = sub.add_parser(
        "validate",
        help="re-check every stored account and take in whatever is in the inbox")
    p_validate.add_argument("files", nargs="*", metavar="file",
                            help="check these instead of the inbox")
    p_validate.add_argument(
        "--interactive", action="store_true",
        help="type one credential into a hidden terminal prompt instead of passing a file; "
             "run this yourself in your own shell",
    )
    p_validate.add_argument(
        "--account", action="append", default=None, metavar="username",
        help="repeatable: re-check only this stored account; takes in nothing and writes "
             "nothing (the read-only probe remote-execution's preflight runs)",
    )
    p_validate.add_argument("--json", action="store_true",
                            help="machine-readable verdicts; only with --account "
                                 "(refused JSON_NEEDS_ACCOUNT otherwise)")
    p_validate.set_defaults(func=cmd_validate)

    p_remove = sub.add_parser("remove", help="delete stored accounts by username")
    p_remove.add_argument("usernames", nargs="+", metavar="username")
    p_remove.set_defaults(func=cmd_remove)

    p_materialize = sub.add_parser(
        "materialize",
        help="write one worker's credential to a config directory, non-interactively")
    p_materialize.add_argument("--worker", required=True, metavar="username")
    p_materialize.add_argument(
        "--into", metavar="dir",
        help="override the default store/workers/<worker>/ destination")
    p_materialize.add_argument(
        "--json", action="store_true",
        help="machine-readable output — a destination, never the credential itself")
    p_materialize.set_defaults(func=cmd_materialize)

    args = parser.parse_args()
    try:
        return args.func(args)
    except (UsageError, StoreError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        # The north, on the one path a refusal reaches a reader.
        print(json.dumps({"objective": OBJECTIVE_FLOW}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
