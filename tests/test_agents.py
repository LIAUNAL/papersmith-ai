"""Every agent is bound to a skill, and every delegating skill to its agents.

The binding is TWO-WAY and both directions are held here, because either one
alone leaves something dead. An agent that names no skill has no rules; a skill
that names no agent has agents nobody invokes -- and an agent nobody invokes is
a file, not a boundary. That second failure already happened once in this
repository and the file was deleted rather than kept.


An agent definition is the one place the purpose reaches a session BEFORE
anything happens: its `description` is the first thing in context on every
invocation. The skill declares the north and every refusal carries it, so it
arrives when you are blocked and when you ask -- and an agent is what makes it
arrive at the start, which is where losing it is cheapest to prevent.

That only holds while the two agree. A description that drifts from the
declared arrival is a north nobody updated, and the agent would open every
session with a destination the skill no longer has. So the arrival is read out
of the skill and asserted in the description rather than proof-read.

Stdlib only, for the same reason `test_suite_collects.py` is: this has to
survive an environment missing everything else.
"""

import ast
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skill_text import stage_references  # noqa: E402  (path set above)

ROOT = Path(__file__).resolve().parent.parent
AGENTS = ROOT / ".claude" / "agents"
SKILLS = ROOT / "skills"

# Skills that declare no north at all -- neither a Python `OBJECTIVE_FLOW`
# nor a TypeScript `profile.ts` `objective`. Pinned by name, not discovered,
# so removing an entry (or a skill quietly growing a north) changes what the
# seal below expects to check, rather than changing what it silently skips.
NORTHLESS_SKILLS = {"skill-audit", "plausibility", "math-tutor"}

# The agents that run on the lighter model. `.claude/agents` is copied into a
# workspace, not rendered, so the `model:` line written in these sources IS the
# Claude projection; every other harness's translator drops it. Pinned by name:
# each one only reads (no tool below in `WRITE_TOOLS`) and holds no gate, and a
# writer, a judge or a gate holder keeps the session's model.
LIGHT_AGENTS = {"math-tutor", "insumos-observer", "style-sampler"}
LIGHT_MODEL = "sonnet"
WRITE_TOOLS = {"Write", "Edit", "Bash", "NotebookEdit"}

# The projections of `.claude/agents` for the harnesses with no cited per-agent
# model mechanism; `scripts/sync-repo-harness.py` writes them.
PROJECTED_AGENT_DIRS = (".pi/agents", ".opencode/agents", ".agents/agents")

# A single-line `arrival: "..."` or `stage: "..."` literal inside a
# TypeScript `objective` block. Anchored to the whole line so a token that
# merely CONTAINS the word `arrival` or `stage` elsewhere in the file (there
# is none today, but nothing guarantees that) cannot be mistaken for the
# declaration.
ARRIVAL_LINE = re.compile(r'^[ \t]*arrival:\s*"([^"]*)"\s*,?\s*$', re.MULTILINE)
STAGE_LINE = re.compile(r'^[ \t]*stage:\s*"([^"]*)"\s*,?\s*$', re.MULTILINE)
# The other two single-line literals a stage and an entrance are made of, read
# the same anchored way and for the same reason.
BEHIND_WHEN_LINE = re.compile(
    r'^[ \t]*behindWhen:\s*"([^"]*)"\s*,?\s*$', re.MULTILINE)
ARRIVES_AT_LINE = re.compile(
    r'^[ \t]*arrivesAt:\s*"([^"]*)"\s*,?\s*$', re.MULTILINE)

# A stage whose closing condition is a person's word rather than a byte
# anything can read. The profile says so itself, in the stage's own
# `behindWhen` -- so which stage this is gets DERIVED per skill, never listed
# here. `deliberated` is that stage in both deliberation domains today; a
# third domain naming it something else is checked the day it is written.
UNMEASURABLE = re.compile(
    r"nothing here measures it|the user said so", re.IGNORECASE)

