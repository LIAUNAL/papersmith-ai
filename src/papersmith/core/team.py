"""``smith team list|add|remove`` — the workspace's team registry.

Several remote accounts per service are allowed only under a TEAM model: one
account per person per service, each owned and operated by a distinct team
member. ``.papersmith/team.json`` records who those people are and which
account each one holds; it never holds a secret (Kaggle credentials stay in
the ``kaggle-accounts`` store, Colab's in each owner's CLI state directory),
but it names people, so ``add`` keeps it git-ignored.

Schema 1::

    {"schema": 1, "members": [{"owner": "<slug>", "displayName": "<text>",
      "attestedAt": "YYYY-MM-DD", "attestation": ATTESTATION,
      "accounts": {"kaggle": {"username": "<kaggle username>"},
                   "colab": {"tier": "free|pro|payg|enterprise",
                             "configDir": "<absolute path>"}}}]}

An owner appears once; the same Kaggle username or Colab ``configDir`` may not
appear under two owners. Parallelism counts distinct owners, never accounts
(``skills/remote-parallelism``), and a Colab account on the ``free`` tier is
never a worker of a split campaign.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..errors import UserError

TEAM_FILE = ".papersmith/team.json"
SCHEMA = 1
ATTESTATION = "owns and operates exactly one account per service listed here"
OWNER_PATTERN = re.compile(r"^[a-z0-9-]{1,40}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
COLAB_TIERS = ("free", "pro", "payg", "enterprise")
#: Tiers whose compute may run a campaign split across owners. The Colab FAQ
#: disallows "running distributed computing workers" on free runtimes without
#: compute units (https://research.google.com/colaboratory/faq.html).
PAID_COLAB_TIERS = ("pro", "payg", "enterprise")
#: Where the ``kaggle-accounts`` skill lives in a workspace; its own ``list
#: --json`` verb is the only way papersmith learns the stored usernames, so the
#: credential store itself is never opened here.
KAGGLE_ACCOUNTS_CLI = "skills/kaggle-accounts/scripts/accounts_cli.py"
KAGGLE_LIST_TIMEOUT_SECONDS = 20


def workspace_root(raw: str | None) -> Path:
    root = Path(raw).expanduser().resolve() if raw else Path.cwd().resolve()
    if not (root / ".papersmith").is_dir():
        raise UserError(f"{root} is not a papersmith workspace (no .papersmith/); "
                        "run `smith init` first or pass --workspace")
    return root


def registry_path(root: Path) -> Path:
    return root / TEAM_FILE


def colab_config_dir(owner: str) -> Path:
    """The owner's Colab CLI state directory, outside every workspace."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base).expanduser() / "papersmith" / "colab" / owner


def load(root: Path) -> dict[str, Any]:
    path = registry_path(root)
    if not path.exists():
        return {"schema": SCHEMA, "members": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise UserError(f"{TEAM_FILE} is not valid JSON ({exc}); fix or remove it by hand")
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("members"), list):
        raise UserError(f"{TEAM_FILE} is not a schema {SCHEMA} team registry; fix or remove it by hand")
    return data


def save(root: Path, data: dict[str, Any]) -> Path:
    path = registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def ensure_ignored(root: Path) -> bool:
    """Append :data:`TEAM_FILE` to the workspace ``.gitignore`` once; return whether it did."""
    path = root / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if TEAM_FILE in (line.strip() for line in text.splitlines()):
        return False
    prefix = "" if not text or text.endswith("\n") else "\n"
    path.write_text(f"{text}{prefix}# team registry: names people, holds no secret\n{TEAM_FILE}\n",
                    encoding="utf-8")
    return True


def members(root: Path) -> list[dict[str, Any]]:
    return [m for m in load(root)["members"] if isinstance(m, dict)]


def find(root: Path, owner: str) -> dict[str, Any]:
    for member in members(root):
        if member.get("owner") == owner:
            return member
    raise UserError(f"no team member with owner {owner!r}; see `smith team list`")


def _accounts(member: dict[str, Any]) -> dict[str, Any]:
    accounts = member.get("accounts")
    return accounts if isinstance(accounts, dict) else {}


def colab_account(member: dict[str, Any]) -> dict[str, Any] | None:
    account = _accounts(member).get("colab")
    return account if isinstance(account, dict) else None


def kaggle_username(member: dict[str, Any]) -> str | None:
    account = _accounts(member).get("kaggle")
    name = account.get("username") if isinstance(account, dict) else None
    return name if isinstance(name, str) and name else None


def split_eligible(tier: str | None) -> bool:
    return tier in PAID_COLAB_TIERS


def _make_private_dir(path: Path) -> None:
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise UserError(f"{parent} is a symlink; refusing to create the Colab state directory through it")
        if parent == Path(parent.anchor):
            break
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        os.chmod(path, 0o700)


