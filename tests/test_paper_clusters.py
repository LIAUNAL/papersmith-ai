"""Idea clusters of the Cited papers view.

``paper_clusters.cluster_papers`` is a computed reading of what a manuscript
cites: it groups papers by their text and by how the manuscript cites them, and
it works for any field, with no domain vocabulary and no fixed cluster count.
The panel shows those groups as a filter and says they are computed.
"""

from __future__ import annotations

import json
import random
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from skills._core.command_center import paper_clusters
from skills._core.command_center.paper_clusters import cluster_papers

STATIC = Path(paper_clusters.__file__).resolve().parent / "static"
PANEL = STATIC / "paper-explorer-panel.js"

REEFS = [
    ("reef1", "Coral reef bleaching under ocean warming", "Coral colonies lose symbionts when the reef warms."),
    ("reef2", "Symbiont shuffling in coral reef recovery", "Reef corals regain symbionts after bleaching events."),
    ("reef3", "Ocean acidification and coral reef calcification", "Acidification slows calcification of reef coral."),
    ("reef4", "Mapping coral bleaching across reef systems", "Satellite maps of coral bleaching on the reef."),
    ("reef5", "Reef fish depend on living coral", "Fish abundance falls when coral cover on a reef falls."),
]
BRIDGES = [
    ("bridge1", "Suspension bridge cable fatigue under traffic", "Steel cable fatigue grows with bridge traffic load."),
    ("bridge2", "Corrosion of steel cable in suspension bridges", "Cable corrosion shortens the life of a bridge."),
    ("bridge3", "Monitoring bridge deck vibration with steel sensors", "Deck vibration reveals bridge fatigue in steel."),
    ("bridge4", "Wind load on long suspension bridge decks", "Wind load excites the deck of a suspension bridge."),
    ("bridge5", "Fatigue cracks in welded steel bridge girders", "Welded steel girders crack with fatigue on a bridge."),
]
# Accents are written as escapes: this repository keeps accented Spanish in i18n/es.js only.
SPANISH = [
    ("rio1", "Calidad del agua en cuencas de r\u00edos andinos", "La calidad del agua de los r\u00edos cambia en la cuenca."),
    ("rio2", "Contaminaci\u00f3n del agua en r\u00edos de la cuenca alta", "Medimos la contaminaci\u00f3n del agua para cada r\u00edo."),
    ("rio3", "Caudal y sedimentos de r\u00edos en cuencas de monta\u00f1a", "El caudal de los r\u00edos arrastra sedimentos por la cuenca."),
    ("rio4", "Sedimentos y calidad del agua en una cuenca", "Los sedimentos alteran el agua de la cuenca y sus r\u00edos."),
    ("voto1", "Participaci\u00f3n electoral y voto juvenil urbano", "El voto juvenil crece con la participaci\u00f3n electoral."),
    ("voto2", "Campa\u00f1as electorales y voto en elecciones locales", "Las campa\u00f1as electorales mueven el voto de las elecciones."),
    ("voto3", "Abstenci\u00f3n electoral en elecciones municipales", "La abstenci\u00f3n electoral marca las elecciones del municipio."),
    ("voto4", "Encuestas de voto y participaci\u00f3n en elecciones", "Las encuestas anticipan el voto y la participaci\u00f3n electoral."),
]
LONERS = [
    ("loner1", "Glacier moraine dating with lichens", "Lichens date a moraine left by a retreating glacier."),
    ("loner2", "Medieval manuscript pigment chemistry", "Pigments of a medieval manuscript reveal its workshop."),
]


def corpus(*groups: list[tuple[str, str, str]]) -> list[dict]:
    return [{"key": key, "title": title, "abstract": abstract, "keywords": []}
            for group in groups for key, title, abstract in group]


def groups(answer: dict) -> list[set[str]]:
    return [set(cluster["keys"]) for cluster in answer["clusters"]]


