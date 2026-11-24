"""The forge's own gate, derived on both sides rather than restated.

`openspec/config.yaml` names the command that has to pass before any apply or
verify slice may call itself done. That command is prose in a YAML file:
nothing executes it at authoring time, so a discovery pattern that reaches one
suite out of six reads exactly like a pattern that reaches all six, and an
interpreter that cannot import what the suites import reads exactly like one
that can. Both failures are silent, and both were real here.

Every lock below derives its two halves instead of asserting a literal. The
suites are whatever `tests/` holds today; the pattern is whatever the
configured command carries today; the interpreter is driven as a process and
asked to import the module that decides the answer. A restated command string
would have to be edited alongside the defect it was meant to catch, which is
the same silence one indirection later.
"""

import ast
import fnmatch
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

FORGE = Path(__file__).resolve().parent.parent
CONFIG = FORGE / "openspec" / "config.yaml"
MANIFEST = FORGE / "package.json"
SUITES = FORGE / "tests"

#: Every place the configuration states the gate. Three sites, one gate: apply
#: names it, verify names it, and the testing block records it a third time. A
#: narrowing repaired at one site leaves the other two reading green.
GATE_SITES = (("rules", "apply", "test_command"),
              ("rules", "verify", "test_command"),
              ("testing", "runner", "command"))

#: The directory holding the module whose import decides which interpreters can
#: run this repository at all. It evaluates a `tuple[int, int] | None` alias at
#: module scope, so an interpreter older than 3.10 raises `TypeError` on the
#: import line rather than failing some later assertion. Naming the module
#: keeps the interpreter lock a measurement instead of a version number
#: somebody chose.
DECIDING_SCRIPTS = FORGE / "skills" / "remote-execution" / "scripts"

#: Every tracked `.py` this guard scans for third-party imports: the
#: suites, the source distribution, every skill's own `scripts/` tree, and
#: every engine shelf under `skills/_core/` -- any depth on all four, since
#: git pathspec `*` crosses `/`. `*.py` on every segment, never a bare
#: directory name -- `src/` and `skills/*/assets/` also carry non-Python
#: tracked files (templates, notebooks), and asking `ast` to parse those
#: would be asking the wrong question, not a merely slower one.
#:
#: The shelf row is the one that was missing, and what the gap cost was
#: measured: `skills/_core/command_center/server.py` imports `fastapi` at
#: module scope, and while that file sat outside every pathspec the derived
#: required-import set never held it. The failure that followed was real but
#: reported as its own symptom -- `test_suite_collects` naming a module that
#: did not load -- which is the reading this guard exists to replace with the
#: cause. The shelves are `_`-prefixed engine trees that reach a workspace
#: through the same `skills` kit entry every skill does, which is why their
#: Python belongs here rather than in a resolution step of its own.
IMPORT_SCOPE_PATHSPECS = (
    "tests/*.py",
    "src/*.py",
    "skills/*/scripts/*.py",
    "skills/_core/*/*.py",
)

#: The tracked asset files a skill's own scripts stage and later execute as
#: subprocesses -- resolved by basename against the `_ASSET`-suffixed
#: constants those scripts declare, never hand-listed. See
#: `resolved_asset_files()`.
ASSET_PATHSPEC = "skills/*/assets/*"

#: A module-level assignment whose target name ends this way declares an
#: asset basename: `adapters/colab.py`'s `LAUNCH_ASSET`, `EXECUTOR_ASSET`,
#: `READ_STATE_ASSET`, and `jobfolder.py`'s `DEFAULT_BOOTSTRAP_ASSET`,
#: `DEFAULT_INVOKE_ASSET`. `nbformat` and `nbclient` live only inside two
#: of the files this resolves -- `assets/colab/executor.py` and
#: `assets/runner_invoke.py` -- imported INSIDE a function rather than at
#: module scope, so a scan that never reached these two files would never
#: have found either.
ASSET_CONSTANT_SUFFIX = "_ASSET"


def tracked_files(*pathspecs):
    """`git ls-files`, never `Path.rglob`. Measured trap: `rglob` walks
    into a skill's own vendored `.venv` (a real environment on disk under
    `skills/paper-ingestion/.venv/`) and harvests every optional import
    inside a third-party distribution as though this repository required
    it. `git ls-files` only ever lists what this repository actually
    versions. Sibling precedent:
    `tests/test_kaggle_accounts.py::AccountVocabularyLeakTests._tracked_skill_scripts`.
    """
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", *pathspecs],
        cwd=str(FORGE), capture_output=True, text=True, check=True,
    )
    return sorted(FORGE / name for name in result.stdout.split("\0") if name)