def add_member(root: Path, *, owner: str, name: str, kaggle: str | None = None,
               colab: bool = False, tier: str | None = None, attest: bool = False,
               email: str | None = None, today: str | None = None) -> dict[str, Any]:
    if not attest:
        raise UserError("pass --attest to confirm this person owns and operates exactly one "
                        "account per service listed here (one account per person per service)")
    if not OWNER_PATTERN.match(owner or ""):
        raise UserError(f"--owner {owner!r} must be 1-40 characters of a-z, 0-9 and '-'")
    if not name or not name.strip():
        raise UserError("--name must not be empty")
    if email is not None:
        email = email.strip()
        if not EMAIL_PATTERN.match(email):
            raise UserError(f"--email {email!r} is not a valid email address")
    if tier is not None and not colab:
        raise UserError("--colab-tier needs --colab")
    if colab and tier is None:
        raise UserError("--colab needs --colab-tier free|pro|payg|enterprise")
    if tier is not None and tier not in COLAB_TIERS:
        raise UserError(f"--colab-tier must be one of {', '.join(COLAB_TIERS)}")
    kaggle = kaggle.strip() if kaggle else None
    if not kaggle and not colab:
        raise UserError("list at least one account: --kaggle-username and/or --colab")
    data = load(root)
    existing = [m for m in data["members"] if isinstance(m, dict)]
    config_dir = colab_config_dir(owner) if colab else None
    for member in existing:
        if member.get("owner") == owner:
            raise UserError(f"owner {owner!r} is already in the team; remove it first to change it")
        other = kaggle_username(member)
        if kaggle and other and other.lower() == kaggle.lower():
            raise UserError(f"Kaggle username {kaggle!r} already belongs to owner {member.get('owner')!r}: "
                            "one account per person per service")
        account = colab_account(member)
        if config_dir is not None and account and account.get("configDir") and \
                os.path.realpath(account["configDir"]) == os.path.realpath(config_dir):
            raise UserError(f"Colab configDir {config_dir} already belongs to owner "
                            f"{member.get('owner')!r}: one account per person per service")
        if email:
            other_email = member.get("email")
            if other_email and other_email.strip().lower() == email.strip().lower():
                if kaggle and other:
                    raise UserError(f"email {email!r} already belongs to owner {member.get('owner')!r} for Kaggle: "
                                    "each account for the same service must be associated with a distinct email address")
                if colab and account:
                    raise UserError(f"email {email!r} already belongs to owner {member.get('owner')!r} for Colab: "
                                    "each account for the same service must be associated with a distinct email address")
    accounts: dict[str, Any] = {}
    if kaggle:
        accounts["kaggle"] = {"username": kaggle}
    if config_dir is not None:
        _make_private_dir(config_dir)
        accounts["colab"] = {"tier": tier, "configDir": str(config_dir)}
    member = {"owner": owner, "displayName": name.strip(),
              "attestedAt": today or datetime.date.today().isoformat(),
              "attestation": ATTESTATION, "accounts": accounts}
    if email:
        member["email"] = email
    data["members"] = [*existing, member]
    ensure_ignored(root)
    save(root, data)
    return member


def remove_member(root: Path, owner: str) -> dict[str, Any]:
    data = load(root)
    kept = [m for m in data["members"] if not (isinstance(m, dict) and m.get("owner") == owner)]
    if len(kept) == len(data["members"]):
        raise UserError(f"no team member with owner {owner!r}; see `smith team list`")
    removed = next(m for m in data["members"] if isinstance(m, dict) and m.get("owner") == owner)
    data["members"] = kept
    save(root, data)
    return removed


def stored_kaggle_usernames(root: Path) -> list[str]:
    """Usernames the ``kaggle-accounts`` store holds, from that skill's own ``list --json``.

    Never opens the store: the skill prints usernames and never keys. An absent
    skill or a failing run yields an empty list.
    """
    script = root / KAGGLE_ACCOUNTS_CLI
    if not script.is_file():
        return []
    try:
        completed = subprocess.run([sys.executable, str(script), "list", "--json"], cwd=root,
                                   capture_output=True, text=True, timeout=KAGGLE_LIST_TIMEOUT_SECONDS)
        payload = json.loads(completed.stdout) if completed.returncode == 0 else {}
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    accounts = payload.get("accounts") if isinstance(payload, dict) else None
    if not isinstance(accounts, list):
        return []
    return sorted({a["username"] for a in accounts
                   if isinstance(a, dict) and isinstance(a.get("username"), str) and a["username"]})