def together(answer: dict, *keys: str) -> bool:
    return any(set(keys) <= group for group in groups(answer))


class TopicTests(unittest.TestCase):
    def test_two_separate_topics_split_into_two_clusters(self) -> None:
        answer = cluster_papers(corpus(REEFS, BRIDGES))
        self.assertCountEqual(groups(answer), [{k for k, _, _ in REEFS}, {k for k, _, _ in BRIDGES}])
        self.assertEqual(answer["unclustered"], [])
        self.assertIn("text", answer["signals"])
        self.assertTrue(answer["method"])

    def test_a_cluster_says_what_it_holds(self) -> None:
        answer = cluster_papers(corpus(REEFS, BRIDGES))
        for cluster in answer["clusters"]:
            self.assertEqual(cluster["size"], len(cluster["keys"]))
            self.assertEqual(cluster["keys"], sorted(cluster["keys"]))
            self.assertGreaterEqual(len(cluster["terms"]), 2)
            self.assertIsInstance(cluster["signals"], dict)
        labels = {cluster["keys"][0]: cluster["label"] for cluster in answer["clusters"]}
        self.assertIn("bridge", labels["bridge1"])
        self.assertIn("coral", labels["reef1"])

    def test_a_label_is_two_or_three_terms_with_no_stop_words(self) -> None:
        for answer in (cluster_papers(corpus(REEFS, BRIDGES)), cluster_papers(corpus(SPANISH))):
            for cluster in answer["clusters"]:
                parts = cluster["label"].split(" \u00b7 ")
                self.assertIn(len(parts), (2, 3))
                self.assertEqual(parts, cluster["terms"][:len(parts)])
                for part in parts:
                    self.assertNotIn(part, {"the", "of", "and", "in", "with", "under", "a", "on",
                                            "de", "la", "el", "los", "las", "del", "en", "y", "una", "para"})

    def test_a_spanish_corpus_clusters_and_keeps_its_accents_in_the_label(self) -> None:
        answer = cluster_papers(corpus(SPANISH))
        self.assertCountEqual(groups(answer), [{"rio1", "rio2", "rio3", "rio4"},
                                               {"voto1", "voto2", "voto3", "voto4"}])
        terms = {term for cluster in answer["clusters"] for term in cluster["terms"]}
        self.assertIn("r\u00edos", terms)

    def test_accents_and_plurals_do_not_split_a_term(self) -> None:
        for left, right in (("Cami\u00f3n blindado", "Camion antiguo"), ("Sonar arrays", "Sonar array")):
            papers = [{"key": "a", "title": f"{left} moderno"}, {"key": "b", "title": f"{right} clasico"},
                      {"key": "c", "title": "Tectonic plates drifting"}]
            self.assertTrue(together(cluster_papers(papers), "a", "b"), left)

    def test_hyphenated_terms_survive_and_state_of_the_art_does_not(self) -> None:
        papers = [{"key": f"p{n}", "title": f"Self-supervised pretraining state-of-the-art variant{n}"} for n in range(3)]
        papers += [{"key": f"q{n}", "title": f"Volcanic ash plume dispersal variety{n}"} for n in range(3)]
        answer = cluster_papers(papers)
        terms = {term for cluster in answer["clusters"] for term in cluster["terms"]}
        self.assertIn("self-supervised", terms)
        self.assertFalse(any("state" in term for term in terms))
        for cluster in answer["clusters"]:
            self.assertFalse({"self", "supervised"} & set(cluster["terms"]))

    def test_keywords_count_as_text(self) -> None:
        papers = [{"key": "a", "title": "One", "keywords": ["mycorrhiza", "soil"]},
                  {"key": "b", "title": "Two", "keywords": ["mycorrhiza", "soil"]},
                  {"key": "c", "title": "Three", "keywords": ["pulsar", "timing"]}]
        self.assertTrue(together(cluster_papers(papers), "a", "b"))

    def test_a_repository_subject_tag_is_not_a_topic(self) -> None:
        tag = ["FOS: Computer and information sciences"]
        papers = [{"key": "a", "title": "Glacier moraine dating", "keywords": tag},
                  {"key": "b", "title": "Pulsar timing arrays", "keywords": tag},
                  {"key": "c", "title": "Medieval pigment chemistry"},
                  {"key": "d", "title": "Volcanic ash dispersal"},
                  {"key": "e", "title": "Honeybee waggle dance"}]
        self.assertEqual(cluster_papers(papers)["unclustered"], ["a", "b", "c", "d", "e"])

    def test_a_title_weighs_more_than_an_abstract(self) -> None:
        tundra = "tundra permafrost thaw"
        quasar = "quasar redshift lensing"
        papers = [{"key": "t1", "title": tundra}, {"key": "t2", "title": tundra},
                  {"key": "q1", "title": quasar}, {"key": "q2", "title": quasar},
                  {"key": "both", "title": tundra, "abstract": quasar}]
        answer = cluster_papers(papers)
        self.assertTrue(together(answer, "both", "t1", "t2"))
        self.assertFalse(together(answer, "both", "q1"))


