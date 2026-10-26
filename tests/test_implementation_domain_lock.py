"""Cut 2 (`the-domain-crosses-the-seam`): the two neutrality locks Cut 1
deferred -- "because with no domain words yet moved it would pass
vacuously" -- plus the kit agreement lock (design.md D4) and the
campaign-proposal exclusion (design.md D6). Python mirror of
`tests/proposal-deliberation-domain-profile-lock.test.mjs`, structurally,
never a shared import: these two files exercise the SAME kind of surface
for different runtimes, and a shared helper module would be one more file
this lock itself would then have to scan and clear.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

FORGE = Path(__file__).resolve().parents[1]
SKILLS_DIR = FORGE / "skills"
ENGINE_DIR = SKILLS_DIR / "_core" / "implementation" / "engine"
ENGINE_FILE = ENGINE_DIR / "implementation_engine.py"

from domain_profile import seeded_profile  # noqa: E402  (tests/ on path)
import scratch_forge  # noqa: E402  (tests/ on path)


def _import_engine_module():
    """A fresh, uncached load of the engine itself -- for the ONE test
    (L3) that needs a live attribute off it rather than its source text.
    Seeds `IMPLEMENTATION_DOMAIN_PROFILE` to this skill's own profile for
    the load only (the same `domain_profile.seeded_profile` discipline
    `tests/seal/harness.py` uses), since the engine fails closed at import
    without one -- and an un-restored override would leak into every later
    subprocess in this test process."""
    if str(ENGINE_DIR) not in sys.path:
        sys.path.insert(0, str(ENGINE_DIR))
    spec = importlib.util.spec_from_file_location(
        "impl_domain_lock_engine_probe", ENGINE_FILE)
    module = importlib.util.module_from_spec(spec)
    with seeded_profile(SKILLS_DIR / "proposal-implementation" / "impl_profile.py"):
        spec.loader.exec_module(module)
    return module


def _load_profile_module(path: Path):
    spec = importlib.util.spec_from_file_location(
        f"impl_domain_lock_probe_{path.parent.name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def profile_values_text(profile: Mapping[str, Any]) -> str:
    """Every leaf VALUE `profile` declares, rendered as text, with
    `vocabulary.names` itself excluded (design.md D6, the M1 finding).

    This is the haystack `test_every_declared_name_really_is_that_domain_
    speaking` searches -- never the profile FILE's own source text, which
    trivially contains every literal in its own `names` list no matter what
    it says (M1: the check was vacuous for every profile, not only for a
    namespace word, because `names`'s own declaration is itself part of the
    file it searched). A declared name found here had to equal some OTHER
    leaf's real, engine-read value -- `vocabulary.subject_singular_es`,
    `kit.root`'s own path text, and so on -- which is the property the old
    check only appeared to have.
    """
    parts: list[str] = []

    def walk(value: Any, path: tuple[str, ...]) -> None:
        if path == ("vocabulary", "names"):
            return
        if isinstance(value, Mapping):
            for key, val in value.items():
                walk(val, path + (key,))
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item, path)
        else:
            parts.append(str(value))

    walk(profile, ())
    return " ".join(parts)


def discover_profiles() -> list[dict[str, Any]]:
    """Globs `skills/*/impl_profile.py`, skipping `_core` -- never
    one hardcoded path (design.md D5, mirroring `discoverProfiles` in the
    TS lock). A third skill's `impl_profile.py` is held to the rule the day
    it appears, without this file being edited."""
    profiles = []
    for entry in sorted(SKILLS_DIR.iterdir()):
        if not entry.is_dir() or entry.name == "_core":
            continue
        profile_path = entry / "impl_profile.py"
        if not profile_path.is_file():
            continue
        source = profile_path.read_text(encoding="utf-8")
        module = _load_profile_module(profile_path)
        profile: Mapping[str, Any] = module.PROFILE
        names = list(profile.get("vocabulary", {}).get("names", []))
        profiles.append({
            "skill_name": entry.name, "source": source, "profile": profile,
            "names": names, "values_text": profile_values_text(profile),
        })
    return profiles


def _engine_files() -> list[Path]:
    return sorted(ENGINE_DIR.rglob("*.py"))


def _read_all(paths: list[Path]) -> list[tuple[str, str]]:
    return [(str(path.relative_to(ENGINE_DIR)), path.read_text(encoding="utf-8"))
            for path in paths]


class LockADiscoveryTests(unittest.TestCase):
    """Lock A (design.md D5): profile discovery, by glob. Vacuity guards
    first -- a check that never found a profile would pass every assertion
    below it vacuously."""

    def test_at_least_one_profile_is_discovered(self):
        profiles = discover_profiles()
        self.assertGreaterEqual(
            len(profiles), 1,
            f"expected at least 1 profile under {SKILLS_DIR}/*/impl_profile.py, "
            f"found {len(profiles)}")

    def test_every_profile_declares_a_nonempty_names_list(self):
        for entry in discover_profiles():
            with self.subTest(skill=entry["skill_name"]):
                self.assertGreater(
                    len(entry["names"]), 0,
                    f"{entry['skill_name']} declares no vocabulary.names word, "
                    "so the check below would pass vacuously")

    def test_no_declared_leaf_is_blank(self):
        for entry in discover_profiles():
            with self.subTest(skill=entry["skill_name"]):
                for name in entry["names"]:
                    self.assertNotEqual(name.strip(), "")

    def test_every_declared_name_really_is_that_domain_speaking(self):
        """'a name no profile value contains is not this domain naming
        itself' -- the TS lock's own words, mirrored exactly.

        Rewritten (design.md D6, the M1 finding): the haystack is
        `profile_values_text` -- every leaf VALUE the profile declares,
        `vocabulary.names` itself excluded -- never `entry["source"]`, the
        profile FILE's own text. `entry["source"]` always contains every
        name literally, because the `names` list's own declaration lives in
        that same file; searching it made this check pass for ANY profile,
        which is exactly what `LockAHonestyTests`
        (`tests/test_implementation_domain_mutation.py`) proves by planting
        a name that only the OLD check would have let through.
        """
        for entry in discover_profiles():
            with self.subTest(skill=entry["skill_name"]):
                haystack = entry["values_text"].lower()
                unused = [n for n in entry["names"] if n.lower() not in haystack]
                self.assertEqual(
                    unused, [],
                    f"{entry['skill_name']}: a name no OTHER profile value "
                    "contains is not this domain naming itself")


class LockBEngineNeutralityTests(unittest.TestCase):
    """Lock B (design.md D5): the engine spells no declared domain word --
    scanned as WHOLE TEXT (code, strings, comments, docstrings), which is
    why the comment/docstring sweep (S12) is load-bearing and not
    cosmetic. Word-boundary, case-insensitive."""

    def test_the_whole_engine_directory_is_scanned(self):
        files = _engine_files()
        self.assertGreater(
            len(files), 0, f"expected at least one *.py file under {ENGINE_DIR}")

    def test_the_engine_spells_no_declared_names_word(self):
        profiles = discover_profiles()
        names: set[str] = set()
        for entry in profiles:
            names.update(entry["names"])
        self.assertGreater(len(names), 0, "no names word discovered -- vacuous")
        leaks = []
        for rel, source in _read_all(_engine_files()):
            for name in names:
                if re.search(rf"\b{re.escape(name)}\b", source, re.IGNORECASE):
                    leaks.append(f"{rel} spells {name!r}")
        self.assertEqual(
            leaks, [],
            "the engine must read these off the host-chosen profile, never spell "
            "them: " + "; ".join(leaks))


class LockCDeclaredMarkerTests(unittest.TestCase):
    """Lock C (`a-data-directory-somebody-can-owe`, B2, design.md D7): the
    dataset detector must read the marker off the profile, never spell
    it as an engine literal (spec `implementation-data-demandability`).
    For every profile `discover_profiles()` finds, for every non-`None`
    `documents[N].dataset_marker`, the literal appears in no file under
    `ENGINE_DIR`.

    Vacuous until a shipped profile declares a marker (D7's own note) --
    non-vacuity is asserted directly (`assertGreater(len(markers), 0)`),
    true only after task 8.1 declares `experimental-implementation`'s
    real one. By M4 (design.md), this is a lock over the declared VALUE,
    never the English word `dataset` -- `classify` already returns that
    word as a reason string, so a lock phrased over the word itself
    would be red at HEAD."""

    def _declared_markers(self) -> list[tuple[str, int, str]]:
        markers = []
        for entry in discover_profiles():
            for index, document in enumerate(entry["profile"].get("documents", [])):
                marker = document.get("dataset_marker")
                if marker is not None:
                    markers.append((entry["skill_name"], index, marker))
        return markers

    def test_at_least_one_declared_marker_exists(self):
        markers = self._declared_markers()
        self.assertGreater(
            len(markers), 0,
            "no profile declares a non-None dataset_marker -- every "
            "assertion below would pass vacuously")

    def test_no_declared_marker_appears_in_the_engine(self):
        markers = self._declared_markers()
        leaks = []
        for rel, source in _read_all(_engine_files()):
            for skill_name, index, marker in markers:
                if marker in source:
                    leaks.append(
                        f"{rel} spells {skill_name}'s documents[{index}]"
                        f".dataset_marker literal {marker!r}")
        self.assertEqual(
            leaks, [],
            "the engine must read a declared dataset_marker off the "
            "profile, never spell it: " + "; ".join(leaks))


class LockDDeclaredLocatorTests(unittest.TestCase):
    """`the-agreement-nothing-computes` (Slice D, design.md M1/D1, tasks.md
    1.8): Lock C's shape, stronger. For every profile `discover_profiles()`
    finds, for every `documents[N].block_locator`, each of the THREE
    declared literals (`pattern`, `block_pattern`, `identity`) appears in
    no file under `ENGINE_DIR`. Non-vacuity asserted explicitly -- both
    shipped profiles declare a non-null locator on every entry, so this is
    non-vacuous the day it lands, unlike Lock C which had to wait for a
    second profile to declare a marker. This is the lock M1 says a
    matcher-only leaf (option 2 of design.md D1) would have let pass: a
    lock over the declared MATCHER alone would stay silent while
    `cmd_handoff`'s renderer still spelled the hardcoded `\\tag{` template
    -- the exact "protected half reads as proof of the whole" scar, one
    level up.
    """

    def _declared_locators(self) -> list[tuple[str, int, str, str]]:
        """`(skill_name, index, sub_key, literal)` for every declared
        `block_locator` sub-key across every discovered profile."""
        locators = []
        for entry in discover_profiles():
            for index, document in enumerate(entry["profile"].get("documents", [])):
                locator = document.get("block_locator")
                if not isinstance(locator, Mapping):
                    continue
                for sub_key in ("pattern", "block_pattern", "identity"):
                    value = locator.get(sub_key)
                    if value:
                        locators.append((entry["skill_name"], index, sub_key, value))
        return locators

    def test_at_least_one_declared_locator_exists(self):
        locators = self._declared_locators()
        self.assertGreater(
            len(locators), 0,
            "no profile declares a block_locator -- every assertion below "
            "would pass vacuously")

    def test_no_declared_locator_literal_appears_in_the_engine(self):
        locators = self._declared_locators()
        leaks = []
        for rel, source in _read_all(_engine_files()):
            for skill_name, index, sub_key, literal in locators:
                if literal in source:
                    leaks.append(
                        f"{rel} spells {skill_name}'s documents[{index}]"
                        f".block_locator.{sub_key} literal {literal!r}")
        self.assertEqual(
            leaks, [],
            "the engine must read a declared block_locator off the "
            "profile, never spell it: " + "; ".join(leaks))


# --- M5: the derived denylist (TS C-3), now landable ------------------------
#
# Deferred at Cut 2 (`the-domain-crosses-the-seam`): with one implementation
# profile on disk the "others" set is empty and every word >=5 letters in
# `OBJECTIVE_FLOW` becomes a denylist entry -- not a stricter lock, an
# unsatisfiable one. A second profile now exists (this change), so the
# "others" set is non-empty and this lands as a real test, never a
# `skipTest` (a skip would move the pinned `skipped=6`, tasks.md 4.5/13.8).

#: Every ``[A-Za-z]{5,}`` word, case-folded -- the Python mirror of
#: `objectiveWords` in `tests/proposal-deliberation-domain-profile-lock.test.mjs`.
_NORTH_WORD_RE = re.compile(r"[A-Za-z]{5,}")


def north_words(profile: Mapping[str, Any]) -> set[str]:
    """Every word `objectiveWords` (the TS lock) would extract: `purpose`,
    every stage's `establishes`/`behindWhen`, `arrival`, `humanStops` --
    read directly off `profile["objective"]` (the module is already
    imported by `discover_profiles()`; no `extractBlock` regex is needed,
    unlike the TS side, which reads unparsed source text)."""
    objective = profile["objective"]
    texts = [objective.get("purpose", ""), objective.get("arrival", "")]
    texts.extend(objective.get("humanStops", []))
    for stage in objective.get("stages", []):
        texts.append(stage.get("establishes", ""))
        texts.append(stage.get("behindWhen", ""))
    words: set[str] = set()
    for text in texts:
        words.update(match.lower() for match in _NORTH_WORD_RE.findall(text))
    return words


def build_denylist(profiles: list[dict[str, Any]]) -> dict[str, str]:
    """A word appearing in EXACTLY ONE profile's north is that domain's own
    subject matter and may not appear, word-boundary, in the engine. A word
    both norths use is engine vocabulary, never flagged -- the Python
    mirror of `buildDenylist` (TS C-3), never a hand-written list."""
    word_sets = {entry["skill_name"]: north_words(entry["profile"])
                for entry in profiles}
    denylist: dict[str, str] = {}
    for skill_name, words in word_sets.items():
        others: set[str] = set()
        for other_name, other_words in word_sets.items():
            if other_name == skill_name:
                continue
            others.update(other_words)
        for word in words:
            if word not in others:
                denylist[word] = skill_name
    return denylist


#: Measured at apply (task 4.6), never predicted -- real occurrence counts
#: (case-insensitive, word-boundary) of every denylist word that the engine
#: ALREADY spells as pre-existing, load-bearing vocabulary, unrelated to
#: either domain's `vocabulary.names` (which Lock B already holds to zero).
#: Two profiles on disk today: `experimental-implementation` (this change)
#: and `proposal-implementation`. Five denylist words measured genuinely
#: 2026-09-14, M2 closed: `cmd_handoff` stopped composing a sentence of
#: its own in one fixed human tongue, so the prose that carried `local`,
#: `measurement`, `named`, `recorded` and `remedy` is gone and five pins
#: SHRINK (40->30, 43->42, 178->177, 77->75, 55->54). A shrink is what
#: this lock permits deliberately; it is recorded here so the next reader
#: knows which change took them down and does not restore them by hand.
#:
#: ABSENT from the engine and need no pin at all: `formulation`,
#: `mathematical`, `mathematics`, `statistical`, `traced` -- the first three
#: are also members of `proposal-implementation`'s own `vocabulary.names`,
#: so their zero count is cross-confirmed by Lock B independently. Each
#: entry below may only move deliberately, never silently (test 3); a pin
#: whose word left the denylist is a dead exemption (also test 3); a pin
#: at zero is a defect (test 4).
#:
#: `"module"`'s pin grew from 171 to 183 in Cut 3 slice C
#: (`the-second-document-verified-on-its-own-terms`, design.md D4/D5):
#: the per-document fidelity fold reads the existing `{"module": rel,
#: ...}` dict shape by that exact key, once per document index
#: (`module["module"]`, `for module in modules`) -- the SAME pre-existing
#: field this pin already counted heavily before this change, now read
#: from more call sites. A deliberate, measured, recorded growth, never a
#: silent bump.
#: `a-data-directory-somebody-can-owe` (B1): ten of these grew again, the
#: same deliberate, measured, recorded shape `"module"`'s own comment
#: above already established for Cut 3 slice C -- new engine prose (the
#: dataset detector, `--revision`'s threading through `build_plan`'s
#: three call sites, `boundTo`) reads naturally with ordinary English
#: words this pin already exempts; contorting every sentence to avoid
#: them would be the cosmetic exercise this lock's own docstring warns
#: against, not a stronger guard. `after` 78->79, `approved` 25->29,
#: `before` 223->224, `beside` 91->92, `check` 145->146, `command`
#: 263->266, `materialize` 29->31, `rather` 330->331, `recorded` 75->76,
#: `refuses` 86->87.
#: `the-agreement-nothing-computes` (Slice D, D1): eleven more grew, the
#: identical deliberate, measured shape -- `document_block_locator`,
#: (upstream-sync 2026-09-13): `after` 79->80, the adopt port's own prose
#: (`_adopt_survey`'s destination-conflict message and the adoption report),
#: recorded here so the pin moves with every word it gained and never in
#: silence.
#: `finding_document_indices`, `_single_named_document_index` and the
#: per-document `remedy_compatibility` loop's own prose reads naturally
#: with ordinary English words this pin already exempts. `against`
#: 181->184, `before` 224->225, `carries` 176->177, `commands` 15->16,
#: `declaration` 189->190, `module` 183->184, `named` 164->169, `refuses`
#: 87->89, `value` 219->223, `whose` 141->142, `write` 104->106.
#: `the-agreement-nothing-computes` (Slice D, D3): eleven more grew again,
#: the identical shape -- `cmd_agree`'s own docstring/refusal prose and
#: the `GATING_COMMANDS`/`GATING_REFUSALS`/parser comments introducing it
#: read naturally with ordinary English words this pin already exempts.
#: `agreed` 23->24, `before` 225->226, `carries` 177->178, `check`
#: 146->150, `claim` 34->35, `command` 266->268, `commands` 16->19,
#: `declaration` 190->191, `module` 184->186, `readable` 23->24, `refuses`
#: 89->91, `value` 223->227.
#: `the-agreement-nothing-computes` (Slice D4): two more grew -- the
#: `--acknowledge` flag's own help text and `cmd_agree`'s reworded
#: comment about it read naturally with two words this pin already
#: exempts. `named` 169->171, `value` 227->229.
#: `the-agreement-nothing-computes` (Slice D5): thirteen more grew --
#: `local_reach`'s own docstring, `cmd_handoff`'s `sources_by_document`
#: comment, and `HANDOFF_DOCUMENT_UNREADABLE`'s own refusal/docstring
#: prose all read naturally with words this pin already exempts.
#: `actually` 75->76, `answers` 98->99, `before` 226->227, `empty`
#: 111->113, `local` 31->35, `module` 186->187, `named` 171->177,
#: `rather` 331->332, `refuses` 91->92, `remedy` 48->49, `value`
#: 229->233, `whose` 142->145, `write` 106->107.
#: `the-agreement-nothing-computes` (Slice D5, second growth): the
#: mixed-reach branch's own docstring/comment/refusal prose (design.md
#: D10's fourth deferredBecause value) grew three more. `local` 35->40,
#: `named` 177->178, `recorded` 76->77.
#: `fix/skills-critical-review`: the four per-document consumers of one
#: premise (`cmd_admit`, `finding_impact`, `cmd_handoff`, `cmd_verify`'s
#: rows), the two shared readers they now call, walk's retired rehearse act
#: and the front door's derived name. Their own docstrings and comments were
#: compressed first -- nine of the words that grew on the first pass came
#: back down that way -- and what is left below reads naturally with
#: ordinary English words this pin already exempts. `before` 227->228, `measured` 140->141, `module` 187->189, `object` 27->28, `place` 50->51, `refuses` 92->93, `remedy` 49->55, `something` 67->69.
#: Six SHRANK, and are recorded here for the same reason: the engine's
#: module docstring stopped hand-listing four subcommands argparse already
#: prints in full, and the compressed comments gave the rest back. `against` 184->183, `approved` 29->28, `commands` 19->18, `readable` 24->23, `resolves` 32->31, `whose` 145->144.
#: `the-comparison-nobody-asked-for` (Unit 2, design.md D1/D2/D3/D10):
#: `revision`/`premises` relocated off `__benchmark__` onto their own
#: `__implementation__` literal (`resolve_implementation_declaration`,
#: `declaration_root`, `_implementation_predates_relocation`), and the
#: three sibling resolvers' docstrings were rewritten to point at the new
#: root. `authored_package_init` grew a ~100-line prefilled-empty template
#: (`_DEFAULT_PACKAGE_DECLARATIONS`) carrying the guidance comments moved
#: out of the kit asset, and `cmd_verify`'s two revision readers were
#: rewritten to source `__implementation__` unconditionally. All of that is
#: new engine prose, not a domain word: twenty-seven words already exempted
#: here read naturally inside it and grew. `after` 79->84, `against`
#: 183->184, `agreed` 24->26, `answered` 71->73, `answers` 99->100,
#: `before` 228->232, `benchmark` 91->98, `beside` 92->94, `check`
#: 150->151, `compares` 23->24, `declaration` 191->202, `empty` 113->120,
#: `isolated` 4->5, `leave` 9->11, `leaves` 34->35, `local` 30->34,
#: `longer` 46->47, `materialized` 10->11, `module` 189->193, `object`
#: 28->29, `place` 51->54, `produces` 44->46, `rather` 332->341, `remote`
#: 55->58, `reported` 142->143, `ruled` 8->9, `scaffolded` 4->7,
#: `something` 69->70, `steps` 133->135, `value` 233->235, `whose`
#: 144->148.
#: Two SHRANK: docstring compression elsewhere in the same edit gave two
#: words back. `invariant` 22->21, `measured` 141->140.
#: Eight LEFT THE DENYLIST ENTIRELY and their pins are removed, not
#: shrunk to zero: `experimental-implementation/impl_profile.py`'s
#: "standing" stage was rewritten in the same commit (design D3, task
#: 2.15) to name the relocated gate the identical way
#: `proposal-implementation`'s own profile does, so `carries`,
#: `materialize`, `objects`, `premises`, `refuses` and `stage` are now
#: BOTH profiles' own north vocabulary -- ordinary engine vocabulary,
#: never single-owner again. `named` and `readable` left with them: they
#: were the exact words the rewritten sentence replaced, and neither
#: survives in the other profile's own north either. A word leaving the
#: denylist needs no exemption at all, dead or otherwise.
#: `the-comparison-nobody-asked-for` (Unit 4, design.md D5/D6/D16): a
#: decline is now a bare `discuss` event, kept stable by
#: `_benchmark_offer_question` and folded once per `cmd_probe` call
#: through `_discussion_buckets`/`_answered_from_buckets`/
#: `_answered_event_from`/`_decision_from_event`, and `previous_implementations`
#: excludes any `_Benchmark`-suffixed directory. All new engine prose, not
#: a domain word: twenty-six words already exempted here read naturally
#: inside it and grew. `actually` 76->78, `after` 84->85, `against`
#: 184->185, `answered` 73->82, `answers` 100->101, `before` 232->238,
#: `beside` 94->95, `declaration` 202->204, `empty` 120->123, `leaves`
#: 35->36, `longer` 47->48, `measured` 140->141, `module` 193->194,
#: `notebooks` 107->110, `object` 29->30, `pilot` 119->123, `produces`
#: 46->51, `rather` 341->349, `recorded` 75->76, `remote` 58->61,
#: `reported` 143->144, `scaffolded` 7->10, `steps` 135->139, `whose`
#: 148->151.
#: Two SHRANK: the docstring rewrite of `previous_implementations` and the
#: three-way ladder comment above the new `declined` override each read
#: differently from what they replaced. `benchmark` 98->97, `place`
#: 54->53.
#: `the-comparison-nobody-asked-for` (Unit 4b, design.md D11/D12/D13/D14):
#: the acid test's own draft (`validation_proposal`), its offer
#: constructor (`_validation_offer_question`/`_canonical_premises`), the
#: `PROBE_DRAFTS` registry replacing the `wiring: bool` flag, and the
#: three-way `benchmark`/`validate`/`declined` ladder branch are all new
#: engine prose, not a domain word: twenty-one words already exempted
#: here read naturally inside it and grew. `against` 185->188, `answered`
#: 82->85, `answers` 101->104, `before` 238->239, `benchmark` 97->99,
#: `beside` 95->98, `claim` 35->36, `declaration` 204->205, `empty`
#: 123->127, `local` 34->37, `longer` 48->49, `makes` 43->44, `object`
#: 30->33, `rather` 349->358, `remote` 61->65, `reported` 144->145,
#: `small` 4->8, `something` 70->71, `validated` 7->8, `value` 235->239,
#: `whose` 151->152. None shrank and none left the denylist.
#: `the-comparison-nobody-asked-for` (Unit 3, design.md D4/D8/D13): the
#: scaffold/harness list flip, the `declare-first` narrowing to
#: `"undeclared"` only, the derived-count sweep (D8) removing every
#: hand-written gap/ladder numeral from engine docstrings, and the Unit 3
#: correction moving the three-way `benchmark`/`validate`/`declined`
#: branch to last among `cmd_probe`'s overrides (so a genuinely owed
#: repair outranks a declined comparison, per the fifth spec revision) are
#: all new/rewritten engine prose, not a domain word: eleven words already
#: exempted here read naturally inside it and grew. `after` 85->87,
#: `agreed` 26->27, `benchmark` 99->105, `declaration` 205->207,
#: `destinations` 37->38, `longer` 49->51, `materialized` 11->12,
#: `measured` 141->142, `rather` 358->359, `scaffolded` 10->11, `whose`
#: 152->153. One SHRANK: the three-way branch's own comment, rewritten for
#: its new last-in-chain position, reads differently from what it
#: replaced. `before` 239->238. None left the denylist; no new leak.
#: `the-comparison-nobody-asked-for` (Unit 6a, design.md D19-D21): the
#: closed `discuss --decision yes|no` token, its `DISCUSS_DECISION_NOT_A_TOKEN`
#: refusal, the absent-token migration rule (D20), the `decisions.*.decision`
#: payload member, and the `build-first` rung (fourth arm of the same
#: last-among-the-overrides branch Unit 3 placed) are all new engine prose,
#: not a domain word: eighteen words already exempted here read naturally
#: inside it and grew. `actually` 78->80, `after` 87->89, `against`
#: 188->189, `answered` 85->92, `before` 238->243, `beside` 98->99, `check`
#: 151->153, `empty` 127->129, `experiment` 24->25, `invariant` 21->22,
#: `longer` 51->53, `makes` 44->46, `rather` 359->366, `recorded` 76->78,
#: `reported` 145->146, `value` 239->242, `whose` 153->154, `write`
#: 107->109. None shrank and none left the denylist; `test_2` confirms no
#: new unpinned leak either.
#: upstream-sync 2026-09-15: re-measured after merging upstream/main bf00e17
#: (engine port + fork adopt deltas + both sides' prose). Every value below is
#: taken from the merged tree, never assumed; pinned == every denylist word the
#: engine actually spells, by construction.
#: `the-holder-each-skill-declares` (Phase 2, design D2/D3/D8/D9/D12):
#: `holder_resolution`, `_header_document_count_detail`, the five
#: repointed call sites, the new `HOLDER_UNDECLARED` refusal and its
#: doctrine/prose sweep are all new engine prose, not a domain word:
#: thirteen words already exempted here read naturally inside it and
#: grew. `before` 252->253, `beside` 104->109, `check` 157->158, `command`
#: 272->273, `declaration` 209->211, `empty` 129->130, `module` 194->195,
#: `rather` 376->377, `reported` 146->147, `something` 74->75, `sweep`
#: 7->10, `validated` 8->9, `write` 110->134 (the settle-mode ambiguity
#: messages moved to `write` into a single holder). One SHRANK,
#: deliberately: `agreed` 27->16 -- the D12 prose sweep amends every
#: engine-voice/fact assertion of the literal `AGREED.md` to name the
#: declared holder leaf instead, leaving only the dated/target-specific
#: measurements standing. None left the denylist; `test_2` confirms no
#: new unpinned leak either.
#: `the-holder-each-skill-declares` (Phase 5, carried defect fix): the
#: rewritten `HOLDER_REPAIR_AMBIGUOUS` refusal detail and its published
#: `resolve` question (naming only exits a reader can actually take,
#: never `--repair-header` as the remedy for a refusal `--repair-header`
#: itself produced) are rewritten engine prose, not a domain word: two
#: words already exempted here read naturally inside it and grew. `after`
#: 91->92, `against` 195->196. None left the denylist; `test_2` confirms
#: no new unpinned leak either.
#: `cross-skill-consistency` (B4): `cmd_settle`'s docstring drops two
#: paragraphs that argued for leaving un-ticking out and for refusing a
#: missing `## Reversed`, both now implemented (a tick is corrected by
#: `--reverse`; the first reversal opens the heading). Five words SHRANK,
#: deliberately: `against` 197->196, `command` 278->275, `measured`
#: 145->143, `rather` 387->384, `something` 77->76.
#: `cross-skill-consistency` (C9): `admit --no-findings` returns its own
#: result payload and `verify` reads a stale no-findings ruling as owed
#: again. Two literals the shapes require, not prose: the payload's
#: `"command"` key (`command` 275->276) and the `"incomplete"` status
#: (`incomplete` 28->29). The surrounding comments were worded to move
#: nothing else.
#: `cross-skill-consistency` (C8): `handoff`'s new `deferredBecause` code
#: `"prose-remedy"` is a published machine value, not prose (`remedy`
#: 56->57); every comment beside it says "correction" instead.
#: `cross-skill-consistency` (C10): `_called_roots` walks an attribute
#: call down to the name it starts from through `ast.Attribute.value`,
#: twice -- code, not prose (`value` 244->246).
#: `cross-skill-consistency` (C11): `materialize --module` is a CLI flag the
#: engine must spell -- its parser registration, its `getattr` read and the
#: one refusal that names it (`module` 195->198). Variables and prose around
#: it say `stem`/"file" instead.
#: `cross-skill-consistency` (C12): the objects stage fills the kit's
#: `{{MODULE}}` token, whose key the engine must spell once (`module`
#: 198->199), and `_materialize_plan_gate` now returns the plan it read
#: (`return approved`, `approved` 47->48; its local keeps the name the seed
#: mutation test anchors on). One SHRANK, deliberately: `_stage_objects`
#: names its owed paths `owed` (`destinations` 39->36).
#: `cross-skill-consistency` (X17): `position` and `settle` write the declared
#: holder's scaffold with the splice instead of first; the two copies of the
#: comment explaining the early creation write are gone. Three SHRANK,
#: deliberately: `before` 263->261, `empty` 132->131, `write` 156->154.
#: backlog #52: `_resolve_survey_target` no longer restates the
#: workspace's `implementations/` path in two docstrings. One SHRANK,
#: deliberately: `implementations` 4->3.
M5_PINNED_RESIDUE: dict[str, int] = {
    "actually": 83, "admissible": 3, "after": 93, "against": 196,
    "agreed": 16, "answered": 97, "answers": 107, "approved": 48,
    "audit": 19, "before": 261, "benchmark": 108, "beside": 111,
    "check": 168, "checkable": 3, "claim": 41, "command": 276,
    "commands": 18, "compares": 25, "declaration": 212,
    "destinations": 36, "empty": 131, "established": 5, "experiment": 25,
    "experiments": 6, "implementations": 3, "incomplete": 29,
    "invariant": 22, "isolated": 5, "leave": 11, "leaves": 38,
    "local": 37, "longer": 54, "makes": 48, "materialized": 12,
    "measured": 143, "measurement": 43, "module": 199, "notebooks": 110,
    "object": 33, "pilot": 123, "place": 58, "produces": 51,
    "rather": 384, "recorded": 81, "remedy": 57, "remote": 65,
    "reported": 149, "resolves": 34, "ruled": 9, "runnable": 15,
    "scaffolded": 12, "sitting": 9, "small": 8, "something": 76,
    "steps": 139, "sweep": 11, "validated": 10, "value": 246, "whose": 156,
    "write": 154, "wrong": 52
}
#: Unit 6b (Part B, the transitions): thirteen pins grew from the new
#: engine prose alone (`_comparison_reuses_acid_test_question`,
#: `_validate_publication`'s own branch, `cmd_probe`'s new reachability
#: branch and fact threading) -- `actually`, `answered`, `answers`,
#: `before`, `benchmark`, `beside`, `declaration`, `measured`,
#: `measurement`, `place`, `rather`, `something`, `value`. Zero admissions,
#: zero removals; `SKILL.md`/`references/usage.md` are outside
#: `_engine_files()`'s own scan, the identical restraint every prior
#: unit's changelog block already states.
#: `the-holder-each-skill-declares` Phase 3 (create-on-absent + the two
#: carried-item fixes, `cmd_settle`/`cmd_position`/`_chosen_holder` docstring
#: and comment growth alone): ten pins grew -- `after`, `against`, `before`,
#: `command`, `empty`, `leaves`, `remedy`, `resolves`, `write`, `wrong`.
#: Zero admissions, zero removals; the same restraint every prior unit's
#: changelog block states.
#: `the-holder-each-skill-declares` Phase 4 (`--repair-header`'s new
#: functions, docstrings and comments alone, `_cmd_position_repair`/
#: `_holder_repair_ambiguous_detail` beside the mutual-exclusivity guard
#: and the two new `GATING_REFUSALS`/`_WORK_STATE_RESOLUTIONS` entries):
#: fourteen pins grew -- `actually`, `against`, `answers`, `before`,
#: `command`, `empty`, `place`, `rather`, `recorded`, `resolves`,
#: `something`, `sweep`, `whose`, `write`. Zero admissions, zero removals;
#: the same restraint every prior unit's changelog block states.
#: `the-holder-each-skill-declares` Phase 7 (operator-authorized post-verify
#: extension closing the CRITICAL defect: one new `elif` branch in
#: `cmd_position`'s holder-sweep dispatch, comments only -- no new
#: function, no new refusal code): eight pins grew by their comment's own
#: prose alone -- `against` (+1), `measured` (+1), `rather` (+2),
#: `reported` (+1), `resolves` (+1), `sweep` (+1), `whose` (+2), `write`
#: (+1). Zero admissions, zero removals; the same restraint every prior
#: unit's changelog block states.
#: `the-holder-each-skill-declares` Phase 8 (operator-authorized extension
#: closing the READ face of the same CRITICAL defect: the new
#: `_absent_position_state` extraction, `cmd_gate`'s own fold-to-absent
#: guard, and the widened `cmd_position` dispatch -- now three-way on
#: `holder_resolution_result["action"]` instead of two, closing the
#: `"create"`-action collision alongside the `"undeclared"` one Phase 7
#: closed -- comments and one new function docstring only, no new refusal
#: code): seven pins grew and two SHRANK by their comment's own prose
#: alone. Grew: `before` (+1), `beside` (+1), `check` (+3), `makes` (+1),
#: `rather` (+2), `validated` (+1), `write` (+1). SHRANK, deliberately:
#: `sweep` 12->11 (the Phase 7 comment naming "this sweep's OWN, unrelated
#: block scan" was rewritten into the `else` branch's own comment, once,
#: rather than twice); `whose` 157->156 (the rewritten `elif`'s docstring
#: reads differently from what it replaced). Zero admissions; the same
#: restraint every prior unit's changelog block states.
#: `the-product-the-history-never-took` (design D5, the ignored-path check
#: and its new `STEP_WROTE_IGNORED`/`_step_wrote_ignored` prose alone):
#: eight pins grew by the new constant's and helper's own prose -- `answered`
#: 95->97, `before` 260->261, `beside` 110->111, `check` 161->164,
#: `declaration` 211->212, `rather` 382->385, `reported` 148->149, `write`
#: 153->154. Zero admissions, zero removals; the same restraint every prior
#: unit's changelog block states.
#: `re-pointing-a-proof-is-not-retracting-a-claim` (`settle --attach
#: --replace`: the refusal ladder, the renderer's third case, the
#: docstring roster's items 3/17/18/19, and the amended `--witness`/
#: `--attach` argparse help -- engine prose alone, no new function):
#: nine pins grew -- `after` 92->93, `before` 261->263, `check` 164->168,
#: `claim` 36->41, `command` 277->278, `rather` 385->387, `recorded`
#: 80->81, `value` 243->244, `write` 154->156. Zero admissions, zero
#: removals; the same restraint every prior unit's changelog block
#: states.


class DerivedDenylistTests(unittest.TestCase):
    """M5 (design.md D9), four separate test methods, never one method with
    four asserts (`b3ca9aa`'s lesson: a method halts at its first failing
    assertion)."""

    def test_1_vacuity_at_least_two_profiles_and_a_nonempty_denylist(self):
        profiles = discover_profiles()
        self.assertGreaterEqual(
            len(profiles), 2,
            "expected at least 2 profiles on disk; the denylist needs a "
            "second north to compare against or it is unsatisfiable rather "
            "than strict")
        denylist = build_denylist(profiles)
        self.assertGreater(
            len(denylist), 0,
            "no single-owner north word was derived -- if two profiles' "
            "norths were accidentally IDENTICAL text, every word would be "
            "shared and the denylist would be empty (the same self-check "
            "the TS lock records)")

    def test_2_no_unpinned_denylist_word_appears_in_the_engine(self):
        denylist = build_denylist(discover_profiles())
        leaks = []
        for rel, source in _read_all(_engine_files()):
            for word, owner in denylist.items():
                if word in M5_PINNED_RESIDUE:
                    continue
                if re.search(rf"\b{re.escape(word)}\b", source, re.IGNORECASE):
                    leaks.append(f"{rel} spells {word!r} ({owner}'s own north)")
        self.assertEqual(
            leaks, [],
            "a core engine file spells a word belonging to only one "
            "domain's own north, and it carries no pin: " + "; ".join(leaks))

    def test_3_every_pinned_words_count_equals_its_pin_and_stays_in_the_denylist(self):
        denylist = build_denylist(discover_profiles())
        for word, expected_count in M5_PINNED_RESIDUE.items():
            with self.subTest(word=word):
                self.assertIn(
                    word, denylist,
                    f"{word!r} is pinned but no longer in the derived "
                    "denylist -- a pin for a word that left the denylist "
                    "is a dead exemption")
                count = sum(
                    len(re.findall(rf"\b{re.escape(word)}\b", source, re.IGNORECASE))
                    for _, source in _read_all(_engine_files()))
                self.assertEqual(
                    count, expected_count,
                    f"{word!r}'s occurrence count drifted from its pin "
                    f"({expected_count}) to {count} -- a pin may only shrink "
                    "deliberately, never move silently")

    def test_4_no_pinned_word_has_a_zero_count(self):
        for word, expected_count in M5_PINNED_RESIDUE.items():
            with self.subTest(word=word):
                self.assertGreater(
                    expected_count, 0,
                    f"{word!r} is pinned at zero -- a pin exists to record "
                    "genuine pre-existing residue, and a zero-count pin is "
                    "a dead exemption for a word the engine does not spell")


def _kit_root_for(profile: Mapping[str, Any]) -> Path:
    return Path(profile["kit"]["root"])


def kit_shipping_profiles() -> list[tuple[str, Mapping[str, Any]]]:
    """Task 4.3 (design.md D9): every discovered profile whose own
    `kit.root` actually ships `assets/kit/src/module.py` -- derived, never
    the single hardcoded `proposal-implementation` path this class used to
    carry. A third skill's kit is held to this lock the day it appears,
    without this file being edited (mutation X9: pointing this filter at
    zero kit-shipping profiles must redden the vacuity guard below)."""
    shipping = []
    for entry in discover_profiles():
        kit_root = _kit_root_for(entry["profile"])
        if (kit_root / "assets" / "kit" / "src" / "module.py").is_file():
            shipping.append((entry["skill_name"], entry["profile"]))
    return shipping


class KitAgreementLockTests(unittest.TestCase):
    """D4/D9 (design.md): the kit template's provenance keys agree with the
    profile -- six sites, two of them EXECUTABLE code that runs inside a
    target's own interpreter, which is the sharpest reason this needs a
    test: a divergence there fails in somebody else's repository, not in
    this suite. No kit file is ever edited by this lock or by this cut.

    `_profile()` no longer hardcodes `proposal-implementation`'s path
    (task 4.3): every test method below iterates `kit_shipping_profiles()`,
    `subTest(skill=...)` per profile, against non-empty and coverage-
    equality assertions. This skill (`experimental-implementation`) ships
    no kit (task 4.4, M3) and is correctly ABSENT from that derived set --
    confirmed directly by `test_this_skill_is_recorded_kitless` below,
    never merely assumed."""

    def test_at_least_one_kit_shipping_profile_is_discovered(self):
        """Vacuity guard, first -- every assertion below would pass on an
        empty set otherwise (mutation X9 reddens exactly this)."""
        shipping = kit_shipping_profiles()
        self.assertGreaterEqual(
            len(shipping), 1,
            "expected at least one kit-shipping profile; found none -- "
            "every assertion below would pass vacuously")

    def test_this_skill_is_recorded_kitless(self):
        """Task 4.4: this skill ships no `assets/kit/` at all (M3) and is
        therefore correctly absent from `kit_shipping_profiles()`."""
        shipping_names = {name for name, _ in kit_shipping_profiles()}
        self.assertNotIn("experimental-implementation", shipping_names)
        this_skill_root = SKILLS_DIR / "experimental-implementation"
        self.assertFalse(
            (this_skill_root / "assets" / "kit" / "src" / "module.py").is_file(),
            "experimental-implementation ships assets/kit/src/module.py -- "
            "it is no longer kitless and kit_shipping_profiles() must find it")

    def test_module_py_declares_the_agreed_provenance_keys(self):
        checked = set()
        for skill_name, profile in kit_shipping_profiles():
            with self.subTest(skill=skill_name):
                kit_dir = _kit_root_for(profile) / "assets" / "kit"
                source = (kit_dir / "src" / "module.py").read_text(encoding="utf-8")
                match = re.search(r"__provenance__\s*=\s*\{(.*?)\n\}", source, re.DOTALL)
                self.assertIsNotNone(match, "module.py declares no __provenance__ literal")
                keys = set(re.findall(r'"(\w+)":', match.group(1)))
                self.assertGreater(len(keys), 0, "extraction found no keys -- vacuous")
                claim_key = profile["provenance"]["claim_key"]
                self.assertEqual(keys, {"revision", "sections", claim_key, "invariants"})
                checked.add(skill_name)
        self.assertEqual(checked, {name for name, _ in kit_shipping_profiles()})

    def test_module_py_rules_docstring_names_both_keys(self):
        checked = set()
        for skill_name, profile in kit_shipping_profiles():
            with self.subTest(skill=skill_name):
                kit_dir = _kit_root_for(profile) / "assets" / "kit"
                source = (kit_dir / "src" / "module.py").read_text(encoding="utf-8")
                claim_key = profile["provenance"]["claim_key"]
                self.assertIn(f'`{claim_key}`', source)
                self.assertIn("`sections`", source)
                checked.add(skill_name)
        self.assertEqual(checked, {name for name, _ in kit_shipping_profiles()})

    def test_src_benchmark_arms_example_spells_sections(self):
        checked = set()
        for skill_name, profile in kit_shipping_profiles():
            with self.subTest(skill=skill_name):
                kit_dir = _kit_root_for(profile) / "assets" / "kit"
                source = (kit_dir / "src_benchmark" / "__init__.py").read_text(
                    encoding="utf-8")
                example = re.search(r'#\s*"arms":\s*\{.*?\n(?:\s*#.*\n)*', source)
                self.assertIsNotNone(example, "no commented arms example found -- vacuous")
                self.assertIn("sections", example.group(0))
                checked.add(skill_name)
        self.assertEqual(checked, {name for name, _ in kit_shipping_profiles()})

    def test_findings_py_commented_keys_equal_locus_and_remedy_locus(self):
        checked = set()
        for skill_name, profile in kit_shipping_profiles():
            with self.subTest(skill=skill_name):
                kit_dir = _kit_root_for(profile) / "assets" / "kit"
                source = (kit_dir / "tests" / "findings.py").read_text(encoding="utf-8")
                locus_key = profile["findings"]["locus_key"]
                remedy_locus_key = profile["findings"]["remedy_locus_key"]
                self.assertIn(f'#     "{locus_key}"', source)
                self.assertIn(f'#     "{remedy_locus_key}"', source)
                checked.add(skill_name)
        self.assertEqual(checked, {name for name, _ in kit_shipping_profiles()})

    def test_test_audit_py_executable_subscript_equals_remedy_locus_key(self):
        checked = set()
        for skill_name, profile in kit_shipping_profiles():
            with self.subTest(skill=skill_name):
                kit_dir = _kit_root_for(profile) / "assets" / "kit"
                source = (kit_dir / "tests" / "test_audit.py").read_text(encoding="utf-8")
                remedy_locus_key = profile["findings"]["remedy_locus_key"]
                pattern = rf'finding\["{re.escape(remedy_locus_key)}"\]'
                self.assertRegex(source, pattern)
                checked.add(skill_name)
        self.assertEqual(checked, {name for name, _ in kit_shipping_profiles()})

    def test_verification_notebook_executable_subscript_equals_claim_key(self):
        checked = set()
        for skill_name, profile in kit_shipping_profiles():
            with self.subTest(skill=skill_name):
                kit_dir = _kit_root_for(profile) / "assets" / "kit"
                source = (kit_dir / "nb" / "verification.ipynb").read_text(
                    encoding="utf-8")
                claim_key = profile["provenance"]["claim_key"]
                pattern = rf"p\['{re.escape(claim_key)}'\]"
                self.assertRegex(source, pattern)
                checked.add(skill_name)
        self.assertEqual(checked, {name for name, _ in kit_shipping_profiles()})


# --- D6: the campaign-proposal exclusion, three layers ---------------------
#
# L1's baseline is MEASURED at apply (task 0.4), never written into the
# design. Phase 0.4 measured 97 occurrences of `\bproposal\b`
# (case-insensitive) across `_core/implementation/engine/`, one file
# (`implementation_engine.py`). S9's `documents.label` conversion of
# `ARMS_UNDECLARED_CONSEQUENCE`'s "of a proposal" phrase into a profile read
# (`"of a {document}"`, formatted with `DOCUMENTS_LABEL`) is the ONE
# deliberate, recorded shrink this cut takes: the literal word "proposal"
# no longer appears in that constant's SOURCE TEXT (it is composed at
# runtime instead), dropping the count by exactly 1, to 96. Re-measured
# after landing every S3-S13 field: still 96, still 1 file. Any OTHER
# movement -- a rename campaign, an accidental sweep -- is refused here.
L1_BASELINE_AT_S0 = 97
L1_DELIBERATE_SHRINK = 3  # documents.label's ARMS_UNDECLARED_CONSEQUENCE conversion;
#: and `fix/skills-critical-review`, where compressing the four per-document
#: consumers' own comments dropped one prose mention of the first host by name
#: (2 total). `the-comparison-nobody-asked-for` (Unit 4b, design D12) removed
#: the bare local variable `proposal` -- `cmd_probe`'s own `wiring_proposal`
#: call site and its `"wiring": proposal,` return-dict line -- in favour of
#: the `PROBE_DRAFTS` dict comprehension's `drafts` variable, dropping 2 more
#: standalone occurrences of the word (`\bproposal\b` never matches inside
#: the identifier `wiring_proposal`, since there is no word boundary before
#: it -- only the bare variable name itself ever counted here).
#: upstream-sync 2026-09-15: re-measured over the merged engine -- 94
#: occurrences, a 3-shrink from S0. Upstream alone measured 97-4=93; the merge
#: lands at 94 because the fork's adopt-delta prose also spells the word
#: (fork pre-merge measured 96). Measured over the merged tree, never assumed.
#: A shrink in this count is the direction this pin wants -- it is recorded
#: rather than absorbed because an unexplained MOVE is the defect, in either
#: direction: a rename campaign looks exactly like this from outside.
#: `the-holder-each-skill-declares` (Phase 2, design D12): +2, deliberate and
#: recorded -- `position_state`'s and `cmd_position`'s docstrings, amended to
#: stop asserting the literal `AGREED.md` as fact, each name the actual skill
#: by its real name ("for `proposal-implementation`") as a qualified example.
#: Naming the real skill is not a rename campaign or an accidental sweep --
#: it is the opposite of what this lock guards against.
L1_HOLDER_DECLARES_GROWTH = 2
L1_EXPECTED_COUNT = (
    L1_BASELINE_AT_S0 - L1_DELIBERATE_SHRINK + L1_HOLDER_DECLARES_GROWTH)
L1_EXPECTED_FILES = ["implementation_engine.py"]

#: L2 (design.md D6): each of these must still resolve, spelled exactly --
#: catches a targeted rename that leaves L1's total count unchanged.
CAMPAIGN_PROPOSAL_SYMBOLS = (
    "proposalDigest", "GATE_PROPOSAL_", "_proposal_digest",
    "_verify_gate_proposal", "_gate_proposal_question",
    "_verify_optional_election", "cmd_propose", "_authorization_binding",
    "_verify_gate_authorization", "_campaign_identity",
    "_load_remote_execution_",
)


class CampaignProposalExclusionTests(unittest.TestCase):
    """D6: the pin alone is not enough (a targeted rename could leave the
    count unchanged) and the list alone is not enough (a wholesale
    rewording could drop the count while never touching a listed symbol).
    Three layers together."""

    def test_l1_residue_pin_equals_the_measured_s0_baseline_minus_its_one_recorded_shrink(self):
        source = ENGINE_FILE.read_text(encoding="utf-8")
        count = len(re.findall(r"\bproposal\b", source, re.IGNORECASE))
        files = sorted(
            path.name for path in _engine_files()
            if re.search(r"\bproposal\b", path.read_text(encoding="utf-8"),
                        re.IGNORECASE))
        self.assertEqual(
            count, L1_EXPECTED_COUNT,
            "the \\bproposal\\b occurrence count drifted from the measured S0 "
            f"baseline ({L1_BASELINE_AT_S0}) minus its one recorded, deliberate "
            f"shrink ({L1_DELIBERATE_SHRINK}, documents.label's "
            "ARMS_UNDECLARED_CONSEQUENCE conversion) -- any OTHER movement is a "
            "defect: a rename campaign, or an accidental sweep hitting the "
            "campaign-proposal meaning")
        self.assertEqual(files, L1_EXPECTED_FILES)

    def test_l2_named_exclusion_symbols_each_still_resolve(self):
        source = ENGINE_FILE.read_text(encoding="utf-8")
        missing = [symbol for symbol in CAMPAIGN_PROPOSAL_SYMBOLS
                  if symbol not in source]
        self.assertEqual(
            missing, [],
            f"the following campaign-proposal symbols no longer resolve, spelled "
            f"exactly, in the engine: {missing}")

    def test_l3_proposal_digest_is_still_an_authorization_binding_key(self):
        module = _import_engine_module()
        self.assertIn("proposalDigest", module._AUTHORIZATION_BINDING_KEYS)

    def test_wiring_proposal_third_sense_residue_is_covered_by_l1_not_l2(self):
        """Recorded (design.md D6): `wiring_proposal`/`_wiring_first_publication`
        spell `proposal` in a THIRD sense -- a draft suggestion, neither the
        managed document nor the campaign launch. In neither the L2 list nor
        renamed into `documents.label`; L1's occurrence pin is their only
        instrument, and this test exists so that fact is asserted rather than
        merely narrated."""
        source = ENGINE_FILE.read_text(encoding="utf-8")
        self.assertIn("wiring_proposal", source)
        self.assertNotIn("wiring_proposal", CAMPAIGN_PROPOSAL_SYMBOLS)


# --- M5: the derived-denylist layer (TS C-3) has now landed ----------------
#
# Landed above (`DerivedDenylistTests`, change `the-second-skill-the-seam-
# was-for`, slice A4, design.md D9): a second implementation profile
# (`experimental-implementation`) now exists on disk, so `buildDenylist`'s
# "others" set is non-empty and the lock is satisfiable rather than
# vacuous. This comment previously recorded why it was deferred; it is kept
# here, corrected, as the historical reason the deferral existed at all --
# never a `skipTest`, which would have moved the pinned `OK (skipped=6)`
# baseline this cut is not allowed to move.


# --- C3: the replacement lock, proven by reading, not by counting --------
#
# D10's single-document guarantee (Cut 3 slice A, `SingleDocumentGuarantee
# Tests`) is DELETED here (task 4.4, spec `experimental-implementation-
# skill` Requirement "A Two-Document Guarantee Is Proven By Reading, Not
# By Counting"): it proved only that `documents` stayed length 1 --
# necessary while `_extra_document_fidelity_status` fed every index the
# SAME four shared, document-count-invariant conditions (a `documents[1]`
# declared before this slice would have yielded a fidelity status that
# read green having measured nothing). Now that the fold genuinely reads
# each document's own claim-key scope (C2a) and its own citation pattern
# (C2b), a documents-count check alone is no longer the property that
# matters -- `TwoDocumentReadProvenTests` below replaces it, proving the
# per-document READ against the shipped skill's own two now-declared
# documents, and catching a reversion of that read even though the count
# stays two throughout.

SHIPPED_LAUNCHER = (
    SKILLS_DIR / "experimental-implementation" / "scripts" / "implementation_cli.py")
SHIPPED_PROFILE = SKILLS_DIR / "experimental-implementation" / "impl_profile.py"


class TwoDocumentReadProvenTests(unittest.TestCase):
    """Real subprocesses against the SHIPPED `experimental-implementation`
    launcher and its own profile (never a synthetic fixture profile, and
    never the shipped file mutated on disk) -- proves `documents[1]`'s own
    text genuinely drives its own `fidelityByDocument` entry, and that a
    documents-count check alone could not have told a correct fold from a
    reverted one."""

    PACKAGE = "TwoDocumentRead"
    DOC0_REVISION = "lock-doc0-r01.md"
    DOC1_OLD_REVISION = "lock-doc1-plan-v00.md"
    DOC1_NEW_REVISION = "lock-doc1-plan-v01.md"

    def setUp(self):
        self.doc0 = Path(tempfile.mkdtemp(prefix="lock-doc0-"))
        self.addCleanup(shutil.rmtree, self.doc0, ignore_errors=True)
        (self.doc0 / self.DOC0_REVISION).write_text(
            "## 1\nexperiments document text.\n", encoding="utf-8")

        self.doc1 = Path(tempfile.mkdtemp(prefix="lock-doc1-"))
        self.addCleanup(shutil.rmtree, self.doc1, ignore_errors=True)
        (self.doc1 / self.DOC1_OLD_REVISION).write_text(
            "the mathematical proposal, an older version.\n", encoding="utf-8")
        (self.doc1 / self.DOC1_NEW_REVISION).write_text(
            "the mathematical proposal, the current version.\n", encoding="utf-8")

    #: The forge and launcher `_build_box`/`_verify` run against: the shipped
    #: ones, unless a test swaps in a scratch forge (`scratch_forge.build`).
    forge = FORGE
    launcher = SHIPPED_LAUNCHER

    def _build_box(self, *, doc1_revision: str, suffix: str = ""):
        box = self.forge / "implementations" / f"_lock_read_{os.getpid()}_{id(self)}{suffix}"
        self.addCleanup(shutil.rmtree, box, ignore_errors=True)
        box.mkdir(parents=True)
        env = dict(os.environ)
        env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "lock-read"
        env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "lock-read@example.invalid"
        subprocess.run(["git", "init", "-q", str(box)], check=True, capture_output=True)

        (box / "src" / self.PACKAGE).mkdir(parents=True)
        (box / "src" / self.PACKAGE / "__init__.py").write_text(
            "__all__ = []\n", encoding="utf-8")
        (box / "src" / self.PACKAGE / "doc0_module.py").write_text(
            "__provenance__ = {\n"
            f"    'revision': {self.DOC0_REVISION!r}, 'sections': ['1'],\n"
            "    'experiments': ['T1'], 'invariants': [],\n"
            "}\n", encoding="utf-8")
        (box / "src" / self.PACKAGE / "doc1_module.py").write_text(
            "__provenance__ = {\n"
            f"    'revision': {doc1_revision!r}, 'sections': ['1'],\n"
            "    'equations': ['1'], 'invariants': [],\n"
            "}\n", encoding="utf-8")
        (box / self.PACKAGE).mkdir(parents=True)
        (box / "tests").mkdir(parents=True)

        subprocess.run(["git", "add", "-A"], cwd=box, env=env, check=True,
                       capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=box, env=env,
                       check=True, capture_output=True)
        return box

    def _verify(self, box: Path) -> dict:
        env = dict(os.environ)
        env.pop("IMPLEMENTATION_DOMAIN_PROFILE", None)
        if self.launcher != SHIPPED_LAUNCHER:
            # A scratch launcher has no profile beside it: name the shipped one.
            env["IMPLEMENTATION_DOMAIN_PROFILE"] = str(SHIPPED_PROFILE)
        env["IMPLEMENTATION_PROPOSALS"] = str(self.doc0)
        env["IMPLEMENTATION_PROPOSALS_1"] = str(self.doc1)
        proc = subprocess.run(
            [sys.executable, str(self.launcher), "verify", "--target", str(box),
             "--name", self.PACKAGE, "--revision", self.DOC0_REVISION],
            capture_output=True, text=True, cwd=self.forge, env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return json.loads(proc.stdout)

    def test_document_one_status_changes_independently_of_document_zero(self):
        """Spec scenario: document 1's own text/module changes while
        document 0 stays clean -- document 1's status alone reflects it."""
        stale_box = self._build_box(
            doc1_revision=self.DOC1_OLD_REVISION, suffix="_stale")
        stale = self._verify(stale_box)
        stale_by_doc = {e["label"]: e for e in stale["fidelity"]["fidelityByDocument"]}
        self.assertEqual(stale_by_doc["experiments"]["status"], "ok")
        self.assertEqual(stale_by_doc["proposal"]["status"], "drift")

        clean_box = self._build_box(
            doc1_revision=self.DOC1_NEW_REVISION, suffix="_clean")
        clean = self._verify(clean_box)
        clean_by_doc = {e["label"]: e for e in clean["fidelity"]["fidelityByDocument"]}
        self.assertEqual(clean_by_doc["experiments"]["status"], "ok")
        self.assertNotEqual(
            clean_by_doc["proposal"]["status"], "drift",
            "document 1's own status did not change when its own text did, "
            "with document 0 held constant -- the fold did not read the index")

    def test_a_reverted_fold_is_caught_even_with_two_documents_declared(self):
        """The count-only failure mode this lock replaces: revert the
        per-document derivation of the real engine source (Y5's own
        mutation), run from a scratch forge so the shipped engine is never
        rewritten (#92) -- `documents` still has two entries, but this lock
        still catches the reversion, because it demonstrates the READ, not
        the count."""
        engine = (SKILLS_DIR / "_core" / "implementation" / "engine"
                 / "implementation_engine.py")
        shipped_bytes = engine.read_bytes()
        shipped_mtime = engine.stat().st_mtime_ns

        def shipped_engine_untouched():
            # Registered first, so it runs after every other cleanup: a
            # byte-identical restore still moves the modification time.
            self.assertEqual(engine.read_bytes(), shipped_bytes,
                             "the shipped engine's bytes changed")
            self.assertEqual(engine.stat().st_mtime_ns, shipped_mtime,
                             "the shipped engine was rewritten on disk")
        self.addCleanup(shipped_engine_untouched)
        old = "doc_revision_n = document_names[index]"
        new = "doc_revision_n = revision"
        original = engine.read_text(encoding="utf-8")
        self.assertEqual(original.count(old), 1)
        self.assertEqual(original.count(new), 0)
        mutated = original.replace(old, new, 1)
        self.forge, self.launcher = scratch_forge.build(
            self, mutated, SHIPPED_LAUNCHER, prefix="lock-read-forge-")

        clean_box = self._build_box(
            doc1_revision=self.DOC1_NEW_REVISION, suffix="_mutated")
        clean = self._verify(clean_box)
        self.assertEqual(engine.read_bytes(), shipped_bytes,
                         "the mutation was written over the shipped engine")
        clean_by_doc = {e["label"]: e for e in clean["fidelity"]["fidelityByDocument"]}
        # Under the mutation, document 1's own current revision is
        # compared against document 0's `revision` instead of its own
        # discovered name -- reads `drift` even though document 1's text
        # never changed. This is exactly what the deleted count-only lock
        # (`SingleDocumentGuaranteeTests`) could never have caught: the
        # document count is still two throughout.
        self.assertEqual(
            clean_by_doc["proposal"]["status"], "drift",
            "the reverted fold should have reported document 1 as drift "
            "under this mutation, even with two documents still declared")


if __name__ == "__main__":
    unittest.main()
