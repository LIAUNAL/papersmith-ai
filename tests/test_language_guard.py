"""The repository speaks English, and so does every agent's doctrine.

Two promises are pinned here. Every shipped document, source and template is
English prose: Spanish survives only where an allowlist entry below says why
(an operator's verbatim words, a locale catalogue, fixture data a test feeds
an engine, an archived record). And every harness entrypoint carries the same
Language section: reply to the human in their language, keep everything else
English.

The detector is a heuristic, not a parser of Spanish. A line is Spanish when it
opens a question or exclamation with an inverted mark, when it pairs an accented
letter with a Spanish function word, or when it holds three function words no
English sentence uses. Test modules are judged on their prose only (comments and
docstrings): a Spanish string literal in a test is data the code under test
reads, and translating it would test something else. A JavaScript or TypeScript
test's prose is its comment lines; a trailing comment after code is not read.
"""

from __future__ import annotations

import ast
import fnmatch
import io
import re
import subprocess
import tempfile
import tokenize
import unittest
from dataclasses import dataclass
from pathlib import Path

from papersmith.generators import ALL_TOOLS, render_files
from papersmith.render import package_template_path

REPO = Path(__file__).resolve().parents[1]
SUFFIXES = (".md", ".py", ".tpl", ".json", ".ts", ".tsx", ".mjs", ".js")
JS_SUFFIXES = (".ts", ".tsx", ".mjs", ".js")
#: Excluded outright, not allowlisted: the dashboard's Spanish lives there
#: until T2 of odd/tasks/language-surfaces.md moves it into a catalogue, and
#: the guard is extended to it afterwards. Dependencies, vendored code and
#: built bundles are not ours to judge: their source is somewhere else.
EXCLUDED = ("skills/_core/command_center/*", "*node_modules/*", "vendor/*", "*/vendor/*",
            "dist/*", "*/dist/*", "*.bundle.js", "*.min.js")

ENTRYPOINTS = ("CLAUDE.md", "OPENCODE.md", ".pi/APPEND_SYSTEM.md", ".agents/AGENTS.md")
LANGUAGE = package_template_path("language.md.tpl").read_text(encoding="utf-8").strip()

ACCENTED = re.compile(r"[áéíóúñÁÉÍÓÚÑ]")
INVERTED = re.compile(r"[¿¡]\w")
WORD = re.compile(r"[a-záéíóúñü]+", re.IGNORECASE)
#: Spanish function words that are not English words either.
STRONG = frozenset(
    "que los las una para pero como esta este esto cuando donde porque desde "
    "hasta entre sus cada hay muy nunca siempre todos toda puede tiene también "
    "más está nada nadie algo eso ese esa así mismo otro otra poder ser igual "
    "parte ya".split())
#: Short Spanish words that collide with English or code on their own, so they
#: only count next to an accented letter.
WEAK = STRONG | frozenset("de la el en y es se lo un al su no del con por sin".split())


@dataclass(frozen=True)
class Allow:
    """One sanctioned exception. ``lines`` narrows it to the lines holding
    one of those substrings; without it the whole file is exempt."""

    pattern: str
    reason: str
    lines: tuple[str, ...] = ()


PENDING_T2 = "pending T2 English catalogue"

ALLOWLIST = (
    Allow("odd/tasks/*", "verbatim operator quotes kept as provenance"),
    Allow("openspec/changes/archive/*", "archived records"),
    Allow("openspec/specs/*", "fixture data: section titles of a Spanish source paper",
          ("Formulación", "Fundamentos de métodos", "Estimación de la entropía",
           "Rényi basada")),
    Allow("CHANGELOG.md", "release history quotes past labels"),
    Allow("docs/diagrams/locales/es.json", "the diagrams' Spanish locale catalogue"),
    Allow("docs/skills.md", "accent-folding and name-normalization examples",
          ("Normalización", "adaptación", "Sección 3. Formulación", "Ñandú", "`é`")),
    Allow("docs/cli.md", PENDING_T2),
    Allow("skills/proposal-deliberation/SKILL.md", "accent-folding examples",
          ("Normalización",)),
    Allow("skills/experimental-implementation/SKILL.md", "vocabulary data",
          ("`ecuación`", "`experimentación`")),
    Allow("skills/*/impl_profile.py", "vocabulary data", ("_es\": \"",)),
    Allow("skills/plausibility/*", "quotes the atlas button's literal label",
          ("Disposición de grupos",)),
    Allow("tests/test_sota_atlas.py", "quotes the atlas button's literal label",
          ("Disposición de grupos",)),
    Allow("skills/paper-writing/scripts/paper_declarations.py", "verbatim operator quote",
          ("las decisiones no viven en ti",)),
    Allow("skills/proposal-deliberation/profile.ts", "vocabulary data", ("ecuaci",)),
    Allow("skills/_core/deliberation/engine/intent-resolver.ts",
          "Spanish instruction vocabulary the resolver recognizes",
          ("has('", ".test(", ".match(/", "=/(?:")),
    Allow("skills/_core/deliberation/engine/target-resolver.ts",
          "Spanish stopwords and heading vocabulary the resolver recognizes",
          ("STOPWORDS", "secci[oó]n")),
    Allow("skills/_core/deliberation/engine/smoke-runner.ts",
          "Spanish instructions the smoke run feeds the resolver", ("execute({instruction:",)),
    Allow("tests/fixtures/*", "fixture data fed to the code under test"),
    Allow("tests/test_experimental_implementation.py",
          "quotes a past engine refusal verbatim", ("no declara qué reescribiría",)),
)