# Prose that asserts work ARRIVES from somewhere else -- another skill's
# handoff, a pair of skills sharing a flow. An entrance is a declared field
# (`objective.entrances`), so an agent whose skill declares none and says one
# of these is claiming a shape its own north does not have. This is a
# lexicon and cannot be derived, so it is held live instead: every phrase
# below must still appear in the documents of a domain that DOES declare an
# entrance (`test_the_entrance_lexicon_is_still_live`), which is what stops a
# rewrite upstream from quietly turning this into five dead strings.
ENTRANCE_CLAIMS = (
    "pair of skills",
    "entrance from outside",
    "arrives through a handoff",
    "handed over by",
    "the implementation skill",
)

# Every `rule: "<id>"` literal `preservation-experimental.ts::violations`
# pushes, anchored the same way `ARRIVAL_LINE`/`STAGE_LINE` are: a syntactic
# shape, not a hand-kept list, so a rule added or renamed there is what moves
# this -- never a second place somebody has to remember to update. The module
# writes every violation it produces in this exact shape (change "the two
# declarations a plan owes" refactored the two cardinality checks onto it
# specifically so this pattern would see them).
RULE_ID_LITERAL = re.compile(r'rule:\s*"([a-z0-9-]+)"')


def flat(text: str) -> str:
    """Whitespace-flattened, because these files are hard-wrapped and "this
    pair of\\nskills" is the same sentence as "this pair of skills"."""
    return " ".join(text.split())