class SignalTests(unittest.TestCase):
    papers = corpus(REEFS, BRIDGES, LONERS)

    def test_with_no_signal_the_unrelated_pair_stays_unclustered(self) -> None:
        answer = cluster_papers(self.papers)
        self.assertEqual(answer["unclustered"], ["loner1", "loner2"])
        self.assertEqual(answer["signals"], ["text"])

    def test_co_citation_pulls_a_pair_together(self) -> None:
        answer = cluster_papers(self.papers, [["loner2", "loner1"]])
        self.assertTrue(together(answer, "loner1", "loner2"))
        self.assertEqual(answer["unclustered"], [])
        self.assertIn("cocitation", answer["signals"])
        pair = next(c for c in answer["clusters"] if "loner1" in c["keys"])
        self.assertEqual(pair["signals"]["cocited_pairs"], 1)

    def test_a_shared_idea_pulls_a_pair_together(self) -> None:
        papers = json.loads(json.dumps(self.papers))
        for paper in papers:
            if paper["key"] in ("loner1", "loner2"):
                paper["ideas"] = [{"idea": "H1", "why": "because"}]
        answer = cluster_papers(papers)
        self.assertTrue(together(answer, "loner1", "loner2"))
        self.assertIn("shared_idea", answer["signals"])
        pair = next(c for c in answer["clusters"] if "loner1" in c["keys"])
        self.assertEqual(pair["signals"]["shared_idea_pairs"], 1)

    def test_a_family_alone_links_nothing_but_is_reported(self) -> None:
        papers = json.loads(json.dumps(self.papers))
        for paper in papers:
            if paper["key"].startswith("loner"):
                paper["family"] = "Archives"
            if paper["key"].startswith("reef"):
                paper["family"] = "Marine"
        answer = cluster_papers(papers)
        self.assertEqual(answer["unclustered"], ["loner1", "loner2"])
        reef = next(c for c in answer["clusters"] if "reef1" in c["keys"])
        self.assertEqual(reef["signals"]["family"], "Marine")
        self.assertNotIn("Marine", reef["label"])
        bridge = next(c for c in answer["clusters"] if "bridge1" in c["keys"])
        self.assertIsNone(bridge["signals"]["family"])