def _public(member: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {"owner": member.get("owner"), "displayName": member.get("displayName"),
                           "attestedAt": member.get("attestedAt"), "accounts": {}}
    if member.get("email"):
        row["email"] = member["email"]
    if kaggle_username(member):
        row["accounts"]["kaggle"] = {"username": kaggle_username(member)}
    account = colab_account(member)
    if account:
        row["accounts"]["colab"] = {"tier": account.get("tier"), "configDir": account.get("configDir"),
                                    "splitCampaignEligible": split_eligible(account.get("tier"))}
    return row


# --- CLI --------------------------------------------------------------------


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "team", help="the team registry: remote accounts associated with distinct emails")
    commands = parser.add_subparsers(dest="team_command", required=True)
    listing = commands.add_parser("list", help="list team members and their accounts (never a secret)")
    listing.add_argument("--json", action="store_true", help="machine-readable output")
    listing.add_argument("--workspace", default=None, help="workspace root (default: current directory)")
    listing.set_defaults(handler=run_list)
    add = commands.add_parser("add", help="add one account owner associated with a distinct email")
    add.add_argument("--owner", required=True, help="slug, 1-40 characters of a-z, 0-9 and '-'")
    add.add_argument("--name", required=True, help="the person's display name")
    add.add_argument("--email", default=None, help="distinct email address for this account")
    add.add_argument("--kaggle-username", default=None, help="this owner's Kaggle username")
    add.add_argument("--colab", action="store_true", help="register a Colab account")
    add.add_argument("--colab-tier", choices=COLAB_TIERS, default=None,
                     help="the Colab account's compute tier; free never joins a split campaign")
    add.add_argument("--attest", action="store_true",
                     help="confirm the account is associated with a distinct email and operated validly")
    add.add_argument("--workspace", default=None, help="workspace root (default: current directory)")
    add.set_defaults(handler=run_add)
    remove = commands.add_parser("remove", help="remove one person (never deletes credential files)")
    remove.add_argument("--owner", required=True)
    remove.add_argument("--workspace", default=None, help="workspace root (default: current directory)")
    remove.set_defaults(handler=run_remove)


def run_list(args) -> int:
    root = workspace_root(args.workspace)
    rows = [_public(m) for m in members(root)]
    claimed = {(kaggle_username(m) or "").lower() for m in members(root)}
    unmapped = [name for name in stored_kaggle_usernames(root) if name.lower() not in claimed]
    if args.json:
        print(json.dumps({"members": rows, "unmappedKaggleUsernames": unmapped}, indent=2,
                         ensure_ascii=False))
        return 0
    if not rows:
        print(f"No team members in {TEAM_FILE}; add one with `smith team add --owner <slug> "
              "--name \"<display>\" [--email E] [--kaggle-username U] [--colab --colab-tier T] --attest`.")
    else:
        print(f"{len(rows)} team member(s), accounts associated with distinct emails:")
        for row in rows:
            parts = []
            if "kaggle" in row["accounts"]:
                parts.append(f"kaggle {row['accounts']['kaggle']['username']}")
            if "colab" in row["accounts"]:
                colab = row["accounts"]["colab"]
                parts.append(f"colab tier {colab['tier']}"
                             + ("" if colab["splitCampaignEligible"] else " (interactive only, no split campaigns)"))
            email_part = f" <{row['email']}>" if row.get("email") else ""
            print(f"  {row['owner']} — {row['displayName']}{email_part} (attested {row['attestedAt']}): "
                  + "; ".join(parts))
    for name in unmapped:
        print(f"warning: Kaggle account {name} is in the kaggle-accounts store but no owner claims it; "
              "map it with `smith team add --kaggle-username` or remove it from the store")
    return 0


def run_add(args) -> int:
    root = workspace_root(args.workspace)
    # Existence only: nothing inside the state directory is listed or read.
    reused = bool(args.colab) and colab_config_dir(args.owner).exists()
    member = add_member(root, owner=args.owner, name=args.name, kaggle=args.kaggle_username,
                        colab=args.colab, tier=args.colab_tier, email=getattr(args, "email", None),
                        attest=args.attest)
    email_note = f" <{member['email']}>" if member.get("email") else ""
    print(f"added: {member['owner']} — {member['displayName']}{email_note} ({TEAM_FILE}, git-ignored)")
    account = colab_account(member)
    if account:
        print(f"Colab state directory: {account['configDir']} (0700)")
        if reused:
            print(f"warning: {account['configDir']} already existed, so it may still hold the "
                  "Colab sign-in of whoever used this owner slug before; if this is a different "
                  "person, delete that directory and run `smith colab login` again")
        print(f"next: smith colab login --owner {member['owner']}")
        if not split_eligible(account["tier"]):
            print("note: a free Colab account runs interactive and proof-of-concept work in one "
                  "session; it is never a worker of a split campaign")
    if kaggle_username(member):
        print("Kaggle: validate the credential with the kaggle-accounts skill (`/kaggle-accounts`).")
    return 0


def run_remove(args) -> int:
    root = workspace_root(args.workspace)
    member = remove_member(root, args.owner)
    print(f"removed: {member.get('owner')} from {TEAM_FILE}; no credential file was deleted")
    account = colab_account(member)
    if account and account.get("configDir"):
        print(f"to delete the Colab sign-in too, remove its state directory: {account['configDir']}")
    name = kaggle_username(member)
    if name:
        print(f"to delete the Kaggle credential too: `python3 {KAGGLE_ACCOUNTS_CLI} remove {name}` "
              "(the kaggle-accounts skill)")
    return 0