def _asset_constant_basenames(paths):
    """Every basename assigned to an `_ASSET`-suffixed name in any of
    `paths`, parsed with `ast` rather than grepped so a multi-line import
    or an f-string mentioning the same word cannot be mistaken for a
    declaration. Handles both shapes actually used: a bare string literal
    (`LAUNCH_ASSET = "launch.py"`) and a path built with `/`
    (`DEFAULT_BOOTSTRAP_ASSET = ASSETS_DIR / "runner_bootstrap.py"`).
    """
    basenames = set()
    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not (isinstance(target, ast.Name)
                        and target.id.endswith(ASSET_CONSTANT_SUFFIX)):
                    continue
                value = node.value
                literal = None
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    literal = value.value
                elif (isinstance(value, ast.BinOp) and isinstance(value.op, ast.Div)
                      and isinstance(value.right, ast.Constant)
                      and isinstance(value.right.value, str)):
                    literal = value.right.value
                if literal:
                    basenames.add(literal)
    return basenames


def resolved_asset_files():
    """The tracked `skills/*/assets/*` files that `IMPORT_SCOPE_PATHSPECS`'
    own scripts actually name via an `_ASSET` constant, resolved by
    basename. Kept separate from `import_scan_scope()` so a test can assert
    this derivation reaches something on its own, before it is folded into
    the larger scope -- a broken parse here would silently shrink that
    scope back to the exact blind spot this guard exists to close.
    """
    basenames = _asset_constant_basenames(tracked_files(*IMPORT_SCOPE_PATHSPECS))
    by_basename = {}
    for path in tracked_files(ASSET_PATHSPEC):
        by_basename.setdefault(path.name, []).append(path)
    resolved = set()
    for name in basenames:
        resolved.update(by_basename.get(name, []))
    return resolved


def import_scan_scope():
    """Every file this guard scans for third-party imports."""
    return sorted(set(tracked_files(*IMPORT_SCOPE_PATHSPECS)) | resolved_asset_files())


def local_module_names():
    """Every name a suite or script can import without leaving this
    repository: the stem of every tracked `.py` file (these trees are put
    on `sys.path` by the suites themselves), plus the directory name of
    every tracked `__init__.py`. Derived from the FULL tracked `.py`
    universe (`git ls-files -z -- '*.py'`), not merely the scan scope --
    measured at 204 files -- because a name can be local without living
    inside the scanned trees.

    One deliberate exception: `papersmith` is never treated as local, even
    though `src/papersmith/__init__.py` would otherwise put it here.
    `src/papersmith/` is a real distribution `scripts/setup_env.py`
    installs editable, and its absence from the environment was exactly
    one of the four gaps measured the day this guard was written --
    excluding it here would exclude the one signal that catches that gap.
    """
    names = set()
    for path in tracked_files("*.py"):
        if path.stem == "__init__":
            names.add(path.parent.name)
        else:
            names.add(path.stem)
    names.discard("papersmith")
    return names


def _try_is_import_guard(node):
    """True when this `ast.Try` declares at least one handler naming
    `ImportError`, `ModuleNotFoundError`, or `Exception`, or a bare
    `except:` -- the shape that means "the author declared this import
    optional," as opposed to an import that happens to sit inside a `try`
    guarding something else entirely.
    """
    for handler in node.handlers:
        if handler.type is None:
            return True
        if _handler_type_names(handler.type) & {
            "ImportError", "ModuleNotFoundError", "Exception",
        }:
            return True
    return False


def _handler_type_names(expr):
    if isinstance(expr, ast.Tuple):
        names = set()
        for elt in expr.elts:
            names |= _handler_type_names(elt)
        return names
    if isinstance(expr, ast.Name):
        return {expr.id}
    if isinstance(expr, ast.Attribute):
        return {expr.attr}
    return set()