class ContractTests(unittest.TestCase):
    def test_output_is_identical_across_shuffled_input(self) -> None:
        papers = corpus(REEFS, BRIDGES, SPANISH, LONERS)
        cocited = [["reef1", "bridge1"], ["loner1", "loner2", "rio1"]]
        expected = json.dumps(cluster_papers(papers, cocited), sort_keys=True)
        rng = random.Random(7)
        for _ in range(10):
            shuffled = papers[:]
            rng.shuffle(shuffled)
            groups_shuffled = [rng.sample(group, len(group)) for group in cocited]
            rng.shuffle(groups_shuffled)
            self.assertEqual(json.dumps(cluster_papers(shuffled, groups_shuffled), sort_keys=True), expected)

    def test_output_is_identical_across_processes(self) -> None:
        script = ("import json;from tests.test_paper_clusters import *;"
                  "print(json.dumps(cluster_papers(corpus(REEFS,BRIDGES,SPANISH,LONERS)),sort_keys=True))")
        root = Path(__file__).resolve().parent.parent
        runs = {subprocess.run(["python", "-c", script], capture_output=True, text=True, cwd=root, check=True,
                               env={"PYTHONHASHSEED": seed, "PATH": str(Path(__import__("sys").executable).parent)}).stdout
                for seed in ("1", "2", "3")}
        self.assertEqual(len(runs), 1)

    def test_cluster_ids_follow_the_members_not_the_position(self) -> None:
        both = cluster_papers(corpus(REEFS, BRIDGES))
        ids = {frozenset(c["keys"]): c["id"] for c in both["clusters"]}
        with_more = cluster_papers(corpus(REEFS, BRIDGES, LONERS))
        for cluster in with_more["clusters"]:
            self.assertEqual(cluster["id"], ids[frozenset(cluster["keys"])])
        self.assertEqual(len(set(ids.values())), 2)

    def test_clusters_sort_by_size_then_label(self) -> None:
        answer = cluster_papers(corpus(REEFS, BRIDGES[:3], SPANISH))
        order = [(-c["size"], c["label"]) for c in answer["clusters"]]
        self.assertEqual(order, sorted(order))

    def test_small_or_textless_input_returns_no_clusters_and_no_error(self) -> None:
        one = corpus(REEFS[:1])
        two = corpus(REEFS[:2])
        textless = [{"key": k} for k in "abcd"]
        blank = [{"key": k, "title": "", "abstract": None, "keywords": None} for k in "abc"]
        only_stop = [{"key": k, "title": "the of and de la"} for k in "abc"]
        for papers, left in (([], []), (one, ["reef1"]), (two, ["reef1", "reef2"]),
                             (textless, list("abcd")), (blank, list("abc")), (only_stop, list("abc"))):
            with self.subTest(papers=papers):
                answer = cluster_papers(papers)
                self.assertEqual(answer["clusters"], [])
                self.assertEqual(answer["unclustered"], left)
                self.assertTrue(answer["method"])

    def test_a_textless_paper_is_unclustered_beside_real_clusters(self) -> None:
        answer = cluster_papers(corpus(REEFS, BRIDGES) + [{"key": "ghost"}], [["ghost", "reef1"]])
        self.assertEqual(answer["unclustered"], ["ghost"])

    def test_malformed_input_never_raises(self) -> None:
        papers = [None, 3, "x", {}, {"key": None}, {"key": 5, "title": "x"},
                  {"key": "a", "title": 7, "abstract": ["no"], "keywords": "reef coral", "ideas": "bad", "family": 3},
                  {"key": "b", "title": "reef coral", "keywords": [1, None, "reef"], "ideas": [None, {"idea": 1}, {}]},
                  {"key": "c", "title": "reef coral"}]
        answer = cluster_papers(papers, [None, 4, "ab", ["a", None, 3], ["a"], [], ["ghost", "b"]])
        self.assertCountEqual([key for c in answer["clusters"] for key in c["keys"]] + answer["unclustered"],
                              ["a", "b", "c"])
        self.assertEqual(cluster_papers(None)["clusters"], [])
        self.assertEqual(cluster_papers({"a": 1}, {"b": 2})["clusters"], [])

    def test_every_paper_lands_exactly_once(self) -> None:
        papers = corpus(REEFS, BRIDGES, SPANISH, LONERS)
        answer = cluster_papers(papers)
        seen = [key for c in answer["clusters"] for key in c["keys"]] + answer["unclustered"]
        self.assertCountEqual(seen, [p["key"] for p in papers])

    def test_five_hundred_papers_stay_fast(self) -> None:
        rng = random.Random(11)
        topics = [[f"topic{t}word{w}" for w in range(40)] for t in range(12)]
        common = [f"commonword{w}" for w in range(200)]
        papers = []
        for n in range(500):
            words = topics[n % 12]
            papers.append({"key": f"k{n}", "title": " ".join(rng.sample(words, 8)),
                           "abstract": " ".join(rng.sample(words, 30) + rng.sample(common, 120)),
                           "keywords": rng.sample(words, 4), "family": f"f{n % 5}",
                           "ideas": [{"idea": f"I{n % 40}", "why": ""}]})
        cocited = [[f"k{n}", f"k{n + 12}", f"k{n + 24}"] for n in range(0, 450, 3)]
        start = time.perf_counter()
        answer = cluster_papers(papers, cocited)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 2.0)
        self.assertGreater(len(answer["clusters"]), 1)


