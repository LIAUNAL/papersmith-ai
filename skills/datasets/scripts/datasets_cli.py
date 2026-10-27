#!/usr/bin/env python3
"""The `datasets` front door: toy sets, discovery, the license gate, quality
checks, the one official preparation, and private publishing on consent.

Stdlib only. Workspace state lives in ``datasets/`` at the workspace root:
``datasets/registry.json`` plus one folder per dataset. The network is touched
only by ``search`` (through the injectable HTTP layer of ``hosts``) and by
``publish`` (through the injectable runner that invokes the publishing host's
official client). No verb reads, stores or prints a credential.

Every refusal is one JSON object on stderr -- ``{"error", "message",
"objective"}`` -- and exit status 2; success is one JSON object on stdout.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hosts  # noqa: E402  (sibling package, resolved from this file's folder)
import capacity_toy  # noqa: E402  (sibling module, same folder)

OBJECTIVE_FLOW = {
    "purpose": (
        "give the proof of concept and the full experiments data they can both "
        "stand on: a seeded toy set always, and a sourced set whose license, "
        "quality and preparation are recorded rather than assumed"),
    "stages": [
        {"stage": "toy",
         "establishes": "a seeded synthetic set exists, so the proof of concept never waits on real data",
         "behindWhen": "the registry holds no entry with role toy"},
        {"stage": "sourced",
         "establishes": "candidate real datasets were searched for and every hit is on disk with its URL and date",
         "behindWhen": "no datasets/search-*.json file exists and no full entry names a source URL"},
        {"stage": "licensed",
         "establishes": "the source license was read and mapped to a decision before any data moves",
         "behindWhen": "the full entry has no license decision, or it is refused without an override"},
        {"stage": "checked",
         "establishes": "the data's shape, gaps, balance and subject structure are measured in qc.json",
         "behindWhen": "the entry's qc is missing or its status is fail"},
        {"stage": "prepared",
         "establishes": "one versioned subject-wise split both experiment stages read, tied to the source sha256",
         "behindWhen": "the entry has no PREPARATION.md and splits.json"},
        {"stage": "published",
         "establishes": "the prepared set sits on the remote dataset host, private unless made public on consent",
         "behindWhen": "the entry records no remote ref"},
    ],
    "arrival": (
        "a toy set and a licensed, checked, prepared dataset that the proof of "
        "concept and the full experiments both read, published privately only "
        "on the operator's consent"),
    "humanStops": [
        "overriding a refused source license (--override with a reason)",
        "consenting to upload one named dataset (--consent <slug>)",
        "consenting separately to make it public (--public --consent-public <slug>)",
    ],
}

VERBS = ("synth", "search", "license", "qc", "prepare", "publish", "status")

ERROR_CODES = (
    "bad-slug", "slug-exists", "member-exists", "unknown-slug", "file-missing", "file-outside-workspace",
    "bad-column", "bad-folds", "too-few-groups", "identical-repetitions", "unknown-host", "license-not-allowed",
    "bad-owner", "bad-metadata", "public-consent-missing", "public-on-existing",
    "no-publisher", "host-cli-missing", "host-cli-failed", "bad-argument",
)

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,48}[a-z0-9])?$")
OWNER_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MISSING = {"", "na", "nan", "null", "none"}
GOOGLE_DATASET_SEARCH = "https://datasetsearch.research.google.com/search?query="


class Refusal(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def today() -> str:
    return datetime.date.today().isoformat()


# ------------------------------------------------------------------ registry
def datasets_dir(root: Path) -> Path:
    return root / "datasets"


def load_registry(root: Path) -> list[dict]:
    path = datasets_dir(root) / "registry.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def save_registry(root: Path, registry: list[dict]) -> None:
    folder = datasets_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    registry = sorted(registry, key=lambda item: item["slug"])
    handle, temp = tempfile.mkstemp(dir=folder, prefix=".registry-", suffix=".json")
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        json.dump(registry, stream, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(temp, folder / "registry.json")


def new_entry(slug: str, role: str, title: str) -> dict:
    return {"slug": slug, "role": role, "title": title,
            "source": {"kind": "", "url": "", "retrieved": ""},
            "license": {"source_name": "", "decision": "", "host_license": ""},
            "files": [], "qc": None, "preparation": None, "remote": None}


def check_slug(slug: str) -> str:
    if not SLUG_RE.match(slug or ""):
        raise Refusal("bad-slug", f"{slug!r}: lowercase letters, digits and hyphens, 1-50 characters")
    return slug


def find(registry: list[dict], slug: str) -> dict:
    check_slug(slug)
    for entry in registry:
        if entry["slug"] == slug:
            return entry
    raise Refusal("unknown-slug", f"{slug} is not in datasets/registry.json; run synth or license first")


def workspace_file(root: Path, name: str) -> tuple[Path, str]:
    path = Path(name)
    path = (path if path.is_absolute() else root / path).resolve()
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        raise Refusal("file-outside-workspace", f"{name} is outside the workspace") from None
    if not path.is_file():
        raise Refusal("file-missing", f"{rel} does not exist")
    return path, rel


def upload_source(root: Path, path: Path) -> Path:
    """A file publish may copy: a regular file inside the workspace reached
    through no symlink at all, so a registry entry or a planted link can never
    smuggle a credential or an outside file into the upload folder."""
    absolute = Path(os.path.normpath(path if path.is_absolute() else root / path))
    if absolute.is_symlink() or absolute.resolve() != absolute:
        raise Refusal("file-outside-workspace", f"{path} is a symlink or passes through one; refusing to upload it")
    try:
        absolute.relative_to(root)
    except ValueError:
        raise Refusal("file-outside-workspace", f"{path} is outside the workspace") from None
    if not absolute.is_file():
        raise Refusal("file-missing", f"{absolute.relative_to(root).as_posix()} does not exist")
    return absolute


def read_rows(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------- synth
#: EEG toy profiles. `alpha`: one 10 Hz rhythm whose amplitude depends on the
#: class. `theta-beta`: a Theta (6 Hz) and a Beta (20 Hz) rhythm whose ratio
#: depends on the class -- class 1 carries the elevated Theta/Beta ratio.
EEG_PROFILES = ("alpha", "theta-beta", "capacity")
THETA_HZ, BETA_HZ = 6.0, 20.0


def synth_rows(kind: str, seed: int, n_subjects: int, n_per_subject: int,
               channels: int, length: int, sfreq: float,
               profile: str = "alpha", label_per: str = "trial") -> tuple[list[str], list[list[str]]]:
    rng = random.Random(seed)
    rows: list[list[str]] = []
    if kind == "eeg":
        header = ["subject", "trial", "label"] + [f"ch{c}_t{t}" for c in range(channels) for t in range(length)]
        for subject in range(n_subjects):
            gain = 1.0 + 0.2 * rng.gauss(0.0, 1.0)
            for trial in range(n_per_subject):
                label = subject % 2 if label_per == "subject" else (trial + subject) % 2
                values = []
                for channel in range(channels):
                    scale = abs(gain) * (1.0 + 0.1 * channel)
                    if profile == "theta-beta":
                        theta = (1.0 if label else 0.5) * scale
                        beta = (0.35 if label else 0.7) * scale
                        phase_t = rng.uniform(0.0, 2.0 * math.pi)
                        phase_b = rng.uniform(0.0, 2.0 * math.pi)
                        for t in range(length):
                            signal = (theta * math.sin(2.0 * math.pi * THETA_HZ * t / sfreq + phase_t)
                                      + beta * math.sin(2.0 * math.pi * BETA_HZ * t / sfreq + phase_b))
                            values.append(f"{signal + rng.gauss(0.0, 0.3):.6f}")
                        continue
                    amplitude = (1.0 if label else 0.4) * scale
                    phase = rng.uniform(0.0, 2.0 * math.pi)
                    for t in range(length):
                        signal = amplitude * math.sin(2.0 * math.pi * 10.0 * t / sfreq + phase)
                        values.append(f"{signal + rng.gauss(0.0, 0.3):.6f}")
                rows.append([f"sub{subject:02d}", str(trial), str(label)] + values)
    else:
        header = ["subject", "sample", "label"] + [f"x{j}" for j in range(channels)]
        for subject in range(n_subjects):
            offset = rng.gauss(0.0, 0.3)
            for sample in range(n_per_subject):
                label = subject % 2 if label_per == "subject" else (sample + subject) % 2
                values = [f"{rng.gauss((label - 0.5) * (1 + j % 2), 1.0) + offset:.6f}" for j in range(channels)]
                rows.append([f"sub{subject:02d}", str(sample), str(label)] + values)
    return header, rows


CAPACITY_ONLY = ("rule", "d_prime")


def cmd_synth(args, root: Path, **_inject) -> dict:
    slug = check_slug(args.slug)
    if args.kind == "eeg" and args.profile == "capacity":
        return synth_capacity(args, root, slug)
    for name in CAPACITY_ONLY:
        if getattr(args, name) is not None:
            raise Refusal("bad-argument", f"--{name.replace('_', '-')} is for --profile capacity only")
    defaults = {"n_subjects": 6, "n_per_subject": 20, "channels": 4, "length": 128, "sfreq": 128.0,
                "label_per": "trial"}
    for name, value in defaults.items():
        if getattr(args, name) is None:
            setattr(args, name, value)
    registry = load_registry(root)
    if any(entry["slug"] == slug for entry in registry) and not args.force:
        raise Refusal("slug-exists", f"{slug} is already registered; pass --force to regenerate it")
    for name, value in (("--n-subjects", args.n_subjects), ("--n-per-subject", args.n_per_subject),
                        ("--channels", args.channels), ("--length", args.length)):
        if value < 1:
            raise Refusal("bad-argument", f"{name} must be positive")
    if args.kind == "eeg" and args.profile == "theta-beta" and args.sfreq <= 2 * BETA_HZ:
        raise Refusal("bad-argument", f"--sfreq must exceed {2 * BETA_HZ:g} Hz for the {BETA_HZ:g} Hz Beta rhythm")
    header, rows = synth_rows(args.kind, args.seed, args.n_subjects, args.n_per_subject,
                              args.channels, args.length, args.sfreq, args.profile, args.label_per)
    folder = datasets_dir(root) / slug
    folder.mkdir(parents=True, exist_ok=True)
    data = folder / f"{slug}.csv"
    with data.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    params = {"kind": args.kind, "seed": args.seed, "n_subjects": args.n_subjects,
              "n_per_subject": args.n_per_subject, "channels": args.channels}
    params["label_per"] = args.label_per
    if args.kind == "eeg":
        params.update({"length": args.length, "sfreq": args.sfreq, "profile": args.profile})
    lines = [f"# Toy dataset `{slug}`", "",
             "Seeded synthetic data for the proof of concept. Same parameters, same bytes.", "",
             "| Parameter | Value |", "|---|---|"]
    lines += [f"| {key} | {value} |" for key, value in params.items()]
    lines += ["", f"- File: `{slug}.csv` ({len(rows)} rows, {len(header)} columns)",
              f"- sha256: `{sha256(data)}`",
              ("- Labels: one class per subject, balanced across subjects (subject-level protocols)."
               if args.label_per == "subject" else "- Labels: two balanced classes, alternating per subject."),
              ("- Signal: a 10 Hz sinusoid per channel whose band power depends on the class "
               "(amplitude 1.0 vs 0.4, times a per-subject gain), plus Gaussian noise (sd 0.3)."
               if args.kind == "eeg" else
               "- Features: Gaussian, class-dependent mean, plus a per-subject offset."),
              "", f"Regenerate: `python3 skills/datasets/scripts/datasets_cli.py synth --slug {slug} "
              + " ".join(f"--{k.replace('_', '-')} {v}" for k, v in params.items()) + " --force`", ""]
    (folder / "TOY.md").write_text("\n".join(lines), encoding="utf-8")
    registry = [entry for entry in registry if entry["slug"] != slug]
    entry = new_entry(slug, "toy", f"Toy {args.kind} set ({slug})")
    entry["source"] = {"kind": "synthetic", "url": "", "retrieved": today()}
    entry["license"] = {"source_name": "generated by this workspace", "decision": "allowed",
                        "host_license": "CC0-1.0", "reason": "synthetic data owes nobody a license"}
    entry["files"] = [data.relative_to(root).as_posix()]
    registry.append(entry)
    save_registry(root, registry)
    return {"slug": slug, "file": entry["files"][0], "rows": len(rows), "columns": len(header),
            "parameters": params}


def synth_capacity(args, root: Path, slug: str) -> dict:
    """One replicate of the capacity profile: `<rule>[-d<d'>]-s<seed>.npy` plus its JSON sidecar."""
    if args.rule is None:
        raise Refusal("bad-argument", f"--profile capacity needs --rule ({', '.join(capacity_toy.RULES)})")
    if args.rule == "monotone" and (args.d_prime is None or not args.d_prime > 0):
        raise Refusal("bad-argument", "--rule monotone needs a positive --d-prime")
    if args.rule != "monotone" and args.d_prime is not None:
        raise Refusal("bad-argument", f"--d-prime grades the monotone rule only, not {args.rule}")
    if args.n_subjects is not None:
        raise Refusal("bad-argument", "--profile capacity takes --n-train, --n-val and --n-test, not --n-subjects")
    if args.channels not in (None, len(capacity_toy.CHANNELS)):
        raise Refusal("bad-argument", f"--profile capacity uses the {len(capacity_toy.CHANNELS)}-channel montage")
    if args.label_per not in (None, "subject"):
        raise Refusal("bad-argument", "--profile capacity gives every subject one class")
    sfreq = 128.0 if args.sfreq is None else args.sfreq
    if sfreq <= 2 * capacity_toy.BANDS["beta"][1]:
        raise Refusal("bad-argument", f"--sfreq must exceed {2 * capacity_toy.BANDS['beta'][1]:g} Hz for the Beta band")
    length = 256 if args.length is None else args.length
    n_per = 12 if args.n_per_subject is None else args.n_per_subject
    sizes = {"train": args.n_train, "validation": args.n_val, "test": args.n_test}
    for name, value in (("--length", length), ("--n-per-subject", n_per)):
        if value < 1:
            raise Refusal("bad-argument", f"{name} must be positive")
    for name, value in sizes.items():
        if value < 0 or value % 2:
            raise Refusal("bad-argument", f"the {name} group needs an even, non-negative number of subjects "
                                          "so both classes are balanced")
    if not sizes["train"]:
        raise Refusal("bad-argument", "--n-train must be positive")
    d_prime = args.d_prime if args.rule == "monotone" else 0.0
    folder = datasets_dir(root) / slug
    stem = capacity_toy.member_name(args.rule, d_prime, args.seed)
    if (folder / f"{stem}.npy").exists() and not args.force:
        raise Refusal("member-exists", f"{slug}/{stem}.npy exists; pass --force to regenerate it")
    meta = capacity_toy.write_member(folder, args.rule, d_prime, args.seed, sizes, n_per, length, sfreq)
    registry = load_registry(root)
    entry = next((e for e in registry if e["slug"] == slug), None)
    if entry is None:
        entry = new_entry(slug, "toy", f"Capacity toy EEG family ({slug})")
        entry["source"] = {"kind": "synthetic", "url": "", "retrieved": today()}
        entry["license"] = {"source_name": "generated by this workspace", "decision": "allowed",
                            "host_license": "CC0-1.0", "reason": "synthetic data owes nobody a license"}
        entry["files"] = []
        registry.append(entry)
    rel = (folder / meta["file"]).relative_to(root).as_posix()
    entry["files"] = sorted(set(entry.get("files") or []) | {rel})
    save_registry(root, registry)
    write_capacity_toy_md(folder, slug, entry["files"])
    return {"slug": slug, "file": rel, "sidecar": rel[:-4] + ".json", "shape": meta["shape"],
            "sha256": meta["sha256"], "rule": args.rule, "dPrime": meta["dPrime"], "seed": args.seed,
            "sizes": sizes}


def write_capacity_toy_md(folder: Path, slug: str, files: list[str]) -> None:
    params = capacity_toy.PARAMETERS
    lines = [f"# Toy dataset `{slug}` (capacity profile)", "",
             f"Seeded synthetic EEG, generator `capacity` version {capacity_toy.GENERATOR_VERSION}: every "
             "replicate draws fresh training, validation and test subjects, one class per subject, balanced "
             "within each group. Same rule, d', seed and sizes, same bytes.", "",
             "- Montage: " + ", ".join(capacity_toy.CHANNELS) + "; the class effect acts on the frontal ("
             + ", ".join(capacity_toy.FRONTAL) + ") and central (" + ", ".join(capacity_toy.CENTRAL) + ") channels.",
             "- Signal: narrowband Theta (4-8 Hz), Beta (13-30 Hz) and Alpha (8-12 Hz), each a sum of "
             f"{params['sinusoidsPerBand']} sinusoids at random in-band frequencies, over an AR(1) red-noise "
             f"background (coefficient {params['backgroundAr']}), each channel mixed with its two neighbours, "
             f"and a frontal eye blink in {params['blinkProbability']:.0%} of the epochs.",
             "- Rules: `monotone` draws the subject's log Theta/Beta offset from N(+-d'/2, 1) by class, so the "
             "subject-level Bayes limit is Phi(d'/2); `interaction` draws independent N(0, 1) Theta and Beta "
             "deviations, class 1 when both deviate in the same direction; `frequency-two` draws a Theta "
             "deviation u uniform on [-pi, pi), class 1 where cos(2u) > 0.",
             "- Files: one float32 `.npy` (epochs x channels x samples) per replicate with a `.json` sidecar "
             "(subjects, splits, clean labels, deviations, parameters, sha256). Label noise is applied by the "
             "experiment, never stored here.", "",
             "| Parameter | Value |", "|---|---|"]
    lines += [f"| {key} | {value} |" for key, value in params.items()]
    lines += ["", "## Members", ""] + [f"- `{Path(f).name}`" for f in files]
    lines += ["", "Regenerate one: `python3 skills/datasets/scripts/datasets_cli.py synth --slug " + slug
              + " --kind eeg --profile capacity --rule <rule> [--d-prime <d'>] --seed <k> --n-train 60 "
              "--n-val 10 --n-test 100 --n-per-subject 12 --force`", ""]
    (folder / "TOY.md").write_text("\n".join(lines), encoding="utf-8")


# -------------------------------------------------------------------- search
def cmd_search(args, root: Path, http=None, **_inject) -> dict:
    available = hosts.discover()
    chosen = args.hosts or list(available)
    unknown = [name for name in chosen if name not in available]
    if unknown:
        raise Refusal("unknown-host", f"{unknown} unknown; hosts here: {list(available)}")
    http = http or hosts.urllib_http
    stamp = today()
    report = {"query": args.query, "retrieved": stamp, "hosts": {}, "hits": [], "manual": [
        {"name": "Google Dataset Search", "note": "no public API: open it by hand",
         "url": GOOGLE_DATASET_SEARCH + urllib.parse.quote(args.query)}]}
    for name in chosen:
        try:
            hits = available[name].search(args.query, http, args.limit)
        except Exception as exc:  # noqa: BLE001 -- a host failing is recorded, never fatal
            report["hosts"][name] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300]}
            continue
        report["hosts"][name] = {"status": "ok", "count": len(hits)}
        for hit in hits:
            report["hits"].append({"host": name, "ref": str(hit.get("ref", "")),
                                   "title": str(hit.get("title", "")), "url": str(hit.get("url", "")),
                                   "license": str(hit.get("license") or ""), "retrieved": stamp})
    folder = datasets_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    target, counter = folder / f"search-{stamp}.json", 2
    while target.exists():
        target, counter = folder / f"search-{stamp}-{counter}.json", counter + 1
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return {"file": target.relative_to(root).as_posix(), "hits": len(report["hits"]),
            "hosts": report["hosts"], "manual": report["manual"]}


# ------------------------------------------------------------------- license
def classify_license(text: str) -> tuple[bool, str, str]:
    """``(allowed, host_license, reason)`` for a source license as written."""
    lowered = (text or "").lower()
    tokens = re.findall(r"[a-z0-9]+", lowered)
    words = set(tokens)
    if not lowered.strip() or words <= {"unknown", "unspecified", "none"}:
        return False, "other", "no license stated: unknown terms are refused"
    noncommercial = "nc" in words or "noncommercial" in words or "non commercial" in " ".join(tokens)
    noderivs = "nd" in words or "noderivs" in words or "noderivatives" in words or "no derivatives" in " ".join(tokens)
    credentialed = bool(words & {"credentialed", "credential", "dua", "restricted", "proprietary"}) \
        or "data use agreement" in " ".join(tokens)
    if noncommercial or noderivs or credentialed:
        kinds = [label for flag, label in ((noncommercial, "non-commercial"), (noderivs, "no-derivatives"),
                                            (credentialed, "credentialed or under a data use agreement")) if flag]
        host = "CC-BY-NC-SA-4.0" if noncommercial and "sa" in words and not noderivs else \
            "CC-BY-NC-4.0" if noncommercial and not noderivs else "other"
        return False, host, f"{', '.join(kinds)} terms do not permit redistribution by default"
    joined = " ".join(tokens)
    if "cc0" in words or {"cc", "zero"} <= words or "public domain" in joined or "pddl" in words:
        return True, "CC0-1.0", "public domain dedication"
    if "odbl" in words:
        return True, "ODbL-1.0", "open database license"
    if ("cc" in words or "creative" in words) and ("by" in words or "attribution" in words):
        if "sa" in words or "sharealike" in words or "share alike" in joined:
            return True, "CC-BY-SA-4.0", "attribution share-alike (redistribute under the same terms)"
        return True, "CC-BY-4.0", "attribution (credit the source on the dataset page)"
    if words & {"mit", "apache", "bsd", "isc"}:
        return True, "other", "permissive software license: name it in the dataset description"
    return False, "other", "unrecognized terms: read them and decide with --override"


def cmd_license(args, root: Path, **_inject) -> dict:
    slug = check_slug(args.slug)
    registry = load_registry(root)
    entry = next((item for item in registry if item["slug"] == slug), None)
    if entry is None:
        entry = new_entry(slug, args.role, args.title or slug)
        entry["source"] = {"kind": "external", "url": args.source_url or "", "retrieved": today()}
        registry.append(entry)
    else:
        if args.title:
            entry["title"] = args.title
        if args.source_url:
            entry["source"] = {"kind": "external", "url": args.source_url, "retrieved": today()}
    allowed, host, reason = classify_license(args.source_license)
    decision = "allowed" if allowed else ("overridden" if args.override else "refused")
    record = {"source_name": args.source_license, "decision": decision, "host_license": host,
              "reason": reason, "decided": today()}
    if args.override and not allowed:
        record["override"] = args.override
    entry["license"] = record
    save_registry(root, registry)
    return {"slug": slug, **record}


# ------------------------------------------------------------------------ qc
def _number(value: str) -> float | None:
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def qc_report(header: list[str], rows: list[dict], label: str | None, group: str | None) -> dict:
    reasons_fail, reasons_warn = [], []
    missing = {col: sum(1 for row in rows if (row.get(col) or "").strip().lower() in MISSING) for col in header}
    constant = [col for col in header if len({row.get(col) for row in rows}) <= 1] if rows else []
    seen, duplicates = set(), 0
    for row in rows:
        key = tuple(row.get(col) for col in header)
        duplicates += key in seen
        seen.add(key)
    ranges = {}
    for col in header:
        present = [row.get(col) or "" for row in rows if (row.get(col) or "").strip().lower() not in MISSING]
        numbers = [_number(value) for value in present]
        if present and all(n is not None for n in numbers):
            ranges[col] = {"min": min(numbers), "max": max(numbers)}
    report = {"rows": len(rows), "columns": len(header), "missing": {k: v for k, v in missing.items() if v},
              "constant_columns": constant, "duplicates": duplicates, "ranges": ranges,
              "class_balance": None, "groups": None}
    if not rows:
        reasons_fail.append("no rows")
    if any(missing.values()):
        reasons_warn.append(f"missing values in {sorted(k for k, v in missing.items() if v)}")
    if constant:
        reasons_warn.append(f"constant columns {constant}")
    if duplicates:
        reasons_warn.append(f"{duplicates} duplicate rows")
    if label:
        if label not in header:
            reasons_fail.append(f"label column {label!r} not in the header")
        else:
            balance = Counter(row[label] for row in rows)
            report["class_balance"] = dict(sorted(balance.items()))
            if len(balance) < 2:
                reasons_fail.append("fewer than two classes")
            elif max(balance.values()) > 3 * min(balance.values()):
                reasons_warn.append("class imbalance above 3:1")
    if group:
        if group not in header:
            reasons_fail.append(f"group column {group!r} not in the header")
        else:
            sizes = Counter(row[group] for row in rows)
            single = 0
            if label and label in header:
                classes = {}
                for row in rows:
                    classes.setdefault(row[group], set()).add(row[label])
                single = sum(1 for value in classes.values() if len(value) == 1)
            report["groups"] = {"count": len(sizes), "min_size": min(sizes.values(), default=0),
                                "max_size": max(sizes.values(), default=0), "single_class_groups": single}
            if sizes and single == len(sizes):
                reasons_warn.append("the label is constant within every group: a subject-wise split "
                                    "confounds subject and class")
    report["status"] = "fail" if reasons_fail else ("warn" if reasons_warn else "pass")
    report["reasons"] = reasons_fail + reasons_warn
    return report


def cmd_qc(args, root: Path, **_inject) -> dict:
    registry = load_registry(root)
    entry = find(registry, args.slug)
    path, rel = workspace_file(root, args.file)
    header, rows = read_rows(path)
    report = qc_report(header, rows, args.label, args.group)
    report.update({"file": rel, "sha256": sha256(path), "checked": today(), "domain_checks": []})
    folder = datasets_dir(root) / entry["slug"]
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / "qc.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    entry["qc"] = {"status": report["status"], "report": out.relative_to(root).as_posix()}
    if rel not in entry["files"]:
        entry["files"].append(rel)
    save_registry(root, registry)
    return {"slug": entry["slug"], "status": report["status"], "reasons": report["reasons"],
            "report": entry["qc"]["report"]}


# ------------------------------------------------------------------- prepare
def stratified_group_folds(rows: list[dict], label: str, group: str, folds: int, seed: int,
                           size_ordered: bool = True) -> dict:
    """Greedy stratified group k-fold: a group's rows all land in one fold.

    `size_ordered` places the largest groups first after the seeded shuffle,
    which balances rows best but leaves the seed to break ties between
    equal-sized groups only. Off, the groups are cut into size strata of
    `folds` groups, largest first, and the seed shuffles inside each stratum,
    so every seed gives its own split; `--seeds` uses that for repetitions.
    """
    per_group: dict[str, Counter] = {}
    for row in rows:
        per_group.setdefault(row[group], Counter())[row[label]] += 1
    classes = sorted({row[label] for row in rows})
    totals = Counter(row[label] for row in rows)
    target = {c: totals[c] / folds for c in classes}
    order = sorted(per_group)
    shuffler = random.Random(seed)
    shuffler.shuffle(order)
    order.sort(key=lambda g: -sum(per_group[g].values()))
    if not size_ordered:
        # Size strata of `folds` groups each, largest first, shuffled inside:
        # the large groups still go out first, and the seed decides which
        # fold each group of a stratum lands in.
        strata = [order[i:i + folds] for i in range(0, len(order), folds)]
        for stratum in strata:
            shuffler.shuffle(stratum)
        order = [name for stratum in strata for name in stratum]
    fold_counts = [Counter() for _ in range(folds)]
    fold_groups = [0] * folds
    assignment: dict[str, int] = {}
    for name in order:
        counts = per_group[name]

        def cost(index: int) -> tuple:
            # How much this group would worsen the fold's distance to its share
            # of every class: the increase, not the level, so an emptier fold wins.
            before = sum((fold_counts[index][c] - target[c]) ** 2 for c in classes)
            after = sum((fold_counts[index][c] + counts[c] - target[c]) ** 2 for c in classes)
            return after - before, fold_groups[index], sum(fold_counts[index].values()), index

        # No cap on groups per fold: the class-count deviation already balances
        # rows; only a fold that would otherwise stay empty is forced.
        empty = [i for i in range(folds) if fold_groups[i] == 0]
        remaining = len(order) - len(assignment)
        candidates = empty if len(empty) >= remaining else range(folds)
        best = min(candidates, key=cost)
        assignment[name] = best
        fold_counts[best].update(counts)
        fold_groups[best] += 1
    summary = [{"fold": i, "n_rows": sum(fold_counts[i].values()), "n_groups": fold_groups[i],
                "class_counts": {c: fold_counts[i][c] for c in classes}} for i in range(folds)]
    return {"assignment": dict(sorted(assignment.items())), "folds_summary": summary}


def cmd_prepare(args, root: Path, **_inject) -> dict:
    registry = load_registry(root)
    entry = find(registry, args.slug)
    path, rel = workspace_file(root, args.file)
    header, rows = read_rows(path)
    for name, column in (("--label", args.label), ("--group", args.group)):
        if column not in header:
            raise Refusal("bad-column", f"{name} {column!r} is not a column of {rel}")
    if args.folds < 2:
        raise Refusal("bad-folds", "--folds must be at least 2")
    n_groups = len({row[args.group] for row in rows})
    if n_groups < args.folds:
        raise Refusal("too-few-groups", f"{n_groups} groups cannot fill {args.folds} folds without "
                                        "putting one subject in two folds")
    if args.seeds is not None and args.seed is not None:
        raise Refusal("bad-argument", "give either --seed (one split) or --seeds (one split per seed), not both")
    if args.seeds is not None and len(set(args.seeds)) != len(args.seeds):
        raise Refusal("bad-argument", f"--seeds repeats a seed: {args.seeds}")
    warnings = []
    if args.seeds is None:
        seeds = [0 if args.seed is None else args.seed]
        repetitions = [stratified_group_folds(rows, args.label, args.group, args.folds, seeds[0])]
        sizes = Counter(row[args.group] for row in rows)
        if len(set(sizes.values())) == len(sizes):
            warnings.append({"code": "inert-seed",
                             "message": "every group has a different size, so this seed changes nothing: "
                                        "the split is the same for any --seed; use --seeds for repetitions"})
    else:
        seeds = list(args.seeds)
        repetitions = [stratified_group_folds(rows, args.label, args.group, args.folds, seed, size_ordered=False)
                       for seed in seeds]
        seen = {}
        for seed, repetition in zip(seeds, repetitions):
            key = json.dumps(repetition["assignment"], sort_keys=True)
            if key in seen:
                raise Refusal("identical-repetitions", f"seeds {seen[key]} and {seed} give the same split; "
                                                       "choose seeds whose splits differ")
            seen[key] = seed
    digest = sha256(path)
    split = repetitions[0]
    version = ((entry.get("preparation") or {}).get("version") or 0) + 1
    folder = datasets_dir(root) / entry["slug"]
    folder.mkdir(parents=True, exist_ok=True)
    splits = {"slug": entry["slug"], "version": version, "file": rel, "sha256": digest, "label": args.label,
              "group": args.group, "folds": args.folds, "seed": seeds[0],
              "method": "stratified group k-fold (greedy, seeded): a row's fold is its group's fold",
              **split}
    if args.seeds is not None:
        splits["method"] = ("stratified group k-fold (greedy, groups taken largest first in size strata of `folds` groups "
                            "shuffled by the seed), repeated once per seed: a row's fold in a repetition is "
                            "its group's fold there")
        splits["seeds"] = seeds
        splits["repetitions"] = [{"seed": seed, **repetition} for seed, repetition in zip(seeds, repetitions)]
    (folder / "splits.json").write_text(json.dumps(splits, indent=2) + "\n", encoding="utf-8")
    lines = [f"# Official preparation of `{entry['slug']}` (version {version})", "",
             "The single preparation the proof of concept and the full experiments both read.",
             "Change it here, never in an experiment's own code.", "",
             "## Source", "", f"- File: `{rel}`", f"- sha256: `{digest}`",
             f"- Rows: {len(rows)}; groups ({args.group}): {n_groups}", "",
             "## Steps", "",
             f"1. Read `{rel}`; check its sha256 against the value above and refuse on mismatch.",
             (f"2. Assign every `{args.group}` to one of {args.folds} folds by stratified group k-fold "
              f"on `{args.label}` (seed {seeds[0]}); no subject appears in two folds."
              if args.seeds is None else
              f"2. For each of {len(seeds)} repetitions, assign every `{args.group}` to one of {args.folds} "
              f"folds by stratified group k-fold on `{args.label}`, taking the groups largest first in size "
              f"strata of {args.folds} that its seed shuffles; no subject appears in two folds of one repetition."),
             ("3. A row's fold is its group's fold, read from `splits.json` (`assignment`)."
              if args.seeds is None else
              "3. A row's fold in a repetition is its group's fold there, read from `splits.json` "
              "(`repetitions[i].assignment`); the first repetition is also `assignment`."), "",
             "## Parameters", "", "| Parameter | Value |", "|---|---|",
             f"| label | `{args.label}` |", f"| group | `{args.group}` |", f"| folds | {args.folds} |",
             f"| {'seed' if args.seeds is None else 'seeds'} | {', '.join(map(str, seeds))} |", ""]
    for seed, repetition in zip(seeds, repetitions):
        lines += [f"## Folds, seed {seed}" if args.seeds is not None else "## Folds", "",
                  "| Fold | Rows | Groups | Classes |", "|---|---|---|---|"]
        lines += [f"| {f['fold']} | {f['n_rows']} | {f['n_groups']} | {json.dumps(f['class_counts'])} |"
                  for f in repetition["folds_summary"]]
        lines.append("")
    lines.pop()
    (folder / "PREPARATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    entry["preparation"] = {"manifest": (folder / "PREPARATION.md").relative_to(root).as_posix(),
                            "splits": (folder / "splits.json").relative_to(root).as_posix(),
                            "version": version, "sha256": digest}
    if rel not in entry["files"]:
        entry["files"].append(rel)
    save_registry(root, registry)
    result = {"slug": entry["slug"], **entry["preparation"], "folds_summary": split["folds_summary"],
              "warnings": warnings}
    if args.seeds is not None:
        result["seeds"] = seeds
    return result


# ------------------------------------------------------------------- publish
def default_runner(argv: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(argv, capture_output=True, text=True, check=False)
    return completed.returncode, completed.stdout, completed.stderr


def cmd_publish(args, root: Path, runner=None, **_inject) -> dict:
    registry = load_registry(root)
    entry = find(registry, args.slug)
    slug = entry["slug"]
    if not OWNER_RE.match(args.owner or ""):
        raise Refusal("bad-owner", f"{args.owner!r} is not a remote account name")
    if entry["license"].get("decision") not in ("allowed", "overridden"):
        raise Refusal("license-not-allowed", f"{slug}'s license decision is "
                      f"{entry['license'].get('decision') or 'missing'}; run license first")
    if args.public and args.consent_public != slug:
        raise Refusal("public-consent-missing", f"--public needs --consent-public {slug}, typed by the operator")
    found = hosts.publisher()
    if found is None:
        raise Refusal("no-publisher", "no host module declares a PUBLISHER")
    host_name, publisher = found
    ref = f"{args.owner}/{slug}"
    folder = datasets_dir(root) / slug
    remote_dir = folder / "remote"
    if not entry["files"]:
        raise Refusal("file-missing", f"{slug} registers no data file; nothing to publish")
    sources = [upload_source(root, Path(rel)) for rel in entry["files"]]
    sources += [upload_source(root, folder / name)
                for name in ("PREPARATION.md", "splits.json", "qc.json", "TOY.md")
                if (folder / name).exists() or (folder / name).is_symlink()]
    if remote_dir.is_symlink():
        raise Refusal("file-outside-workspace", f"{remote_dir.relative_to(root).as_posix()} is a symlink")
    names = [path.name for path in sources]
    if len(set(names)) != len(names):
        raise Refusal("bad-metadata", f"two files share a name: {sorted(names)}")
    missing = [path.relative_to(root).as_posix() for path in sources if not path.is_file()]
    if missing:
        raise Refusal("file-missing", f"registered files missing: {missing}")
    keywords = args.keyword or (["eeg"] if "eeg" in f"{slug} {entry['title']}".lower() else ["tabular"])
    meta = {"title": entry["title"][:50], "id": ref,
            "subtitle": f"{entry['role'].capitalize()} dataset with its official preparation"[:80],
            "licenses": [{"name": entry["license"].get("host_license") or "other"}],
            "keywords": keywords,
            "resources": [{"path": name, "description": f"{name} from the papersmith workspace"} for name in names]}
    problems = publisher.validate_metadata(meta)
    if problems:
        raise Refusal("bad-metadata", "; ".join(problems))
    if remote_dir.exists():
        shutil.rmtree(remote_dir)
    remote_dir.mkdir(parents=True)
    for path in sources:
        shutil.copy2(path, remote_dir / path.name)
    (remote_dir / publisher.metadata_file).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    known = (entry.get("remote") or {}).get("ref") == ref
    notes = args.version_notes or "New version"
    plan = {"create": publisher.create_argv(str(remote_dir), args.public),
            "version": publisher.version_argv(str(remote_dir), notes)}
    if args.consent != slug:
        return {"slug": slug, "dry_run": True, "host": host_name, "folder": remote_dir.relative_to(root).as_posix(),
                "metadata": meta, "plan": " ".join(plan["version"] if known else plan["create"]),
                "next": f"re-run with --consent {slug} to upload (private"
                        + (", public on --consent-public" if args.public else "") + ")"}
    runner = runner or default_runner

    def call(argv):
        try:
            return runner(argv)
        except FileNotFoundError:
            raise Refusal("host-cli-missing", f"`{argv[0]}` is not installed in this environment") from None

    exists = known
    if not exists:
        code, _out, _err = call(publisher.status_argv(ref))
        exists = code == 0
    if exists and args.public:
        raise Refusal("public-on-existing", f"{ref} already exists; change its visibility on the host's "
                                            "settings page, never from here")
    argv = plan["version"] if exists else plan["create"]
    code, out, err = call(argv)
    if code != 0:
        raise Refusal("host-cli-failed", f"{' '.join(argv[:3])} exited {code}: {(err or out)[-500:]}")
    previous = (entry.get("remote") or {}).get("version")
    version = (previous + 1 if isinstance(previous, int) else None) if exists else 1
    visibility = (entry.get("remote") or {}).get("visibility", "private") if exists else \
        ("public" if args.public else "private")
    entry["remote"] = {"ref": ref, "visibility": visibility, "version": version}
    save_registry(root, registry)
    return {"slug": slug, "dry_run": False, "host": host_name, "ran": " ".join(argv), "remote": entry["remote"],
            "output": (out or "")[-1000:], "mount": publisher.mount_hint(ref)}


# -------------------------------------------------------------------- status
def cmd_status(args, root: Path, **_inject) -> dict:
    items = []
    for entry in sorted(load_registry(root), key=lambda item: item["slug"]):
        items.append({"slug": entry["slug"], "role": entry["role"], "title": entry["title"],
                      "license": entry["license"].get("decision") or None,
                      "host_license": entry["license"].get("host_license") or None,
                      "qc": (entry.get("qc") or {}).get("status"),
                      "prepared": bool(entry.get("preparation")),
                      "remote": entry.get("remote")})
    return {"datasets": items}


# ---------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="datasets_cli.py", description=(
        "Toy sets, discovery, license gate, quality checks, official preparation and "
        "private publishing on consent."))
    parser.add_argument("--root", default=".", help="workspace root (default: current directory)")
    sub = parser.add_subparsers(dest="verb", required=True, metavar="{" + ",".join(VERBS) + "}")

    p = sub.add_parser("synth", help="write a seeded toy set")
    p.add_argument("--slug", required=True)
    p.add_argument("--kind", choices=("classification", "eeg"), default="eeg")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--n-subjects", type=int, help="default 6; not with --profile capacity")
    p.add_argument("--n-per-subject", type=int, help="default 20 (12 with --profile capacity)")
    p.add_argument("--channels", type=int, help="default 4 (19, the declared montage, with --profile capacity)")
    p.add_argument("--length", type=int, help="default 128 (256 with --profile capacity)")
    p.add_argument("--sfreq", type=float, help="default 128")
    p.add_argument("--rule", choices=capacity_toy.RULES, help="--profile capacity only: the class rule")
    p.add_argument("--d-prime", type=float, help="--profile capacity --rule monotone only: between-subject separation")
    p.add_argument("--n-train", type=int, default=60, help="--profile capacity: training subjects (even)")
    p.add_argument("--n-val", type=int, default=10, help="--profile capacity: validation subjects (even)")
    p.add_argument("--n-test", type=int, default=100, help="--profile capacity: test subjects (even)")
    p.add_argument("--label-per", choices=("trial", "subject"),
                   help="trial: classes alternate within each subject (default); subject: one class per "
                        "subject, for protocols that decide per subject")
    p.add_argument("--profile", choices=EEG_PROFILES, default="alpha",
                   help="eeg only: alpha (one 10 Hz rhythm), theta-beta (class-dependent 6 Hz / 20 Hz ratio) or capacity "
                        "(fresh training, validation and test subjects under --rule, written as .npy)")
    p.add_argument("--force", action="store_true", help="regenerate an existing slug")
    p.set_defaults(func=cmd_synth)

    p = sub.add_parser("search", help="search the remote dataset hosts")
    p.add_argument("--query", required=True)
    p.add_argument("--hosts", nargs="+", help="restrict to these hosts")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("license", help="record a source license decision")
    p.add_argument("--slug", required=True)
    p.add_argument("--source-license", required=True, help="the license text as the source states it")
    p.add_argument("--override", help="the operator's reason for accepting refused terms")
    p.add_argument("--title")
    p.add_argument("--source-url")
    p.add_argument("--role", choices=("toy", "full"), default="full")
    p.set_defaults(func=cmd_license)

    p = sub.add_parser("qc", help="quality checks into datasets/<slug>/qc.json")
    p.add_argument("--slug", required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--label")
    p.add_argument("--group")
    p.set_defaults(func=cmd_qc)

    p = sub.add_parser("prepare", help="the official subject-wise split and its manifest")
    p.add_argument("--slug", required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--group", required=True)
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--seed", type=int, default=None, help="one split (default 0)")
    p.add_argument("--seeds", type=int, nargs="+", default=None,
                   help="one split per seed (repeated cross-validation); the seed shuffles groups inside size strata")
    p.set_defaults(func=cmd_prepare)

    p = sub.add_parser("publish", help="upload privately on consent (dry run otherwise)")
    p.add_argument("--slug", required=True)
    p.add_argument("--owner", required=True)
    p.add_argument("--version-notes")
    p.add_argument("--keyword", action="append")
    p.add_argument("--consent", help="the dataset slug, typed by the operator, to upload")
    p.add_argument("--public", action="store_true")
    p.add_argument("--consent-public", help="the dataset slug again, to make it public")
    p.add_argument("--dry-run", action="store_true", help="the default without --consent")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("status", help="registry summary")
    p.set_defaults(func=cmd_status)
    return parser


def run(argv: list[str] | None = None, http=None, runner=None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    if getattr(args, "dry_run", False):
        args.consent = None
    try:
        result = args.func(args, root, http=http, runner=runner)
    except Refusal as refusal:
        print(json.dumps({"error": refusal.code, "message": refusal.message, "objective": OBJECTIVE_FLOW},
                         indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
