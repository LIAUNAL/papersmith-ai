"""The Idea pane (idea-shaping S6): an "Idea" tab for every line, a six-step
stepper (sources with status chips, profile, experience, interests with the
bank's thematic help, topic cards with evidence labelled by source, the draft
with the prompt gate), "Talk to the guide" and "Launch plausibility"; every
string in both catalogues."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from papersmith import __version__
from skills._core.command_center import server

STATIC = Path(server.__file__).resolve().parent / "static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")
PANEL = (STATIC / "idea-panel.js").read_text(encoding="utf-8")

HARNESS = r"""
const fs = require('fs');
const store = {};
const listeners = {};
const els = {};
function el(id) { return els[id] || (els[id] = { id, value: '', innerHTML: '', checked: false }); }
global.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } };
global.CustomEvent = function (name, init) { this.type = name; this.detail = init && init.detail; };
global.window = { localStorage: global.localStorage };
global.document = {
  documentElement: {}, readyState: 'complete', getElementById: el, querySelectorAll: () => [],
  addEventListener: (type, fn) => { (listeners[type] = listeners[type] || []).push(fn); },
  dispatchEvent: (e) => { (listeners[e.type] || []).forEach((fn) => fn(e)); },
};
for (const file of process.argv.slice(1)) eval(fs.readFileSync(file, 'utf8'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
window.i18n.setLanguage(input.lang || 'en');
const calls = [];
window.sendToCli = async (t, r, o) => { calls.push(['send', t, r, o && o.kind]); return input.sendResult ?? true; };
global.fetch = async (url, init) => {
  calls.push(['fetch', url, init && init.body ? JSON.parse(init.body) : null]);
  const r = (input.responses || {})[url] || { status: 200, body: input.view };
  return { ok: r.status < 400, status: r.status, json: async () => r.body };
};
(async () => {
  const out = { html: window.IdeaPanel.html(input.view) };
  window.IdeaPanel.reset();
  window.IdeaPanel.render(input.view);
  for (const step of input.steps || []) {
    if (step.values) Object.entries(step.values).forEach(([id, v]) => { el(id).value = v; });
    await window.IdeaPanel.act(step.action, step.arg);
    await new Promise((r) => setTimeout(r, 5));
  }
  out.calls = calls;
  out.rendered = el('ideaPanel').innerHTML;
  console.log(JSON.stringify(out));
})();
"""

TWO_SENTENCES = ("Current EEG classifiers lose accuracy across hospitals. "
                 "I propose a domain-adaptive graph model that keeps it.")


def brief(**parts) -> dict:
    base = {
        "schema": 1, "updated_at": None,
        "bank": {"choice": None, "server": None, "compatible": None, "tools": [], "available": None,
                 "reason": None, "checked_at": None},
        "profile": {"orcid": None, "openalex_author": None, "scholar_url": None, "display_name": None,
                    "works_count": None, "topics": [], "source": None, "reason": None},
        "experience": {"level": None, "methods": [], "resources": [], "time": None},
        "interests": {"keywords": [], "domain": None, "admired_paper": None},
        "topics": [], "chosen": {"topic_ids": [], "note": None},
        "draft": {"text": "", "source_topics": [], "gate": {"ok": False, "score": None, "missing": []},
                  "approved": False, "approved_at": None},
        "history": [],
    }
    for key, value in parts.items():
        base[key] = {**base[key], **value} if isinstance(base[key], dict) else value
    return base


def view(**parts) -> dict:
    b = brief(**parts)
    ready = bool(b["draft"]["approved"])
    return {"ok": True, "brief": b, "levels": ["student", "early-career", "experienced", "senior"],
            "choices": {"managed": "banco-lia", "others": [
                {"server": "labbank", "transport": "stdio", "command": "python", "args": ["labbank.py"]}]},
            "ready": ready, "handoff": f"/plausibility {b['draft']['text']}" if ready else None}


TOPICS = [{"id": "t1", "title": "EEG <b>graphs</b> in neurology", "rationale": "Built from your keywords.",
           "keywords": ["eeg", "graphs"],
           "evidence": [{"source": "operator", "detail": "your keywords: eeg, graphs", "count": None, "url": None},
                        {"source": "bank:labbank", "detail": "2 related items", "count": 2, "url": None},
                        {"source": "openalex", "detail": "12 works since 2022 in OpenAlex: few recent works",
                         "count": 12, "url": "https://api.openalex.org/works?search=eeg"},
                        {"source": "profile", "detail": "9 of your works", "count": 9,
                         "url": "javascript:alert(1)"}]},
          {"id": "t2", "title": "Domain shift for EEG", "rationale": "Another pairing.", "keywords": [],
           "evidence": []}]


def run(data: dict, lang: str = "en", steps=(), responses=None, send_result=True) -> dict:
    files = [str(STATIC / "i18n" / "en.js"), str(STATIC / "i18n" / "es.js"), str(STATIC / "i18n.js"),
             str(STATIC / "idea-panel.js")]
    done = subprocess.run(["node", "-e", HARNESS, *files], capture_output=True, text=True, check=True,
                          input=json.dumps({"view": data, "lang": lang, "steps": list(steps),
                                            "responses": responses or {}, "sendResult": send_result}),
                          cwd=tempfile.gettempdir())
    return json.loads(done.stdout)


def posts(out: dict, url: str) -> list:
    return [c[2] for c in out["calls"] if c[0] == "fetch" and c[1] == url]


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class StepperTests(unittest.TestCase):
    def test_six_steps_and_a_reload_resumes_at_the_first_unanswered_one(self) -> None:
        html = run(view())["html"]
        for label in ("Sources", "Profile", "Experience", "Interests", "Topics", "Draft"):
            self.assertIn(label, html)
        self.assertEqual(len(re.findall(r'data-idea-action="go" data-idea-arg="\d"', html)) >= 6, True)
        self.assertIn('data-idea-step="1"', html)
        answered = view(bank={"choice": "none"}, profile={"source": "none", "reason": "offline"},
                        experience={"level": "student"})
        self.assertIn('data-idea-step="4"', run(answered)["html"])

    def test_the_guide_and_the_spanish_labels(self) -> None:
        out = run(view(), lang="es", steps=[{"action": "guide"}])
        self.assertIn("Hablar con el guía", out["html"])
        self.assertIn("Fuentes", out["html"])
        self.assertIn(["send", "/idea-shaping", False, "slash"], out["calls"])

    def test_an_unreadable_brief_is_reported(self) -> None:
        html = run({"ok": False, "code": "BRIEF_UNREADABLE", "message": "fix <it>"})["html"]
        self.assertIn("The idea brief cannot be read: fix &lt;it&gt;", html)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class SourcesTests(unittest.TestCase):
    def test_three_radio_cards_and_the_other_servers(self) -> None:
        html = run(view())["html"]
        for value in ("banco-lia", "other", "none"):
            self.assertIn(f'data-idea-bank="{value}"', html)
        self.assertIn('<option value="labbank"', html)
        self.assertIn("No bank is queried", html)
        self.assertIn('data-idea-action="bank-add"', html)

    def test_status_chips_after_a_probe(self) -> None:
        # An unreachable bank keeps step 1 open: a reload shows the reason and Retry.
        down = run(view(bank={"choice": "banco-lia", "server": "banco-lia", "available": False,
                              "reason": "cannot start uvx"}))["html"]
        self.assertIn('data-idea-step="1"', down)
        self.assertIn("Unreachable: cannot start uvx", down)
        self.assertIn('data-idea-action="bank-retry"', down)
        back = [{"action": "go", "arg": "1"}]
        up = run(view(bank={"choice": "banco-lia", "server": "banco-lia", "available": True,
                            "compatible": True}), steps=back)["rendered"]
        self.assertIn(">Available</span>", up)
        guide = run(view(bank={"choice": "other", "server": "notes", "available": True, "compatible": False}),
                    steps=back)["rendered"]
        self.assertIn("notes: used only by talking to the guide (its mcp__notes__* tools)", guide)
        compatible = run(view(bank={"choice": "other", "server": "labbank", "available": True,
                                    "compatible": True}), steps=back)["rendered"]
        self.assertIn("labbank: compatible, queried like banco-lia", compatible)

    def test_choosing_posts_the_choice(self) -> None:
        out = run(view(), steps=[{"action": "bank-pick", "arg": "none"}, {"action": "bank-choose"}])
        self.assertEqual(posts(out, "/api/idea/bank"), [{"action": "choose", "choice": "none"}])
        out = run(view(), steps=[{"action": "bank-pick", "arg": "other"},
                                 {"action": "bank-choose", "values": {"ideaOtherServer": "labbank"}}])
        self.assertEqual(posts(out, "/api/idea/bank"), [{"action": "choose", "choice": "other",
                                                          "server": "labbank"}])

    def test_adding_a_server_by_url_or_command(self) -> None:
        out = run(view(), steps=[{"action": "bank-add", "values": {"ideaServerName": "mybank",
                                                                   "ideaServerSpec": "https://bank.example/mcp"}}])
        self.assertEqual(posts(out, "/api/idea/bank"), [{"action": "add", "name": "mybank",
                                                          "url": "https://bank.example/mcp"}])
        out = run(view(), steps=[{"action": "bank-add", "values": {"ideaServerName": "mybank",
                                                                   "ideaServerSpec": "uvx my-bank"}}])
        self.assertEqual(posts(out, "/api/idea/bank")[0]["command"], "uvx my-bank")

    def test_a_refusal_is_shown(self) -> None:
        out = run(view(), steps=[{"action": "bank-pick", "arg": "none"}, {"action": "bank-choose"}],
                  responses={"/api/idea/bank": {"status": 422, "body": {
                      "ok": False, "code": "SERVER_MANAGED", "message": "asta is managed by smith"}}})
        self.assertIn("Not saved: asta is managed by smith", out["rendered"])


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class ProfileAndAnswersTests(unittest.TestCase):
    def test_profile_field_note_and_result_cards(self) -> None:
        start = view(bank={"choice": "none"})
        html = run(start)["html"]
        self.assertIn('id="ideaProfileText"', html)
        self.assertIn("Google Scholar is only used to find your name", html)
        found = view(bank={"choice": "none"}, profile={"source": "openalex", "display_name": "Ada Lovelace",
                                                      "works_count": 42,
                                                      "topics": [{"name": "BCI", "count": 9}]})
        out = run(found, steps=[{"action": "go", "arg": "2"}])
        self.assertIn("Ada Lovelace", out["rendered"])
        self.assertIn("42 works", out["rendered"])
        self.assertIn("BCI · 9", out["rendered"])
        offline = view(bank={"choice": "none"}, profile={"source": "none", "reason": "OpenAlex could not be reached"})
        out = run(offline, steps=[{"action": "go", "arg": "2"}])
        self.assertIn("No profile: OpenAlex could not be reached", out["rendered"])

    def test_profile_find_posts_the_free_answer(self) -> None:
        out = run(view(bank={"choice": "none"}),
                  steps=[{"action": "profile-find", "values": {"ideaProfileText": " Ada  Lovelace "}}])
        self.assertEqual(posts(out, "/api/idea/profile"), [{"text": "Ada Lovelace"}])

    def test_experience_chips_and_level(self) -> None:
        start = view(bank={"choice": "none"}, profile={"source": "none"})
        out = run(start, steps=[{"action": "chip-add", "arg": "methods", "values": {"ideaMethodsInput": "svm, SVM; surveys"}},
                                {"action": "experience-save", "values": {"ideaLevel": "student", "ideaTime": "six months"}}])
        self.assertEqual(posts(out, "/api/idea/experience"), [{"level": "student", "methods": ["svm", "surveys"],
                                                               "resources": [], "time": "six months"}])

    def test_interests_keywords_are_capped_at_five(self) -> None:
        start = view(bank={"choice": "none"}, profile={"source": "none"}, experience={"level": "student"})
        out = run(start, steps=[{"action": "chip-add", "arg": "keywords",
                                 "values": {"ideaKeywordsInput": "a, b, c, d, e, f"}},
                                {"action": "interests-save", "values": {"ideaDomain": "neurology"}}])
        self.assertEqual(posts(out, "/api/idea/interests"), [{"keywords": ["a", "b", "c", "d", "e"],
                                                              "domain": "neurology", "admired_paper": None}])

    def test_the_thematic_help_asks_banco_lia_with_the_keywords(self) -> None:
        start = view(bank={"choice": "banco-lia", "server": "banco-lia", "available": True, "compatible": True},
                     profile={"source": "none"}, experience={"level": "student"},
                     interests={"keywords": ["eeg", "graphs", "transfer"]})
        html = run(start, steps=[{"action": "go", "arg": "4"}])["rendered"]
        self.assertIn("Thematic help from the bank", html)
        suggestion = {"available": True, "keywords": ["eeg", "graphs", "transfer"], "match": "any",
                      "items": [{"id": "A1", "kind": "articulo", "title": "EEG <script>x</script>", "year": 2024}],
                      "topics": [{"id": "C1", "name": "Signals", "count": 1}],
                      "draft": TWO_SENTENCES}
        out = run(start, steps=[{"action": "suggest"}, {"action": "suggest-use"}],
                  responses={"/api/plausibility/suggest": {"status": 200, "body": suggestion}})
        self.assertEqual(posts(out, "/api/plausibility/suggest"),
                         [{"keywords": ["eeg", "graphs", "transfer"], "language": "en"}])
        self.assertEqual(posts(out, "/api/idea/draft"), [{"action": "text", "text": TWO_SENTENCES}])
        none = view(bank={"choice": "none"}, profile={"source": "none"}, experience={"level": "student"},
                    interests={"keywords": ["eeg", "graphs", "transfer"]})
        self.assertNotIn("Thematic help from the bank", run(none, steps=[{"action": "go", "arg": "4"}])["rendered"])

    def test_a_compatible_other_bank_is_searched_through_the_idea_route(self) -> None:
        start = view(bank={"choice": "other", "server": "labbank", "available": True, "compatible": True},
                     profile={"source": "none"}, experience={"level": "student"},
                     interests={"keywords": ["eeg", "graphs", "transfer"]})
        out = run(start, steps=[{"action": "suggest"}])
        self.assertEqual(posts(out, "/api/idea/bank"), [{"action": "search", "query": "eeg graphs transfer"}])
        self.assertEqual(posts(out, "/api/plausibility/suggest"), [])


ANSWERED = dict(bank={"choice": "none"}, profile={"source": "none"}, experience={"level": "student"},
                interests={"keywords": ["eeg", "graphs", "transfer"]})


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class TopicsTests(unittest.TestCase):
    def test_cards_label_every_evidence_item_by_source_and_escape(self) -> None:
        html = run(view(topics=TOPICS, **ANSWERED))["html"]
        self.assertIn('data-idea-step="5"', html)
        for label in ("You", "Bank: labbank", "OpenAlex", "Profile"):
            self.assertIn(f">{label}</span>", html)
        self.assertIn("EEG &lt;b&gt;graphs&lt;/b&gt; in neurology", html)
        self.assertIn('href="https://api.openalex.org/works?search=eeg"', html)
        self.assertNotIn("javascript:", html)

    def test_propose_then_combine_two_topics_with_a_note(self) -> None:
        out = run(view(**ANSWERED), steps=[{"action": "go", "arg": "5"}, {"action": "propose"}])
        self.assertEqual(posts(out, "/api/idea/topics"), [{"n": 3}])
        steps = [{"action": "topic-toggle", "arg": "t1"}, {"action": "topic-toggle", "arg": "t2"},
                 {"action": "choose", "values": {"ideaNote": "low-cost sensors"}}]
        out = run(view(topics=TOPICS, **ANSWERED), steps=steps)
        self.assertEqual(posts(out, "/api/idea/choose"), [{"topic_ids": ["t1", "t2"], "note": "low-cost sensors"}])


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class DraftTests(unittest.TestCase):
    def picked(self, **draft) -> dict:
        return view(topics=TOPICS, chosen={"topic_ids": ["t1"]}, draft=draft, **ANSWERED)

    def test_launch_is_disabled_until_the_draft_is_approved(self) -> None:
        html = run(self.picked(text="Graphs for EEG.", gate={"ok": False, "score": 40,
                                                             "missing": ["at least 2 sentences"]}))["html"]
        self.assertIn('data-idea-step="6"', html)
        self.assertRegex(html, r'data-idea-action="launch"[^>]*disabled')
        self.assertIn("Prompt gate: not yet (40/100)", html)
        self.assertIn("at least 2 sentences", html)
        out = run(self.picked(text="Graphs for EEG."), steps=[{"action": "launch"}])
        self.assertFalse([c for c in out["calls"] if c[0] == "send"])

    def test_compose_and_approve_store_an_edited_text_first(self) -> None:
        out = run(self.picked(), steps=[{"action": "compose"}])
        self.assertEqual(posts(out, "/api/idea/draft"), [{"action": "compose"}])
        out = run(self.picked(text="Old text."), steps=[{"action": "approve", "values": {"ideaDraft": TWO_SENTENCES}}])
        self.assertEqual(posts(out, "/api/idea/draft"), [{"action": "text", "text": TWO_SENTENCES}])
        self.assertEqual(posts(out, "/api/idea/approve"), [{}])

    def test_launch_types_the_approved_draft_with_the_gate_marker(self) -> None:
        approved = self.picked(text=TWO_SENTENCES, approved=True, approved_at="2026-11-25T10:00:00Z",
                               gate={"ok": True, "score": 100, "missing": []})
        html = run(approved)["html"]
        self.assertNotRegex(html, r'data-idea-action="launch"[^>]*disabled')
        out = run(approved, steps=[{"action": "launch", "values": {"ideaDraft": TWO_SENTENCES}}])
        self.assertIn(["send", f"/plausibility {TWO_SENTENCES} [prompt-gate: approved]", True, "slash"], out["calls"])
        out = run(approved, steps=[{"action": "launch", "values": {"ideaDraft": TWO_SENTENCES + " Edited."}}])
        self.assertFalse([c for c in out["calls"] if c[0] == "send"])


class PageWiringTests(unittest.TestCase):
    def test_the_tab_shows_for_every_line_after_the_line_tabs(self) -> None:
        buttons = re.findall(r"onclick=\"navigateTab\('([a-z]+)'\)\"", PAGE)
        self.assertEqual(buttons[:5], ["flow", "pipeline", "review", "study", "idea"])
        tag = re.search(r"<button[^>]*navigateTab\('idea'\)[^>]*>", PAGE).group(0)
        self.assertNotIn("data-kinds", tag)
        self.assertIn('data-i18n="nav.idea"', tag)

    def test_pane_script_and_refresh_hooks(self) -> None:
        self.assertIn('<div id="pane-idea" class="tab-pane">', PAGE)
        self.assertIn('id="ideaPanel"', PAGE)
        self.assertIn(f'src="./idea-panel.js?v={__version__}"', PAGE)
        self.assertRegex(PAGE, r"if \(tabId === 'idea'\) \{?\s*window\.refreshIdeaPanel\?\.\(\)")
        self.assertIn("idea: () => window.refreshIdeaPanel?.()", PAGE)
        allow = re.search(r"\[('pipeline'[^\]]*)\]\.includes\(hash\)", PAGE)
        self.assertIn("'idea'", allow.group(1))

    def test_the_panel_calls_its_routes_and_the_launch_marker(self) -> None:
        for route in ("/api/idea", "/api/idea/bank", "/api/idea/profile", "/api/idea/experience",
                      "/api/idea/interests", "/api/idea/topics", "/api/idea/choose", "/api/idea/draft",
                      "/api/idea/approve", "/api/plausibility/suggest"):
            self.assertIn(f"'{route}'", PANEL)
        self.assertIn("'[prompt-gate: approved]'", PANEL)


class CatalogueTests(unittest.TestCase):
    @staticmethod
    def keys(lang: str) -> set[str]:
        text = (STATIC / "i18n" / f"{lang}.js").read_text(encoding="utf-8")
        body = re.search(rf"window\.PAPERSMITH_I18N\.{lang}\s*=\s*(\{{.*\}})\s*;\s*\Z", text, re.S).group(1)
        return set(json.loads(body))

    def test_the_idea_keys_are_the_same_in_both_languages(self) -> None:
        en = {k for k in self.keys("en") if k.startswith("idea.")}
        es = {k for k in self.keys("es") if k.startswith("idea.")}
        self.assertGreater(len(en), 80)
        self.assertEqual(en, es)

    def test_every_literal_key_of_the_panel_exists(self) -> None:
        used = set(re.findall(r"'(idea\.[A-Za-z0-9_.]+)'", PANEL))
        self.assertGreater(len(used), 80)
        self.assertEqual(sorted(used - self.keys("en")), [])
        markup = set(re.findall(r'data-i18n="((?:idea|nav\.idea)[A-Za-z0-9_.]*)"', PAGE))
        self.assertEqual(sorted(markup - self.keys("en")), [])


if __name__ == "__main__":
    unittest.main()