class PanelWiringTests(unittest.TestCase):
    panel = PANEL.read_text(encoding="utf-8")
    page = (STATIC / "index.html").read_text(encoding="utf-8")

    def test_the_page_holds_the_bar_inside_the_view(self) -> None:
        view = self.page[self.page.index('id="citedPapersContainer"'):self.page.index('id="citedPapersList"')]
        self.assertIn('id="citedClustersBar"', view)
        self.assertLess(view.index('id="citedClustersBar"'), view.index('id="citedPapersCount"'))
        self.assertIn(".paper-explorer__clusters", self.page)

    def test_the_catalogues_carry_the_new_keys(self) -> None:
        for lang in ("en", "es"):
            text = (STATIC / "i18n" / f"{lang}.js").read_text(encoding="utf-8")
            for key in ("explorer.unclustered", "explorer.clustersNote", "explorer.clustersLabel",
                        "explorer.badAnswer"):
                self.assertIn(f'"{key}"', text)
        self.assertRegex(self.panel, r"t\('explorer\.unclustered'\)")
        self.assertRegex(self.panel, r"t\('explorer\.clustersNote'\)")

    def test_the_references_warning_names_its_file(self) -> None:
        self.assertRegex(self.panel, r"references:\s*'paper/\.paper-writing/references\.json'")

    def test_cluster_text_is_escaped(self) -> None:
        self.assertIn("esc(cluster.label)", self.panel)
        self.assertIn("esc(paper.cluster.label)", self.panel)