def frontmatter(path: Path) -> dict:
    """The agent's own header, parsed without a YAML dependency.

    Three keys, one line each, values optionally quoted. A parser is not what
    this file is for, and pulling in YAML would put it back inside the class of
    things `test_suite_collects.py` exists to detect.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    header = text.split("---\n", 2)[1]
    found = {}
    for line in header.splitlines():
        match = re.match(r'^(\w+):\s*"?(.*?)"?\s*$', line)
        if match:
            found[match.group(1)] = match.group(2)
    return found


def _python_objective(skill: str) -> dict | None:
    """This skill's own `OBJECTIVE_FLOW`, as `{"arrival": str, "stages": [str]}`,
    or None if no Python source under it declares one.

    Read out of the source with `ast` rather than by importing it: importing a
    skill's CLI pulls in whatever it depends on, and this file may not depend
    on anything.
    """
    for script in sorted((SKILLS / skill).rglob("*.py")):
        # `__pycache__` holds `.pyc` under a `.py`-shaped name on some layouts
        # and is never source anyway; a decode error there would fail this file
        # for a reason that has nothing to do with what it checks.
        if "__pycache__" in script.parts:
            continue
        try:
            source = script.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            # A kit template carries `{{TOKEN}}` placeholders and is not valid
            # Python until it is materialized. It is scaffolding, never a place
            # a north is declared, so failing on it would fail this file for a
            # reason that has nothing to do with what it checks.
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "OBJECTIVE_FLOW" not in names:
                continue
            flow = ast.literal_eval(node.value)
            return {
                "arrival": flow.get("arrival"),
                "stages": [stage.get("stage") for stage in flow.get("stages", [])],
            }
    return None


def _typescript_objective(skill: str) -> dict | None:
    """This skill's own `<skill>/profile.ts` `objective`, as
    `{"arrival": str, "stages": [str]}`, or None if the skill has no
    `profile.ts` at all.

    Read by an anchored regex over the two single-line literals the shape
    guarantees (see `domain-profile.ts`'s `objective.arrival` comment: "the
    Python seal reads it") -- never by executing TypeScript, since this
    file's whole contract is stdlib-only and must survive an environment
    missing node.

    Fail closed: a `profile.ts` that EXISTS but whose `arrival` or `stages`
    literal does not parse raises rather than returning None, so a change
    that breaks this regex's assumption fails loudly instead of reading as
    "no north declared".
    """
    profile = SKILLS / skill / "profile.ts"
    if not profile.is_file():
        return None
    source = profile.read_text(encoding="utf-8")
    arrival_match = ARRIVAL_LINE.search(source)
    stage_matches = STAGE_LINE.findall(source)
    if arrival_match is None or not stage_matches:
        raise AssertionError(
            f"{skill}/profile.ts exists but its `objective.arrival` and/or "
            f"`objective.stages[].stage` single-line literals could not be "
            f"parsed by the anchored regex -- fix the profile or this "
            f"regex, never read the failure as \"no north declared\"")
    return {"arrival": arrival_match.group(1), "stages": stage_matches}


def declared_objective(skill: str) -> dict | None:
    """This skill's own declared `{"arrival": str, "stages": [str]}`, tried
    in Python first and then TypeScript, or None if neither source declares
    one at all.

    Both present in the same skill is a mistake this raises on rather than
    silently picking a source: one skill, one north.
    """
    python_objective = _python_objective(skill)
    typescript_objective = _typescript_objective(skill)
    if python_objective is not None and typescript_objective is not None:
        raise AssertionError(
            f"{skill} declares OBJECTIVE_FLOW in Python AND an objective in "
            f"profile.ts -- one skill, one north; pick a source of truth")
    return python_objective if python_objective is not None else typescript_objective


def _python_flow(skill: str) -> dict | None:
    """The WHOLE `OBJECTIVE_FLOW` dict, not the two keys the seal above needs.

    A separate walk rather than a widened `_python_objective`: that one is what
    the arrival seal reads, and coverage added here has no business changing
    what an existing check sees. The duplication is deliberate and small.
    """
    for script in sorted((SKILLS / skill).rglob("*.py")):
        if "__pycache__" in script.parts:
            continue
        try:
            source = script.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if "OBJECTIVE_FLOW" not in [t.id for t in node.targets
                                        if isinstance(t, ast.Name)]:
                continue
            return ast.literal_eval(node.value)
    return None


def stage_conditions(skill: str) -> list[tuple[str, str]] | None:
    """`(stage, behindWhen)` for every stage of this skill's declared north,
    in declaration order, or None if it declares none at all.

    The TypeScript side zips the two anchored single-line literals rather than
    parsing an object: every stage declares exactly one of each, in that order,
    so a length mismatch means the shape moved and this raises instead of
    silently pairing a stage with the wrong condition.
    """
    flow = _python_flow(skill)
    if flow is not None:
        return [(stage.get("stage"), stage.get("behindWhen") or "")
                for stage in flow.get("stages", [])]

    profile = SKILLS / skill / "profile.ts"
    if not profile.is_file():
        return None
    source = profile.read_text(encoding="utf-8")
    stages = STAGE_LINE.findall(source)
    conditions = BEHIND_WHEN_LINE.findall(source)
    if not stages:
        return None
    if len(stages) != len(conditions):
        raise AssertionError(
            f"{skill}/profile.ts declares {len(stages)} `stage:` literals and "
            f"{len(conditions)} `behindWhen:` ones -- the anchored regexes can "
            f"no longer pair them, so fix the profile or these patterns, never "
            f"read the mismatch as \"no condition declared\"")
    return list(zip(stages, conditions))


def declared_entrances(skill: str) -> list[str] | None:
    """The stages this skill's north declares an outside entrance INTO, or
    None if the skill declares no north at all.

    An empty list is the meaningful answer here, and it is not the same as
    None: `experimental-deliberation` declares a north and deliberately
    declares no entrance ("declaring an entrance nothing produces would be a
    claim with no producer"), and that is exactly the state an agent may not
    contradict.
    """
    flow = _python_flow(skill)
    if flow is not None:
        return [entrance.get("arrivesAt")
                for entrance in flow.get("entrances", [])]

    profile = SKILLS / skill / "profile.ts"
    if not profile.is_file():
        return None
    source = profile.read_text(encoding="utf-8")
    if not STAGE_LINE.findall(source):
        return None
    arrives_at = ARRIVES_AT_LINE.findall(source)
    if re.search(r"^[ \t]*entrances:", source, re.MULTILINE) and not arrives_at:
        raise AssertionError(
            f"{skill}/profile.ts declares an `entrances:` field whose "
            f"`arrivesAt:` literals this anchored regex cannot read -- fix the "
            f"profile or this pattern, never read it as \"no entrance\"")
    return arrives_at


def bound_skill(path: Path) -> str:
    """The single skill this agent's body binds to, read by its `Skill:`
    path -- never by the agent's filename, which is the STRETCH's name and
    need not match any skill directory at all (`implementation-walk` is not
    a skill and never will be).

    `test_every_agent_names_a_skill_that_exists` already asserts this
    binding is present and real; this reuses the same regex rather than a
    weaker filename guess.
    """
    body = path.read_text(encoding="utf-8")
    named = re.findall(r"skills/([\w-]+)/SKILL\.md", body)
    assert named, f"{path.name} names no skill to load"
    return named[0]


class AgentBindingTests(unittest.TestCase):

    def agents(self):
        return sorted(AGENTS.glob("*.md")) if AGENTS.is_dir() else []

    def test_there_is_at_least_one_agent(self) -> None:
        self.assertTrue(self.agents(), "no agent definitions to hold")

    def test_every_agent_names_its_own_file(self) -> None:
        for path in self.agents():
            self.assertEqual(frontmatter(path).get("name"), path.stem, path.name)

    def test_every_agent_names_a_skill_that_exists(self) -> None:
        """By its PATH in the body, never by its filename.

        An agent is a STRETCH between two of the operator's gates, so its name
        is the stretch's and not the skill's -- `implementation-walk` is not a
        skill and never will be. Reading the binding out of the body is what
        lets one skill have several agents without any of them being named
        after it.
        """
        for path in self.agents():
            body = path.read_text(encoding="utf-8")
            named = re.findall(r"skills/([\w-]+)/SKILL\.md", body)
            self.assertTrue(named, f"{path.name} names no skill to load")
            for skill in named:
                self.assertTrue((SKILLS / skill / "SKILL.md").is_file(),
                                f"{path.name} names {skill}, which does not exist")

    def test_every_agent_a_skill_delegates_to_exists(self) -> None:
        """The other direction. A skill that names an agent it delegates a
        stretch to is what makes that agent reachable at all; without this, a
        renamed or deleted agent leaves a skill pointing at nothing and the
        stretch silently stops being delegated."""
        named = set()
        for skill in sorted(SKILLS.iterdir()):
            doc = skill / "SKILL.md"
            if not doc.is_file():
                continue
            for agent in re.findall(r"delegates to the `([\w-]+)` agent", 
                                    doc.read_text(encoding="utf-8")):
                named.add((skill.name, agent))
        self.assertTrue(named, "no skill delegates a stretch to any agent")
        for skill, agent in sorted(named):
            self.assertTrue((AGENTS / f"{agent}.md").is_file(),
                            f"{skill} delegates to `{agent}`, which does not exist")

    def test_every_agent_is_invoked_by_a_skill(self) -> None:
        """The half the first version of this file did not check, and two
        agents were written without it: it asked only that SOME skill delegate,
        which a single delegation satisfies while every other agent sits
        unreachable. An agent nobody invokes is a file, not a boundary -- the
        exact defect that had one deleted earlier the same day.
        """
        invoked = set()
        for skill in sorted(SKILLS.iterdir()):
            doc = skill / "SKILL.md"
            if doc.is_file():
                invoked.update(re.findall(r"delegates to the `([\w-]+)` agent",
                                          doc.read_text(encoding="utf-8")))
        orphans = sorted(path.stem for path in self.agents()
                         if path.stem not in invoked)
        self.assertEqual(orphans, [],
                         "these agents exist and no skill delegates to them, "
                         "so nothing reaches them")

    def test_every_agent_bound_to_a_split_skill_reads_the_current_stage(self) -> None:
        """A skill that moved its per-state sections into `references/` keeps
        one `Stage reference:` line per section. An agent told to load
        `SKILL.md` and nothing else would never see the section for the state
        it is in, so it has to be told where that section went."""
        bound = 0
        for path in self.agents():
            body = path.read_text(encoding="utf-8")
            for skill in sorted(set(re.findall(r"skills/([\w-]+)/SKILL\.md", body))):
                doc = SKILLS / skill / "SKILL.md"
                if not doc.is_file() or not stage_references(doc):
                    continue
                bound += 1
                with self.subTest(agent=path.stem, skill=skill):
                    text = " ".join(body.split())
                    self.assertIn("references/next-step-<nextStep>.md", text)
                    self.assertIn("`Stage reference:`", text)
        self.assertTrue(bound, "no agent binds a skill with stage references")

    def test_only_the_read_only_agents_name_a_model(self) -> None:
        """Omitted is the default and means the session's model. The one value
        an agent may name is the lighter one, and only a read-only agent may
        name it."""
        named = {}
        for path in self.agents():
            header = path.read_text(encoding="utf-8").split("---\n", 2)[1]
            models = re.findall(r"^model:[ \t]*(.*?)[ \t]*$", header, re.MULTILINE)
            if models:
                named[path.stem] = models
        self.assertEqual(named, {name: [LIGHT_MODEL] for name in LIGHT_AGENTS})
        for name in sorted(LIGHT_AGENTS):
            with self.subTest(agent=name):
                tools = {tool.strip() for tool in
                         frontmatter(AGENTS / f"{name}.md")["tools"].split(",")}
                self.assertEqual(tools & WRITE_TOOLS, set())

    def test_no_other_harness_projection_names_a_model(self) -> None:
        for directory in PROJECTED_AGENT_DIRS:
            projected = sorted((ROOT / directory).glob("*.md"))
            self.assertTrue(projected, f"{directory} holds no agent")
            for path in projected:
                with self.subTest(agent=f"{directory}/{path.name}"):
                    header = path.read_text(encoding="utf-8").split("---\n", 2)[1]
                    self.assertIsNone(
                        re.search(r"^(model|tier):", header, re.MULTILINE), header)

    def test_every_agent_states_its_tools(self) -> None:
        """An agent that declares none inherits everything, which is the
        capability restriction silently not applied."""
        for path in self.agents():
            self.assertTrue(frontmatter(path).get("tools"), path.name)

    def test_every_agent_names_both_ends_of_its_stretch(self) -> None:
        """An agent whose stretch has no ends is not a stretch, it is a job
        with a title. Two of these were written before the criterion existed
        and had neither."""
        for path in self.agents():
            body = path.read_text(encoding="utf-8")
            # Whitespace-tolerant on purpose: these files are hard-wrapped,
            # so "You\nend" is the same sentence as "You end" and a regex that
            # could not cross a line break failed one of them for its wrapping.
            flat = " ".join(body.split())
            self.assertIn("You begin", flat,
                          f"{path.name} never says where its stretch begins")
            self.assertRegex(flat, r"[Yy]ou end",
                             f"{path.name} never says where its stretch ends")

    def test_every_agent_declares_what_it_returns(self) -> None:
        """A subagent's report is not shown to the operator: it reaches the
        orchestrator, which relays what matters. So it is read twice and
        translated once, and anything the agent leaves out is gone. Without a
        declared shape the orchestrator receives whatever occurred to it."""
        for path in self.agents():
            body = path.read_text(encoding="utf-8")
            self.assertIn("## What you return", body, path.name)
            for field in ("`did`", "`stoppedAt`", "`state`", "`owed`"):
                self.assertIn(field, body,
                              f"{path.name} omits {field} from what it returns")

    def test_what_is_returned_is_measurable_and_not_a_conclusion(self) -> None:
        """The property that makes a report checkable rather than believable.
        "I verified it is correct" cannot be checked by anybody; "I ran X, it
        answered Y, I stopped at Z" can -- and the orchestrator's job is to
        verify against the repository rather than believe."""
        for path in self.agents():
            body = path.read_text(encoding="utf-8")
            self.assertIn("never conclusions", body, path.name)
            self.assertIn("measured again", body, path.name)

    def test_every_delegated_stretch_names_what_to_measure_first(self) -> None:
        """A precondition read before delegating, not discovered inside.

        Each agent also refuses from within when it finds itself before its own
        start, and that is the backstop rather than the rule: discovering it
        there costs a whole round trip to learn something that was measurable
        before leaving.
        """
        delegating = [skill for skill in sorted(SKILLS.iterdir())
                      if (skill / "SKILL.md").is_file()
                      and "delegates to the `" in (skill / "SKILL.md").read_text(
                          encoding="utf-8")]
        self.assertTrue(delegating)
        for skill in delegating:
            doc = (skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("Measure this before delegating", doc,
                          f"{skill.name} delegates a stretch and names no "
                          f"precondition to read first")

    def test_a_description_carries_the_arrival_its_skill_declares(self) -> None:
        """The seal.

        Bound by the body `Skill:` path, never the filename -- the earlier
        version checked `declared_arrival(path.stem)`, which only matches a
        skill directory that happens to share the agent's own name, and
        `paper-ingestion` was the sole agent where that held. Coverage was
        1 of 5 and `assertGreater(checked, 0)` passed on that one survivor.

        The property itself is FALSE for an agent whose stretch stops
        short: `implementation-build` ends at "the findings report", not at
        `proposal-implementation`'s arrival, and forcing it to carry that
        arrival would make a correct description lie. So every agent bound
        to a north-declaring skill must name its own end in frontmatter --
        `stretch: terminal` (its description carries the skill's `arrival`
        verbatim) or `stretch: <stage>` (a stage that skill actually
        declares) -- and coverage is an EQUALITY against the derived set of
        agents bound to a north-declaring skill, not `assertGreater(..., 0)`.
        """
        expected = {path.stem for path in self.agents()
                    if bound_skill(path) not in NORTHLESS_SKILLS}
        if not expected:
            self.skipTest("no agent is bound to a skill that declares a "
                           "north; nothing for this seal to check")

        checked = set()
        for path in self.agents():
            skill = bound_skill(path)
            if skill in NORTHLESS_SKILLS:
                self.assertIsNone(declared_objective(skill),
                                  f"{skill} is listed in NORTHLESS_SKILLS "
                                  f"but declares an objective -- remove it "
                                  f"from the map")
                continue

            objective = declared_objective(skill)
            self.assertIsNotNone(
                objective,
                f"{path.name} is bound to {skill}, which is not in "
                f"NORTHLESS_SKILLS, but declares no OBJECTIVE_FLOW and no "
                f"profile.ts objective")
            checked.add(path.stem)

            stretch = frontmatter(path).get("stretch")
            self.assertTrue(stretch,
                            f"{path.name} is bound to {skill}, which "
                            f"declares a north, but names no `stretch:`")
            description = frontmatter(path).get("description", "")
            if stretch == "terminal":
                self.assertIn(objective["arrival"], description,
                              f"{path.name}'s description does not carry "
                              f"the arrival its own skill declares")
            else:
                self.assertIn(stretch, objective["stages"],
                              f"{path.name} declares `stretch: {stretch}`, "
                              f"which is not one of {skill}'s declared "
                              f"stages {objective['stages']}")

        self.assertEqual(checked, expected,
                         "the seal's coverage drifted from every agent "
                         "bound to a north-declaring skill")

    def test_every_agent_carries_the_shared_role_discipline(self) -> None:
        """The role discipline is COPIED into every agent, never extracted --
        a decision already taken, because a shared fragment could only be
        asserted by REFERENCE, and whether an agent actually loaded it is
        unmeasurable. This asserts the whole named tuple lives in each
        agent's own bytes.

        Most of the tuple overlaps tests already above
        (`test_every_agent_declares_what_it_returns`,
        `test_what_is_returned_is_measurable_and_not_a_conclusion`) and is
        re-asserted here as one named set, not claimed as new. Three items
        are new: the `## Measure before you assert` heading, the corrected
        sentence about which agents carry an arrival at all (the false
        universal claim the seal above used to make silently, by checking
        only one agent), and the coverage equality below.
        """
        fragments = (
            "## What you return",
            "`did`",
            "`stoppedAt`",
            "`state`",
            "`owed`",
            "never conclusions",
            "measured again",
            "## Measure before you assert",
            "Not every agent's description carries its bound skill's arrival",
        )
        agents = self.agents()
        checked = 0
        for path in agents:
            body = path.read_text(encoding="utf-8")
            for fragment in fragments:
                self.assertIn(fragment, body,
                              f"{path.name} is missing the shared role "
                              f"discipline fragment {fragment!r}")
            checked += 1
        self.assertEqual(checked, len(agents),
                         "not every agent file was checked for the shared "
                         "role discipline")

    def test_an_unmeasurable_stage_is_never_delegated(self) -> None:
        """The stage no agent may be handed, and which agents must say so.

        WHICH stage that is comes out of the profile, never this file: the one
        whose own `behindWhen` says the user said so and nothing here measures
        it. An agent able to close it would be approving its own proposal --
        the failure the whole north exists to name rather than paper over.

        Two layers, both derived:

        * EVERY agent bound to a skill whose north declares such a stage must
          NAME that stage in its own bytes. An agent that never mentions it has
          not positioned itself with respect to it at all.
        * Every such agent whose own `stretch:` is `terminal` must additionally
          DISCLAIM it. A `stretch: <stage>` agent already ends at a named
          earlier stage, so its boundary excludes the unmeasurable one
          structurally; a terminal agent's stretch runs to the arrival, and it
          is the one that could plausibly absorb the stage on its own word.
          `experimental-validation` is the non-terminal case today: it does say
          the same thing ("that is why this stretch, unlike `deliberated`, may
          be delegated at all"), but in wording only a regex loose enough to
          accept anything would match -- so it is held to the naming layer and
          not the disclaimer one, and that limit is stated rather than hidden.
        """
        naming, disclaiming = {}, {}
        for path in self.agents():
            skill = bound_skill(path)
            if skill in NORTHLESS_SKILLS:
                continue
            conditions = stage_conditions(skill)
            self.assertIsNotNone(
                conditions,
                f"{path.name} is bound to {skill}, which is not in "
                f"NORTHLESS_SKILLS but declares no stages to read")
            unmeasurable = [stage for stage, when in conditions
                            if UNMEASURABLE.search(when)]
            if not unmeasurable:
                continue
            naming[path] = unmeasurable
            if frontmatter(path).get("stretch") == "terminal":
                disclaiming[path] = unmeasurable

        if not naming:
            self.skipTest("no agent is bound to a skill whose north declares "
                          "a stage nothing measures; there is no stage here "
                          "that may not be delegated")

        for path, stages in sorted(naming.items()):
            body = flat(path.read_text(encoding="utf-8"))
            for stage in stages:
                self.assertIn(
                    f"`{stage}`", body,
                    f"{path.name} is bound to a north whose `{stage}` stage "
                    f"nothing measures, and never names it")

        self.assertTrue(
            disclaiming,
            "no agent bound to such a north declares `stretch: terminal`, so "
            "the disclaimer below was never asserted against anything")
        for path, stages in sorted(disclaiming.items()):
            body = flat(path.read_text(encoding="utf-8"))
            description = frontmatter(path).get("description", "")
            for stage in stages:
                self.assertIn(
                    f"The `{stage}` stage is not yours", body,
                    f"{path.name} runs to its skill's arrival and never says "
                    f"the `{stage}` stage is not its own")
            self.assertIn(
                "nothing measures it", body,
                f"{path.name} disclaims the stage without giving the reason "
                f"its own north gives -- that nothing measures it")
            self.assertIn(
                "approving its own", body,
                f"{path.name} does not say what closing that stage itself "
                f"would amount to")
            self.assertIn(
                "is not in this stretch and may not be", description,
                f"{path.name}'s description -- the first thing in context on "
                f"every invocation -- does not exclude the deliberation from "
                f"its stretch")
            self.assertIn(
                "nothing but the operator closes that", description,
                f"{path.name}'s description does not say who closes it "
                f"instead")

    def test_an_agent_never_claims_an_entrance_its_skill_does_not_declare(
            self) -> None:
        """A domain-bound line adapted rather than copied.

        `experimental-publish` was authored from `deliberation-publish` as a
        template. That one says "how this pair of skills loses work", which
        names `proposal-deliberation`'s declared entrance -- a finding handed
        over by the implementation skill. `experimental-deliberation` declares
        no entrance at all, and says so in the profile: "declaring an entrance
        nothing produces would be a claim with no producer". So the copy would
        have been a false statement about the domain, and nothing read it.

        The scope is derived rather than the phrase hardcoded: whether a
        domain HAS an entrance is a declared field, so the same check catches
        the next line copied across from a domain that has one, not just this
        phrase. The lexicon it matches with is held live separately.
        """
        checked, expected = set(), set()
        for path in self.agents():
            skill = bound_skill(path)
            if skill in NORTHLESS_SKILLS:
                continue
            entrances = declared_entrances(skill)
            self.assertIsNotNone(
                entrances,
                f"{path.name} is bound to {skill}, which is not in "
                f"NORTHLESS_SKILLS but declares no north to read an entrance "
                f"out of")
            if entrances:
                continue
            expected.add(path.stem)
            body = flat(path.read_text(encoding="utf-8"))
            for phrase in ENTRANCE_CLAIMS:
                self.assertNotIn(
                    phrase, body,
                    f"{path.name} is bound to {skill}, whose north declares "
                    f"no entrance, and its own bytes say {phrase!r} -- a "
                    f"shape carried over from a domain that has one")
            checked.add(path.stem)

        if not expected:
            self.skipTest("every agent is bound to a skill declaring an "
                          "entrance; there is no domain here that could be "
                          "given one it does not have")
        self.assertEqual(
            checked, expected,
            "an agent bound to an entrance-less north went unchecked")

    def test_the_entrance_lexicon_is_still_live(self) -> None:
        """`ENTRANCE_CLAIMS` cannot be derived, so it is held against reality.

        Every phrase in it must still appear somewhere in a domain that
        genuinely declares an entrance -- its doctrine, its profile, or an
        agent bound to it. A phrase that has vanished from there is a string
        that can no longer catch anything, and the check above would go on
        passing while matching nothing. A rewrite upstream reddens this and
        the lexicon gets re-derived from what the prose now says.
        """
        documents = []
        for skill_dir in sorted(SKILLS.iterdir()):
            if not (skill_dir / "SKILL.md").is_file():
                continue
            if not declared_entrances(skill_dir.name):
                continue
            documents.append(skill_dir / "SKILL.md")
            documents.append(skill_dir / "profile.ts")
            documents.extend(path for path in self.agents()
                             if bound_skill(path) == skill_dir.name)
        self.assertTrue(
            documents,
            "no domain declares an entrance at all, so every phrase in "
            "ENTRANCE_CLAIMS is unfalsifiable and the check that uses them "
            "proves nothing")
        corpus = " ".join(flat(document.read_text(encoding="utf-8"))
                          for document in documents if document.is_file())
        for phrase in ENTRANCE_CLAIMS:
            self.assertIn(
                phrase, corpus,
                f"{phrase!r} no longer appears in any domain that declares an "
                f"entrance -- it is a dead string, and the agents checked "
                f"against it are no longer being checked for anything")

    def test_the_validation_agents_rule_enumeration_derives_from_the_module(
            self) -> None:
        """The class of defect this change found, closed for good.

        `experimental-validation.md` (`stretch: validated`) once enumerated
        the rules that confirm its stage closed as a hand-kept prose list --
        exactly the shape that drifted the day this change found it: two new
        rules landed in `preservation-experimental.ts::violations` and the
        agent kept reporting the stage done while both blocked publication.

        This derives the expected set from the module itself (every `rule:
        "<id>"` literal `violations()` can push -- `RULE_ID_LITERAL`, read the
        same anchored way as the north's own single-line literals above) and
        requires each one to be MENTIONED, by its exact backtick-quoted id,
        somewhere in the agent's body.

        Deliberately NOT a check that every rule must be described as
        CONFIRMING the stage: `report-table-fabricated-value` is a genuine,
        permanent exclusion (a composition property no search closes), named
        in its own "not this stretch" sentence rather than the confirming
        list -- and a naive "every rule is in the confirming list" check
        would be WRONG, going red on that correct omission. Presence alone,
        in either an inclusion or an explicit exclusion, is what this module's
        own curation is built to need: a rule this file has never seen before
        must be classified one way or the other before this passes again.
        """
        module = (SKILLS / "experimental-deliberation" /
                   "preservation-experimental.ts")
        self.assertTrue(module.is_file(), f"{module} does not exist")
        source = module.read_text(encoding="utf-8")
        declared_rules = sorted(set(RULE_ID_LITERAL.findall(source)))
        self.assertGreaterEqual(
            len(declared_rules), 10,
            f"expected at least 10 rule ids in {module.name}, found "
            f"{len(declared_rules)}: {declared_rules} -- this check would "
            f"otherwise be vacuous")

        agent = AGENTS / "experimental-validation.md"
        self.assertTrue(agent.is_file(), f"{agent} does not exist")
        body = agent.read_text(encoding="utf-8")
        unclassified = [rule_id for rule_id in declared_rules
                        if f"`{rule_id}`" not in body]
        self.assertEqual(
            unclassified, [],
            f"{agent.name} never mentions {unclassified} by its exact "
            f"backtick-quoted id -- classify each one, either among the "
            f"rules that confirm the `validated` stage closed, or in an "
            f"explicit sentence naming it as not this stretch's concern")
