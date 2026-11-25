"""Steps 2 and 5 of idea shaping: the author's profile from OpenAlex
(``profile.py``) and the candidate topics with their evidence (``topics.py``).
OpenAlex is always a fake fetcher (or a patched ``urlopen``); no network."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from unittest import mock

from skills._core.idea import bank, brief, idea_cli, profile, topics

AUTHOR = {
    "id": "https://openalex.org/A5023888391", "orcid": "https://orcid.org/0000-0002-1825-0097",
    "display_name": "Ada Lovelace", "works_count": 42,
    "topics": [{"display_name": "EEG signal analysis", "count": 9},
               {"display_name": "Brain-computer interfaces", "count": 14},
               {"display_name": "Graph neural networks", "count": 3}],
}


class FakeOpenAlex:
    def __init__(self, count: int = 30, offline: bool = False) -> None:
        self.count, self.offline = count, offline
        self.calls: list[str] = []

    def __call__(self, url: str):
        self.calls.append(url)
        if self.offline:
            raise urllib.error.URLError("network is unreachable")
        if "/authors/orcid:" in url or "/authors/A" in url:
            return AUTHOR
        if "/authors?" in url:
            return {"results": [AUTHOR]}
        if "/works?" in url:
            return {"meta": {"count": self.count}}
        raise AssertionError(f"unexpected OpenAlex request {url}")


class ProfileTests(unittest.TestCase):
    def test_orcid_finds_the_author_and_their_topics(self) -> None:
        fake = FakeOpenAlex()
        result = profile.lookup(orcid="https://orcid.org/0000-0002-1825-0097", fetch=fake)
        self.assertEqual(fake.calls, ["https://api.openalex.org/authors/orcid:0000-0002-1825-0097"])
        self.assertEqual(result["source"], "openalex")
        self.assertEqual((result["display_name"], result["openalex_author"], result["works_count"]),
                         ("Ada Lovelace", "A5023888391", 42))
        self.assertEqual(result["topics"][0], {"name": "Brain-computer interfaces", "count": 14})
        self.assertIsNone(result["reason"])

    def test_openalex_id_from_its_url(self) -> None:
        fake = FakeOpenAlex()
        result = profile.lookup(openalex_author="https://openalex.org/a5023888391", fetch=fake)
        self.assertEqual(fake.calls, ["https://api.openalex.org/authors/A5023888391"])
        self.assertEqual(result["orcid"], "0000-0002-1825-0097")

    def test_a_scholar_link_is_only_read_for_a_name(self) -> None:
        fake = FakeOpenAlex()
        link = "https://scholar.google.com/citations?view_op=search_authors&mauthors=Ada+Lovelace&hl=en"
        result = profile.lookup(scholar_url=link, fetch=fake)
        self.assertEqual(len(fake.calls), 1)
        self.assertIn("/authors?search=Ada+Lovelace", fake.calls[0])
        self.assertNotIn("scholar.google", fake.calls[0])
        self.assertEqual((result["source"], result["scholar_url"]), ("openalex", link))
        self.assertEqual(profile.scholar_name('https://scholar.google.com/scholar?q=author:"Grace Hopper"'),
                         "Grace Hopper")

    def test_a_scholar_profile_link_without_a_name_asks_for_one(self) -> None:
        fake = FakeOpenAlex()
        result = profile.lookup(scholar_url="https://scholar.google.com/citations?user=AbC123&hl=en", fetch=fake)
        self.assertEqual(fake.calls, [])
        self.assertEqual(result["source"], "none")
        self.assertIn("carries no author name", result["reason"])

    def test_offline_answers_source_none_with_a_reason(self) -> None:
        result = profile.lookup(name="Ada Lovelace", fetch=FakeOpenAlex(offline=True))
        self.assertEqual(result["source"], "none")
        self.assertIn("OpenAlex could not be reached", result["reason"])
        self.assertEqual(result["topics"], [])

    def test_a_malformed_orcid_is_refused_without_a_request(self) -> None:
        fake = FakeOpenAlex()
        result = profile.lookup(orcid="1234", fetch=fake)
        self.assertEqual((fake.calls, result["source"]), ([], "none"))
        self.assertIn("not an ORCID", result["reason"])

    def test_identify_reads_one_free_answer(self) -> None:
        self.assertEqual(profile.identify("0000-0002-1825-0097"), {"orcid": "0000-0002-1825-0097"})
        self.assertEqual(profile.identify("A5023888391"), {"openalex_author": "A5023888391"})
        self.assertEqual(profile.identify("https://scholar.google.com/citations?user=x"),
                         {"scholar_url": "https://scholar.google.com/citations?user=x"})
        self.assertEqual(profile.identify("  Ada   Lovelace "), {"name": "Ada Lovelace"})

    def test_the_operator_key_is_sent_but_never_stored(self) -> None:
        captured: list[str] = []

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def urlopen(request, timeout=None):
            captured.append(request.full_url)
            return Response(json.dumps({"meta": {"count": 7}}).encode())

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"OPENALEX_API_KEY": "secret-key-123456"}), \
                mock.patch.object(profile.urllib.request, "urlopen", urlopen):
            root = Path(tmp)
            (root / ".papersmith").mkdir()
            brief.record(root, "interests", {"keywords": ["eeg", "domain shift"]})
            proposed = topics.propose(root, 1)
        self.assertIn("api_key=secret-key-123456", captured[0])
        self.assertNotIn("secret", json.dumps(proposed))


class TopicsTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / ".papersmith").mkdir()
        self.fake = FakeOpenAlex(count=12)
        patcher = mock.patch.object(profile, "FETCH", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        connect = mock.patch.object(bank, "CONNECT", self.forbidden)
        connect.start()
        self.addCleanup(connect.stop)
        bank.choose(self.root, "none")
        brief.record(self.root, "profile", profile.lookup(orcid="0000-0002-1825-0097"))
        brief.record(self.root, "experience", {"methods": ["graph neural networks"]})
        brief.record(self.root, "interests", {"keywords": ["eeg", "domain shift", "transfer learning"],
                                              "domain": "clinical neurology"})

    @staticmethod
    def forbidden(*args, **kwargs):
        raise AssertionError("no bank may be contacted when the choice is none")

    def test_three_topics_carry_evidence_with_their_sources(self) -> None:
        proposed = topics.propose(self.root, today=date(2026, 11, 25))
        self.assertEqual([t["id"] for t in proposed], ["t1", "t2", "t3"])
        self.assertEqual(proposed[0]["title"], "eeg and domain shift in clinical neurology")
        self.assertEqual(proposed[1]["title"], "eeg applied to Brain-computer interfaces")
        sources = [{e["source"] for e in t["evidence"]} for t in proposed]
        self.assertEqual(sources[0], {"operator", "openalex"})
        self.assertIn("profile", sources[1])
        for topic in proposed:
            volume = [e for e in topic["evidence"] if e["source"] == "openalex"][0]
            self.assertEqual(volume["count"], 12)
            self.assertIn("since 2022", volume["detail"])
            self.assertIn("possible gap", volume["detail"])
            self.assertIn("from_publication_date%3A2022-01-01", volume["url"])
            self.assertTrue(topic["rationale"])
        self.assertFalse([e for t in proposed for e in t["evidence"] if e["source"].startswith("bank:")])
        self.assertEqual(brief.load(self.root)["topics"], proposed)
        self.assertEqual(topics.propose(self.root, today=date(2026, 11, 25)), proposed, "deterministic")

    def test_offline_topics_keep_their_other_evidence(self) -> None:
        self.fake.offline = True
        proposed = topics.propose(self.root)
        self.assertEqual(len(proposed), 3)
        self.assertFalse([e for t in proposed for e in t["evidence"] if e["source"] == "openalex"])
        self.assertEqual(len([c for c in self.fake.calls if "/works?" in c]), 1, "one failed request, not three")

    def test_pick_by_number_or_id_and_combine(self) -> None:
        topics.propose(self.root)
        self.assertEqual(topics.choose(self.root, "1,t3", "focus on small cohorts"),
                         {"topic_ids": ["t1", "t3"], "note": "focus on small cohorts"})
        with self.assertRaises(brief.IdeaError) as ctx:
            topics.choose(self.root, "t9")
        self.assertEqual(ctx.exception.code, "TOPIC_UNKNOWN")
        topics.propose(self.root)
        self.assertEqual(brief.load(self.root)["chosen"]["topic_ids"], [], "a new proposal clears the pick")

    def test_topics_verb_proposes_and_chooses(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = idea_cli.main(["topics", str(self.root), "--propose", "--choose", "2", "--json"])
        body = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(len(body["topics"]), 3)
        self.assertEqual(body["chosen"]["topic_ids"], ["t2"])

    def test_profile_verb_records_the_lookup(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = idea_cli.main(["profile", str(self.root), "--name", "Ada Lovelace"])
        self.assertEqual(code, 0)
        self.assertIn("Ada Lovelace (OpenAlex A5023888391, 42 works)", out.getvalue())
        self.assertEqual(brief.load(self.root)["profile"]["display_name"], "Ada Lovelace")


if __name__ == "__main__":
    unittest.main()