PRELUDE = r"""
const fs = require('fs');
const elements = {};
const element = (id) => elements[id] ||= { id, value: '', innerHTML: '', textContent: '', hidden: false, listeners: {},
  addEventListener(type, fn) { this.listeners[type] = fn; } };
const ready = [];
const documentListeners = {};
global.document = {
  getElementById: element,
  addEventListener(type, fn) { if (type === 'DOMContentLoaded') ready.push(fn); else documentListeners[type] = fn; },
};
let now = 1000;
let timers = [];
let nextTimer = 1;
Date.now = () => now;
global.setTimeout = (fn, ms) => { timers.push({ id: nextTimer, at: now + ms, fn }); return nextTimer++; };
global.clearTimeout = (id) => { timers = timers.filter((timer) => timer.id !== id); };
const advance = (ms) => {
  const end = now + ms;
  for (;;) {
    const due = timers.filter((timer) => timer.at <= end).sort((a, b) => a.at - b.at)[0];
    if (!due) break;
    timers = timers.filter((timer) => timer !== due);
    now = due.at;
    due.fn();
  }
  now = end;
};
global.currentGraphKind = 'cited';
const switched = [];
const switchGraph = (kind) => { switched.push(kind); global.currentGraphKind = kind; };
let language = 'en';
global.window = { t: (key) => `${language}:${key}`, switchGraph, location: { origin: 'http://panel', href: 'http://panel/' } };
Object.defineProperty(global, 'navigator', { value: { clipboard: { writeText: async () => {} } } });
const reply = (value) => ({ ok: true, json: async () => JSON.parse(JSON.stringify(value)) });
const body = JSON.parse(process.argv[3]);
global.fetch = async () => reply(body);
eval(fs.readFileSync(process.argv[2], 'utf8'));
ready.forEach((fn) => fn());
const list = element('citedPapersList');
const bar = element('citedClustersBar');
const shown = () => [...list.innerHTML.matchAll(/data-key="([^"]+)"/g)].map((m) => m[1]);
const search = (text) => { element('citedSearchInput').value = text; window.filterCitedPapers(); return shown(); };
const chip = (cluster) => bar.listeners.click({ target: { closest: () => ({ dataset: { cluster } }) } });
const act = (item) => list.listeners.click({ target: { closest: () => (item.dataset ? item : { dataset: item }) } });
// The live document of the graph frame, as locate reads it.
const graph = (state, nodes, path = '/api/atlas/manuscript-graph/view') => {
  const doc = { readyState: state, location: { pathname: path }, selected: [],
    querySelector: () => (nodes ? {} : null),
    querySelectorAll: () => doc.selected.map((id) => ({ dataset: { id } })) };
  return doc;
};
const frame = element('graphIframe');
frame.src = 'http://panel/api/atlas/manuscript-graph/view';
const sent = [];
frame.contentWindow = { postMessage: (message) => {
  sent.push(message.id);
  if (frame.contentDocument.selects) frame.contentDocument.selected = [message.id];
} };
const finish = (value) => console.log(JSON.stringify(value));
"""


def paper(key: str, **fields) -> dict:
    return {"key": key, "title": f"Title {key}", "authors": [], "order": ord(key[0]), "cites": 1, "in_pool": False,
            "has_entry": True, "sections": [], "claims": [], "ideas": [], "keywords": [], **fields}


def answer_with(*papers: dict, **fields) -> dict:
    return {"summary": {"missing_entries": [], "with_link": 0, "with_abstract": 0, "in_pool": 0},
            "warnings": [], "cite_source": "main.tex", "papers": list(papers), **fields}