def _guarded_import_ids(tree):
    """The `id()` of every `Import`/`ImportFrom` node lexically inside the
    BODY of a `try` that guards against import failure -- never a handler,
    `else`, or `finally` clause, none of which is what "guarded against
    ImportError" means. A `try` nested inside a guarded body stays guarded,
    because `ast.walk` recurses into it; a `try` living in a handler,
    `else`, or `finally` does not, because those are never walked here.
    """
    guarded = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and _try_is_import_guard(node):
            for stmt in node.body:
                for sub in ast.walk(stmt):
                    if isinstance(sub, (ast.Import, ast.ImportFrom)):
                        guarded.add(id(sub))
    return guarded


def file_top_level_imports(path):
    """Yield `(name, guarded)` for every top-level package this file
    imports, walked at ALL depths (`ast.walk`, never only the module body)
    so an import made INSIDE a function -- `nbformat`/`nbclient` in
    `assets/colab/executor.py`, deliberately imported late so importing the
    module never requires a kernel -- is still found. `ImportFrom` only
    counts when `level == 0`: a relative import can only ever name a module
    already inside this repository.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return
    guarded_ids = _guarded_import_ids(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0], id(node) in guarded_ids
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                yield node.module.split(".")[0], id(node) in guarded_ids


def _pip_skippable_prefixes():
    """The requirements of `env/ingestion.txt`, the pip layer
    `scripts/setup_env.py install --no-ingestion` skips, read from that file
    rather than restated, normalized to the `-`-delimited prefix
    (`marker-pdf==2.0.0` -> `marker`). This is a heuristic tied to that one
    declaration, not a hand-picked exception: `--no-ingestion` skips exactly
    that file, so requiring one of its entries here would turn a documented,
    supported install into a red gate. Measured confirmation: `marker` is
    ABSENT from the `.venv` that ran the suites, and no suite failure
    involved it.
    """
    ingestion = FORGE / "env" / "ingestion.txt"
    prefixes = set()
    for line in ingestion.read_text(encoding="utf-8").splitlines():
        entry = line.split("#")[0].strip()
        if not entry:
            continue
        normalized = re.split(r"[=<>!~\[;]", entry, maxsplit=1)[0].strip()
        prefixes.add(normalized.split("-")[0].lower())
    return prefixes


def required_third_party_imports():
    """`{name: [file, ...]}` for every third-party import this guard's
    scan scope requires -- the files list is what makes a later failure
    name a culprit instead of a bare name nobody can act on.

    A name is required when at least one occurrence anywhere in scope is
    UNGUARDED: an import guarded in one file (declared optional there) and
    unguarded in another (a hard requirement there) is still required,
    because the unguarded occurrence is what proves it. Excluded, in this
    order: the standard library (`sys.stdlib_module_names`), every local
    module name (`local_module_names()`, `papersmith` deliberately
    excepted), and any name `env/ingestion.txt` (the layer
    `--no-ingestion` skips) declares skippable (`_pip_skippable_prefixes()`).
    """
    stdlib = set(sys.stdlib_module_names)
    local = local_module_names()
    skippable = _pip_skippable_prefixes()

    occurrences = {}
    for path in import_scan_scope():
        for name, guarded in file_top_level_imports(path):
            if not guarded:
                occurrences.setdefault(name, []).append(path)

    return {
        name: sorted(files) for name, files in occurrences.items()
        if name not in stdlib and name not in local and name.lower() not in skippable
    }


def configuration():
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def at(document, path):
    node = document
    for key in path:
        if not isinstance(node, dict) or key not in node:
            raise AssertionError(
                f"openspec/config.yaml has no {'.'.join(path)}")
        node = node[key]
    return node


def stated_gate():
    return at(configuration(), GATE_SITES[0])


def gate_scripts(manifest):
    """The Node half no longer names `unittest discover` directly: since
    commit `5c63644` the gate delegates to `npm run test:all`, whose
    `package.json` scripts split Node (`test:node`) and Python (`test:py`)
    halves that this doctrine now derives instead of the old two-stage
    `&&` spelling."""
    scripts = manifest["scripts"]
    required = ("test", "test:all", "test:node", "test:py")
    missing = [name for name in required if not scripts.get(name)]
    if missing:
        raise AssertionError(
            f"package.json lacks test scripts this gate derives from: {missing}")
    return scripts


def gate_command(manifest, config):
    stated = config["rules"]["apply"]["test_command"]
    matched = re.fullmatch(r"npm run ([\w:]+)", stated.strip())
    if not matched or matched.group(1) != "test:all":
        raise AssertionError(
            f"the gate's command {stated!r} does not delegate to "
            "package.json's test:all script, so nothing holds the Python "
            "half of the gate to the interpreter pytest runs under")
    return stated, manifest["scripts"]["test:all"]


def provisioned_bin_directory():
    """Where `scripts/setup_env.py` puts the environment's programs, asked
    of that script rather than restated here.

    Two declarations decide whether the gate can run at all -- the one that
    BUILDS the environment and the one that NAMES its interpreter -- and
    they lived in different files with nothing between them. They
    disagreed: the provisioning script built a micromamba environment under
    `.micromamba/`, while the lock below looked for a `.venv/` that no
    script in this repository creates. Everything passed anyway, on an
    environment somebody had made by hand. Deriving the directory from the
    script that creates it is what makes the disagreement visible instead
    of load-bearing.
    """
    spec = importlib.util.spec_from_file_location(
        "papersmith_setup_env", FORGE / "scripts" / "setup_env.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return (module.MAMBA_ROOT / "envs" / module.ENV_NAME / "bin").relative_to(FORGE)


def pytest_stage(manifest):
    """The gate's Python half: `test:py`'s pytest stage, matched by the
    BASENAME of the program it names rather than by the whole token.

    An earlier spelling required the token to equal `pytest` exactly, which
    forced the gate to name a bare console script -- and a bare name is
    resolved by the caller's `PATH`, which is the one thing about the
    caller's machine this repository cannot state. Measured here: `pytest`
    resolved to a Python 3.9 user-site install that sits ahead of the
    provisioned environment and cannot import `DECIDING_SCRIPTS` at all, so
    the gate was configured against an interpreter that could never run the
    suites. Matching the basename lets `test:py` name a path, which is what
    `test_the_gate_names_the_provisioned_interpreter` below then holds to
    what `scripts/setup_env.py` actually provisions.
    """
    stages = [stage.strip() for stage in manifest["scripts"]["test:py"].split("&&")]
    pytest_stages = [
        stage for stage in stages
        if Path(stage.split()[0]).name in ("pytest", "pytest.exe")
    ]
    if len(pytest_stages) != 1:
        raise AssertionError(
            f"package.json's test:py script names {len(pytest_stages)} pytest "
            "stages, not one")
    return pytest_stages[0]


def node_stage(manifest):
    """The stage of the `test:all` gate that is not the pytest half: the
    npm script that packages the Node half (the two sides delegate rather
    than restate, so the scripts themselves are the roster)."""
    scripts = manifest["scripts"]
    stages = [stage.strip() for stage in scripts["test:all"].split("&&")]
    node_stages = [stage for stage in stages if stage.startswith("npm run test:node")]
    if len(node_stages) != 1:
        raise AssertionError(
            f"package.json's test:all script delegates {len(node_stages)} "
            "times to test:node, not once, so the Node half is not a single "
            "named stage")
    return node_stages[0]


def discovery_pattern(stated_command, manifest):
    """The suite-name pattern pytest reaches through, read from
    `pyproject.toml`'s pytest config (pytest's own loader runs the gate)."""
    import tomllib
    pyproject = (FORGE / "pyproject.toml").read_bytes()
    return tomllib.loads(pyproject.decode())["tool"]["pytest"]["ini_options"]["testpaths"]


def suites_on_disk():
    return sorted(path.name for path in SUITES.glob("test_*.py"))


class GateSiteAgreementTests(unittest.TestCase):
    """One gate, stated three times, and the three have to be one string."""

    def test_every_site_states_the_same_command(self):
        document = configuration()
        stated = {".".join(path): at(document, path) for path in GATE_SITES}
        self.assertEqual(
            len(set(stated.values())), 1,
            "the configuration states more than one gate, so a slice told to "
            f"run one of them runs something other than another does: {stated}")


class GateReachesEverySuiteTests(unittest.TestCase):
    """The configured pattern has to reach every suite on disk.

    Derived from the directory, never from a list. A suite added tomorrow is
    covered the day it lands, and a pattern narrowed tomorrow fails here
    rather than passing quietly for the next four months.
    """

    def setUp(self):
        self.config = configuration()
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.stated, self.test_all = gate_command(self.manifest, self.config)
        self.found = suites_on_disk()
        self.assertGreater(
            len(self.found), 1,
            "tests/ holds one suite or none, so a pattern reaching exactly "
            "one of them could not be told apart from a pattern reaching all")

    def test_pytests_own_testpaths_reach_every_suite(self):
        """The pattern read by `fnmatch` above, read again from pytest's own
        configuration, which is the loader the gate actually uses.

        `fnmatch` is this file's reading; `pyproject.toml`'s `testpaths` is
        what pytest runs the gate against. Compared, not restated: a narrowed
        `testpaths` fails here, and an unchanged pattern passes."""
        import tomllib
        pyproject = (FORGE / "pyproject.toml").read_bytes()
        testpaths = tomllib.loads(pyproject.decode())["tool"]["pytest"]["ini_options"]["testpaths"]
        self.assertEqual(
            testpaths, ["tests"],
            f"pytest's testpaths {testpaths!r} leaves the gate running a "
            "narrowed surface: it must reach the whole tests/ directory")
        unreached = [name for name in self.found
                     if not fnmatch.fnmatch(name, "test_*.py")]
        self.assertEqual(
            unreached, [],
            f"{unreached} sits inside tests/ and pytest's default pattern "
            "test_*.py does not match it, so the gate runs a suite pytest "
            "never collects; rename the suite or the pattern moves with it")


class GateNodeHalfTests(unittest.TestCase):
    """"""
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.config = configuration()
        self.stated, self.test_all = gate_command(self.manifest, self.config)

    """The Node half has to be the Node gate `package.json` already defines.

    `node --test tests/*.test.mjs` looks like the whole Node suite and is not:
    the suites resolve their domain profile from an environment variable the
    npm script sets, so the bare invocation dies at import with every file
    unrun. It dies loudly, which is the only mercy here -- and because the
    stages are joined by `&&`, a Node half that exits non-zero means the
    Python half never runs at all.

    Derived from `package.json` rather than restated, so an assignment added
    to that script tomorrow is required of the gate the day it lands.
    """

    #: A leading `NAME=value` prefix on a shell command line.
    ASSIGNMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")

    def script_assignments(self):
        script = json.loads(
            MANIFEST.read_text(encoding="utf-8"))["scripts"]["test"]
        found = []
        for token in script.split():
            match = self.ASSIGNMENT_RE.match(token)
            if not match:
                break
            found.append(match.group(1))
        return script, found

    def test_the_node_half_carries_what_the_npm_script_carries(self):
        script, assignments = self.script_assignments()
        self.assertTrue(
            assignments,
            "package.json's test script sets no environment at all, so this "
            f"rule has nothing to require and proves nothing: {script!r}")
        stage = node_stage(self.manifest)
        delegated = re.fullmatch(r"npm (?:run )?(\S+)", stage.strip())
        if delegated:
            target_script = self.manifest.get("scripts", {}).get(delegated.group(1), "")
            stage = target_script if target_script else stage
        if re.fullmatch(r"npm (?:run )?test", stage.strip()):
            return
        missing = [name for name in assignments if name not in stage]
        self.assertEqual(
            missing, [],
            f"the gate's Node stage {stage!r} neither delegates to the npm "
            f"script nor sets {missing}, which that script sets. Without it "
            "the Node suites raise at import, the stage exits non-zero, and "
            "the Python half behind the `&&` never runs")


class GateInterpreterTests(unittest.TestCase):
    """"""
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.config = configuration()
        self.stated, self.test_all = gate_command(self.manifest, self.config)

    """The configured interpreter has to be able to run the suites.

    Every assertion here drives the interpreter the configuration actually
    names, as a process. A bare `python3` is whatever the caller's path
    resolves it to, and the one this repository was configured against could
    not import this repository's own code at all.
    """

    def interpreter(self):
        """Resolve the program `test:py` names, the way a shell running the
        npm script would, then insist on a file on disk.

        A token carrying a path separator is resolved against the
        repository, never through `PATH`: that is the whole point of naming
        a path, and consulting `PATH` for it would reintroduce the lottery.
        A bare name still goes through `PATH`, because that is what a shell
        would do with it -- and `test_the_gate_names_the_provisioned_
        interpreter` is what refuses a bare name in the first place.
        """
        named = pytest_stage(self.manifest).split()[0]
        if "/" in named or "\\" in named:
            resolved = FORGE / named
        else:
            resolved = Path(shutil.which(named) or (FORGE / named))
        self.assertTrue(
            resolved.is_file(),
            f"the gate names the interpreter {named!r}, which resolves to no "
            f"file at {resolved}. If the environment is simply not "
            "provisioned yet, `npm run setup` creates it; the gate cannot "
            "pass before it exists, and reporting that as anything other "
            "than a failure would hide the one fact that decides whether "
            "the suites can run at all")
        # `pytest` is a console script, not something that can drive `-c`;
        # the PYTHON the distribution provisions beside it is what answers
        # the import probes these tests drive.
        python_candidate = resolved.parent / "python"
        self.assertTrue(
            python_candidate.is_file(),
            f"pytest resolved to {resolved}, but is the sibling interpreter "
            f"{python_candidate} missing? The import probes below must be "
            "driven by the same distribution that runs the suites")
        return python_candidate

    def drive(self, source):
        return subprocess.run([str(self.interpreter()), "-c", source],
                              cwd=str(FORGE), capture_output=True, text=True,
                              timeout=120)

    def test_the_gate_names_the_provisioned_interpreter(self):
        """The gate's interpreter and the provisioning script's environment
        are the same environment -- asked of both declarations, and
        answerable whether or not that environment exists yet.

        This is the half that is about the REPOSITORY. The three probes
        below are about the MACHINE: they need the environment on disk and
        fail while it is absent, which is true and actionable. Conflating
        the two is what let a real configuration defect read as somebody's
        missing setup for as long as it did.
        """
        named = pytest_stage(self.manifest).split()[0]
        self.assertEqual(
            Path(named).parent, provisioned_bin_directory(),
            f"`test:py` names {named!r}, which does not live in the "
            "environment `scripts/setup_env.py` provisions. A gate that "
            "names an interpreter nothing in this repository creates is a "
            "gate that only passes on a machine somebody prepared by hand")

    def test_the_gate_names_an_interpreter_that_exists_on_disk(self):
        self.interpreter()

    def test_the_named_interpreter_imports_the_module_that_decides(self):
        done = self.drive("import sys\n"
                          f"sys.path.insert(0, {str(DECIDING_SCRIPTS)!r})\n"
                          "import adapter\n")
        self.assertEqual(
            done.returncode, 0,
            "the interpreter the gate names cannot import the remote skill's "
            "adapter, so every suite that touches it errors before it asserts "
            f"anything:\n{done.stderr}")

    def test_the_named_interpreter_carries_requests(self):
        """The one import the suites reach for outside the standard library.

        Named here rather than derived from `requirements.txt`, which does not
        list it: it arrives as another row's dependency. That is precisely why
        an interpreter can satisfy the requirements file and still fail the
        suites, and why this asks the interpreter instead of the file.
        """
        done = self.drive("import requests\n")
        self.assertEqual(
            done.returncode, 0,
            "the interpreter the gate names has no `requests`, so the suites "
            f"that import it error rather than assert:\n{done.stderr}")

    def assert_derivation_is_non_vacuous(self):
        """A silent empty scope or empty required set would let every
        assertion downstream of it pass over nothing, which reads exactly
        like a clean result. Called from both tests below so neither one
        can pass vacuously, even the capability probe that never touches
        the required-import set directly.
        """
        scope = import_scan_scope()
        self.assertTrue(
            scope,
            "the scanned file universe (IMPORT_SCOPE_PATHSPECS) is empty "
            "-- nothing was found under tests/, src/, or any skill's "
            "scripts/ tree, so this guard has nothing to check")
        required = required_third_party_imports()
        self.assertTrue(
            required,
            "the derived required-import set is empty -- either nothing "
            "in scope imports anything outside the standard library, or "
            "the derivation itself is broken; either way this guard would "
            "be checking nothing")
        return scope, required

    def test_the_derivation_reaches_the_assets_the_scripts_declare(self):
        """Without this, a broken `_ASSET`-constant parse would silently
        shrink `import_scan_scope()` back to exactly the blind spot this
        guard exists to close: `nbformat` and `nbclient` live ONLY inside
        `assets/colab/executor.py` and `assets/runner_invoke.py`, never in
        a file `skills/*/scripts/*.py` reaches directly, so a derivation
        that resolved zero asset files would never see either name.
        """
        resolved = resolved_asset_files()
        self.assertTrue(
            resolved,
            "resolved_asset_files() found nothing -- either no script in "
            "scope declares an `_ASSET` constant any more, or the parse "
            "of that declaration is broken; both would silently drop "
            "nbformat/nbclient from the required set")
        under_assets = [p for p in resolved
                        if "assets" in p.relative_to(FORGE).parts]
        self.assertTrue(
            under_assets,
            f"none of the resolved files {sorted(resolved)} sit under an "
            "assets/ directory, so the resolution is not actually "
            "reaching the staged asset files it claims to")

    def test_the_named_interpreter_carries_every_import_the_forge_requires(self):
        """Every third-party import the forge's own code requires, derived
        from `tests/`, `src/`, every skill's `scripts/` tree, and the
        asset files those scripts stage as subprocesses -- probed under
        the interpreter the gate names, in ONE subprocess.

        Measured today: this same interpreter passed the two hand-picked
        import probes above (`adapter`, `requests`) while the environment
        was missing `nbformat`, `nbclient`, the `papersmith` distribution,
        and `ipykernel` -- and the full gate then failed 31 tests, taking
        13 minutes to reveal what this derived probe reports in seconds.
        A hand-picked probe only ever proves what somebody remembered to
        pick; this one is required to find everything the code itself
        reaches for.
        """
        scope, required = self.assert_derivation_is_non_vacuous()
        names = sorted(required)
        program = (
            "import importlib.util, json\n"
            f"names = {names!r}\n"
            "missing = [n for n in names if importlib.util.find_spec(n) is None]\n"
            "print(json.dumps(missing))\n"
        )
        done = self.drive(program)
        self.assertEqual(
            done.returncode, 0,
            f"the import probe itself crashed under the gate's interpreter"
            f" (scanned {len(scope)} files, required {names}):\n{done.stderr}")
        missing = json.loads(done.stdout)
        if missing:
            detail = "; ".join(
                f"{name} (e.g. {required[name][0].relative_to(FORGE)})"
                for name in missing
            )
            self.fail(
                "the interpreter the gate names cannot import "
                f"{len(missing)} distribution(s) this forge's own code "
                f"requires: {detail}")

    def test_the_named_interpreter_can_start_a_notebook_kernel(self):
        """A CAPABILITY probe, not an import probe -- and deliberately so.

        `ipykernel` is the fourth gap measured today, and NO file in this
        repository imports it: `nbclient` pulls in `jupyter_client`, which
        knows how to TALK to a kernel, and never `ipykernel`, which is the
        thing that actually RUNS the cells. That gap surfaced as a child
        process exiting non-zero mid-notebook, not as a missing import, so
        no import scan of any scope -- however wide -- could ever have
        found it. This asks the interpreter to actually resolve a `python3`
        kernel spec instead of asking whether a module merely imports.
        """
        self.assert_derivation_is_non_vacuous()
        program = (
            "import sys\n"
            "try:\n"
            "    from jupyter_client.kernelspec import find_kernel_specs\n"
            "except ImportError as exc:\n"
            "    print('NO_JUPYTER_CLIENT:' + str(exc))\n"
            "    sys.exit(0)\n"
            "print('FOUND' if 'python3' in find_kernel_specs() else 'NOT_FOUND')\n"
        )
        done = self.drive(program)
        self.assertEqual(
            done.returncode, 0,
            f"the kernel-spec probe itself crashed:\n{done.stderr}")
        output = done.stdout.strip()
        if output.startswith("NO_JUPYTER_CLIENT"):
            self.fail(
                "the interpreter the gate names has no `jupyter_client` at "
                "all, so a kernel spec cannot even be asked for -- that is "
                "test_the_named_interpreter_carries_every_import_the_forge_"
                f"requires's business, not this one's: {output}")
        self.assertEqual(
            output, "FOUND",
            "the interpreter the gate names cannot resolve a `python3` "
            "notebook kernel spec, so nbclient's NotebookClient has "
            "nothing to execute the notebook suites' cells with -- even "
            "though every import above resolves cleanly. Install "
            "`ipykernel` in that environment "
            f"(e.g. `python -m ipykernel install --user`): {output}")


if __name__ == "__main__":
    unittest.main()