def is_spanish(line: str) -> bool:
    if INVERTED.search(line):
        return True
    words = {word.lower() for word in WORD.findall(line)}
    if ACCENTED.search(line) and words & WEAK:
        return True
    strong = len(words & STRONG)
    return strong >= 3 or (strong >= 1 and len(words & WEAK) >= 4)


def _tracked_files() -> list[str]:
    """Tracked and untracked-but-not-ignored files that exist on disk: a
    translation not yet staged is judged, a deletion not yet staged is not."""
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO, capture_output=True, text=True, check=True).stdout.splitlines()
    return sorted({rel for rel in listed
                   if rel.endswith(SUFFIXES) and (REPO / rel).is_file()
                   and not any(fnmatch.fnmatch(rel, pat) for pat in EXCLUDED)})


def _prose_lines(source: str) -> dict[int, str]:
    """A Python test's comments and docstrings, by line number."""
    prose: dict[int, str] = {}
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        tree = ast.parse(source)
    except (SyntaxError, tokenize.TokenError):
        return dict(enumerate(source.split("\n"), 1))
    for token in tokens:
        if token.type == tokenize.COMMENT:
            prose[token.start[0]] = token.string
    lines = source.split("\n")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                for number in range(body[0].lineno, body[0].end_lineno + 1):
                    prose[number] = lines[number - 1]
    return prose


def _js_prose_lines(source: str) -> dict[int, str]:
    """A JavaScript or TypeScript test's comment lines, by line number: those
    opening with ``//``, and every line of a block comment that opens a line."""
    prose: dict[int, str] = {}
    in_block = False
    for number, line in enumerate(source.split("\n"), 1):
        stripped = line.lstrip()
        if in_block or stripped.startswith(("//", "/*")):
            prose[number] = line
            if stripped.startswith("/*") or in_block:
                in_block = "*/" not in line
    return prose