@unittest.skipUnless(shutil.which("node"), "node is required to run the panel")
class PanelBehaviorTests(unittest.TestCase):
    """The real panel script against a stub DOM, as ``test_dashboard_i18n`` runs its runtime."""

    def run_panel(self, body: dict | None, scenario: str) -> dict:
        with tempfile.TemporaryDirectory() as scratch:
            script = Path(scratch) / "harness.js"
            script.write_text(f"{PRELUDE}(async () => {{ {scenario} }})();", encoding="utf-8")
            done = subprocess.run(["node", str(script), str(PANEL), json.dumps(body)],
                                  capture_output=True, text=True, check=True)
        return json.loads(done.stdout)

    def clustered(self) -> dict:
        return answer_with(paper("a"), paper("b"), paper("c"), paper("d"), clusters={
            "method": "m", "signals": ["text"], "unclustered": ["d"], "clusters": [
                {"id": "c1", "label": "<one> \u00b7 two", "terms": ["<one>", "two", "hiddenterm"], "keys": ["a", "b"],
                 "size": 2, "signals": {}},
                {"id": "c2", "label": "three \u00b7 four", "terms": ["three", "four"], "keys": ["c"],
                 "size": 1, "signals": {}}]})

    def test_without_clusters_the_bar_stays_hidden(self) -> None:
        for body in (answer_with(paper("a")), answer_with(paper("a"), clusters=None),
                     answer_with(paper("a"), clusters={"clusters": [], "unclustered": ["a"]})):
            out = self.run_panel(body, "await window.loadCitedPapers(); finish({hidden: bar.hidden, all: shown()});")
            self.assertTrue(out["hidden"])
            self.assertEqual(out["all"], ["a"])

    def test_chips_filter_toggle_combine_and_reset(self) -> None:
        out = self.run_panel(self.clustered(), """
            await window.loadCitedPapers();
            const out = {hidden: bar.hidden, all: shown()};
            chip('c1'); out.first = shown();
            out.combined = search('nomatchanywhere');
            search('');
            chip('c1'); out.toggled = shown();
            chip('unclustered'); out.loose = shown();
            window.resetCitedFilters(); out.reset = shown();
            out.byTerm = search('hiddenterm');
            finish(out);""")
        self.assertFalse(out["hidden"])
        self.assertEqual(out["all"], ["a", "b", "c", "d"])
        self.assertEqual(out["first"], ["a", "b"])
        self.assertEqual(out["combined"], [])
        self.assertEqual(out["toggled"], ["a", "b", "c", "d"])
        self.assertEqual(out["loose"], ["d"])
        self.assertEqual(out["reset"], ["a", "b", "c", "d"])
        self.assertEqual(out["byTerm"], ["a", "b"])

    def test_the_bar_shows_each_chip_the_note_and_escapes_text(self) -> None:
        out = self.run_panel(self.clustered(), """
            await window.loadCitedPapers();
            const card = list.innerHTML;
            chip('c1');
            finish({bar: bar.innerHTML, card});""")
        self.assertIn("&lt;one&gt;", out["bar"])
        self.assertNotIn("<one>", out["bar"])
        self.assertIn("explorer.clustersNote", out["bar"])
        self.assertIn("explorer.unclustered", out["bar"])
        self.assertEqual(len(re.findall(r"data-cluster=", out["bar"])), 3)
        self.assertRegex(out["bar"], r'data-cluster="c1"[^>]*aria-pressed="true"')
        self.assertIn("&lt;one&gt; \u00b7 two", out["card"])

    def test_a_chosen_cluster_that_a_reload_removes_stops_filtering(self) -> None:
        out = self.run_panel(self.clustered(), """
            await window.loadCitedPapers();
            chip('c1');
            global.fetch = async () => reply({...body, clusters: undefined});
            await window.loadCitedPapers();
            finish({all: shown(), hidden: bar.hidden});""")
        self.assertEqual(out, {"all": ["a", "b", "c", "d"], "hidden": True})

    def test_search_filters_and_ignores_accents_and_case(self) -> None:
        body = answer_with(paper("a", title="M\u00e9xico y Per\u00fa", in_pool=True),
                           paper("b", title="Oslo", sections=[{"title": "Intro", "count": 1}]))
        out = self.run_panel(body, """
            await window.loadCitedPapers();
            const out = {folded: search('MEXICO peru'), none: search('atlantis')};
            search('');
            element('citedOriginFilter').value = 'pool'; window.filterCitedPapers(); out.pool = shown();
            element('citedOriginFilter').value = 'outside'; window.filterCitedPapers(); out.outside = shown();
            element('citedOriginFilter').value = '';
            element('citedSectionFilter').value = 'Intro'; window.filterCitedPapers(); out.section = shown();
            finish(out);""")
        self.assertEqual(out, {"folded": ["a"], "none": [], "pool": ["a"], "outside": ["b"], "section": ["b"]})

    def test_a_slow_older_load_never_replaces_a_newer_one(self) -> None:
        out = self.run_panel(answer_with(paper("a")), """
            let release;
            const old = reply({...body, papers: [{...body.papers[0], key: 'stale'}]});
            global.fetch = () => new Promise((resolve) => { release = () => resolve(old); });
            const slow = window.loadCitedPapers();
            global.fetch = async () => reply(body);
            await window.loadCitedPapers();
            release();
            await slow;
            finish({all: shown()});""")
        self.assertEqual(out["all"], ["a"])

    def test_a_malformed_answer_shows_one_readable_error(self) -> None:
        for body in ({}, {"papers": "x"}, None):
            out = self.run_panel(body, """
                await window.loadCitedPapers();
                finish({list: list.innerHTML, hidden: bar.hidden});""")
            self.assertIn("explorer.loadError", out["list"])
            self.assertTrue(out["hidden"])

    def test_an_answer_with_no_summary_still_lists_its_papers(self) -> None:
        out = self.run_panel({"papers": [paper("a"), None]}, """
            await window.loadCitedPapers();
            finish({all: shown()});""")
        self.assertEqual(out["all"], ["a"])

    def test_locate_waits_for_the_graph_document(self) -> None:
        out = self.run_panel(None, """
            frame.contentDocument = graph('complete', false, '/api/atlas/view');
            act({action: 'locate', node: 'n1'});
            const out = {kinds: switched.slice(), early: sent.length};
            advance(300);
            frame.contentDocument = graph('loading', false);
            advance(300);
            out.loading = sent.length;
            frame.contentDocument = graph('complete', true);
            frame.contentDocument.selects = true;
            advance(100);
            out.ready = sent.slice();
            advance(2000);
            out.after = sent.length;
            out.pending = timers.length;
            finish(out);""")
        self.assertEqual(out, {"kinds": ["summary"], "early": 0, "loading": 0, "ready": ["n1"], "after": 1, "pending": 0})

    def test_locate_tells_a_reloaded_document_once_and_gives_up_in_time(self) -> None:
        out = self.run_panel(None, """
            frame.contentDocument = graph('complete', true);
            act({action: 'locate', node: 'n1'});
            const out = {first: sent.length};
            advance(500);
            out.same = sent.length;
            frame.contentDocument = graph('complete', true);
            advance(100);
            out.reloaded = sent.length;
            advance(10000);
            out.pending = timers.length;
            frame.contentDocument = graph('complete', true);
            advance(1000);
            out.late = sent.length;
            finish(out);""")
        self.assertEqual(out, {"first": 1, "same": 1, "reloaded": 2, "pending": 0, "late": 2})

    def test_a_newer_locate_or_a_view_switch_cancels_the_pending_one(self) -> None:
        out = self.run_panel(None, """
            frame.contentDocument = graph('loading', false);
            act({action: 'locate', node: 'old'});
            act({action: 'locate', node: 'new'});
            frame.contentDocument = graph('complete', true);
            advance(100);
            const out = {newer: sent.slice()};
            sent.length = 0;
            frame.contentDocument = graph('loading', false);
            act({action: 'locate', node: 'gone'});
            switchGraph('atlas');
            frame.contentDocument = graph('complete', true);
            advance(1000);
            out.left = sent.slice();
            out.pending = timers.length;
            finish(out);""")
        self.assertEqual(out, {"newer": ["new"], "left": [], "pending": 0})

    def test_a_second_copy_click_never_freezes_the_copied_label(self) -> None:
        out = self.run_panel(None, """
            const button = {dataset: {action: 'copy', key: 'a'}, textContent: 'en:explorer.copy'};
            const settle = async () => { await new Promise((done) => setImmediate(done)); };
            act(button); await settle();
            const out = {copied: button.textContent};
            advance(600);
            act(button); await settle();
            advance(700);
            out.held = button.textContent;
            language = 'es';
            advance(600);
            out.restored = button.textContent;
            global.navigator.clipboard.writeText = async () => { throw new Error('denied'); };
            act(button); await settle();
            out.failed = button.textContent;
            finish(out);""")
        self.assertEqual(out, {"copied": "en:explorer.copied", "held": "en:explorer.copied",
                               "restored": "es:explorer.copy", "failed": "es:explorer.copyFailed"})


if __name__ == "__main__":
    unittest.main()