def _is_test(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.startswith("tests/") or ".test." in name or ".spec." in name


def _lines(rel: str) -> dict[int, str]:
    text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
    if _is_test(rel) and rel.endswith(".py"):
        return _prose_lines(text)
    if _is_test(rel) and rel.endswith(JS_SUFFIXES):
        return _js_prose_lines(text)
    return dict(enumerate(text.split("\n"), 1))


def _allowed(rel: str, line: str) -> Allow | None:
    for entry in ALLOWLIST:
        if fnmatch.fnmatch(rel, entry.pattern) and (
                not entry.lines or any(marker in line for marker in entry.lines)):
            return entry
    return None


def scan() -> tuple[list[str], set[Allow]]:
    """``(violations, allowlist entries that excused at least one line)``."""
    violations: list[str] = []
    used: set[Allow] = set()
    for rel in _tracked_files():
        for number, line in _lines(rel).items():
            if not is_spanish(line):
                continue
            entry = _allowed(rel, line)
            if entry is None:
                violations.append(f"{rel}:{number}: {line.strip()[:100]}")
            else:
                used.add(entry)
    return violations, used


class SpanishDetectorTests(unittest.TestCase):
    """The detector fires on Spanish and stays quiet on English and code, so
    a clean scan means something."""

    def test_it_flags_spanish_prose(self) -> None:
        for line in ("Esta función devuelve el número de secciones.",
                     "¿Qué sujetos ve la normalización?",
                     "Una tarea puede estar hecha a medias, pero nadie lo nota cuando corre.",
                     "Declararlo y no registrarlo deja la parte sin poder computarse igual."):
            with self.subTest(line=line):
                self.assertTrue(is_spanish(line))

    def test_it_passes_english_and_code(self) -> None:
        for line in ("This function returns the number of sections.",
                     "x, y = sin(theta), cos(theta)  # en dash, de facto",
                     '_WORD = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{4,}")',
                     "# OT1 has no glyphs for these: as text they print as ¡ ¿ and a dash.",
                     "the Fréchet distance between both embeddings"):
            with self.subTest(line=line):
                self.assertFalse(is_spanish(line))

    def test_a_test_module_is_judged_on_its_prose_only(self) -> None:
        source = ('"""Una prueba que nadie corre."""\n'
                  'FIXTURE = "Modifica la sección de los métodos."\n'
                  '# este comentario está en español\n')
        self.assertEqual(sorted(_prose_lines(source)), [1, 3])

    def test_a_javascript_test_is_judged_on_its_comments_only(self) -> None:
        source = ("// un comentario que nadie lee\n"
                  "const instruction = 'Modifica la sección de los métodos.';\n"
                  "/* un bloque\n"
                  "   que sigue */\n"
                  "assert.ok(true);\n")
        self.assertEqual(sorted(_js_prose_lines(source)), [1, 3, 4])

    def test_only_test_modules_are_judged_on_prose(self) -> None:
        for rel in ("tests/proposal-workspace.test.mjs", "ui/src/lib/hash.test.ts",
                    "ui/e2e/atlas.spec.ts", "tests/test_extract_pdf.py"):
            with self.subTest(rel=rel):
                self.assertTrue(_is_test(rel))
        self.assertFalse(_is_test("skills/_core/deliberation/engine/ambiguity-gate.ts"))


class RepositoryLanguageTests(unittest.TestCase):
    def test_no_spanish_prose_outside_the_allowlist(self) -> None:
        violations, _ = scan()
        self.assertEqual(violations, [], "Spanish prose in shipped files; translate it, "
                         "or allowlist it with a reason:\n" + "\n".join(violations))

    def test_every_allowlist_entry_still_excuses_something(self) -> None:
        """An exception that no longer matches is a stale permission: once
        T1b or T2 translates a file, its entry must go."""
        _, used = scan()
        stale = [f"{entry.pattern} ({entry.reason})" for entry in ALLOWLIST if entry not in used]
        self.assertEqual(stale, [])

    def test_every_allowlist_entry_states_a_reason(self) -> None:
        for entry in ALLOWLIST:
            with self.subTest(pattern=entry.pattern):
                self.assertTrue(entry.reason.strip())

    def test_the_spanish_copies_are_gone(self) -> None:
        self.assertFalse((REPO / "README.es.md").exists())
        self.assertEqual(sorted(path.name for path in REPO.glob("MANTENIMIENTO-*.md")), [])
        for name in ("MAINTENANCE-the-forge-carries-no-paper-inside.md",
                     "MAINTENANCE-seven-ways-to-fail-green.md"):
            with self.subTest(name=name):
                self.assertTrue((REPO / name).is_file())


class LanguageDoctrineTests(unittest.TestCase):
    """The reply-language rule reaches every harness, in a new workspace and
    in this repository, from one template."""

    def test_the_rule_names_both_halves(self) -> None:
        self.assertTrue(LANGUAGE.startswith("## Language\n"))
        self.assertIn("in the language they write in", LANGUAGE)
        for half in ("skills", "agent definitions", "messages between agents",
                     "tool inputs", "commit messages", "unless the paper declares"):
            with self.subTest(half=half):
                self.assertIn(half, LANGUAGE)

    def test_a_new_workspace_states_the_rule_in_every_harness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rendered = render_files(Path(tmp), {"name": "fresh-paper"}, tools=ALL_TOOLS)
        for path in ENTRYPOINTS:
            with self.subTest(path=path):
                self.assertEqual(rendered[path].count(LANGUAGE), 1)

    def test_this_repository_states_the_same_rule(self) -> None:
        for path in ENTRYPOINTS:
            with self.subTest(path=path):
                text = (REPO / path).read_text(encoding="utf-8")
                self.assertEqual(text.count(LANGUAGE), 1)
                self.assertEqual(text.count("## Language\n"), 1)


if __name__ == "__main__":
    unittest.main()
