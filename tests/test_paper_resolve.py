"""paper-writing resolve: arXiv normalization and clean refusals.

Stdlib-only `unittest`. The transport is stubbed, so no test touches the
network: the prefix defect was measured live (`id_list=arXiv:1512.03385`
-> 706-byte entry-less feed; the bare id -> 2814 bytes with `<entry>`),
and these pin the corrected behavior.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path

FORGE_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = FORGE_ROOT / "skills" / "paper-writing" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
sys.path.insert(0, str(FORGE_ROOT / "skills" / "_core" / "implementation"))
import paper_resolve  # noqa: E402
from impl_refusals import Refused  # noqa: E402

CONFIG = {
    "paper_writing": {
        "roles": {"resolution": ["arxiv"], "full-text": [], "discovery": []},
        "contact": "",
    }
}

EMPTY_FEED = (
    b"<?xml version='1.0' encoding='UTF-8'?>\n"
    b'<feed xmlns="http://www.w3.org/2005/Atom"><id>x</id><title>empty</title></feed>'
)

ENTRY_FEED = (
    b"<?xml version='1.0' encoding='UTF-8'?>\n"
    b'<feed xmlns="http://www.w3.org/2005/Atom">\n'
    b"<entry><title>Deep Residual Learning</title>"
    b"<summary>We present a residual  learning framework.</summary>"
    b'<link href="https://arxiv.org/pdf/1512.03385" type="application/pdf"/>'
    b"<author><name>Kaiming He</name></author></entry>\n"
    b"</feed>"
)


def id_list_of(url: str) -> str:
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["id_list"][0]


class ArxivIdentifierTests(unittest.TestCase):
    """The `arXiv:` prefix users paste is not part of the API's id."""

    def stub_get(self, payload: bytes) -> list[str]:
        seen: list[str] = []
        original = paper_resolve._get

        def fake(url: str, *, config: dict) -> bytes:
            seen.append(url)
            return payload

        paper_resolve._get = fake
        self.addCleanup(setattr, paper_resolve, "_get", original)
        return seen

    def test_prefix_variants_query_the_bare_id(self) -> None:
        for identifier in ("arXiv:1512.03385", "arxiv:1512.03385", "  1512.03385  "):
            with self.subTest(identifier=identifier):
                assert id_list_of(paper_resolve._arxiv_url(identifier)) == "1512.03385"

    def test_empty_feed_refuses_identifier_unresolved(self) -> None:
        seen = self.stub_get(EMPTY_FEED)
        with self.assertRaises(Refused) as ctx:
            paper_resolve.resolve_identifier(
                "arXiv:1512.03385", resolver="arxiv", role="resolution", config=CONFIG
            )
        assert ctx.exception.code == "IDENTIFIER_UNRESOLVED", ctx.exception.code
        assert len(seen) == 1 and id_list_of(seen[0]) == "1512.03385", seen

    def test_entry_feed_resolves_with_measured_fields(self) -> None:
        seen = self.stub_get(ENTRY_FEED)
        result = paper_resolve.resolve_identifier(
            "arXiv:1512.03385", resolver="arxiv", role="resolution", config=CONFIG
        )
        assert id_list_of(seen[0]) == "1512.03385", seen
        assert result["title"] == "Deep Residual Learning", result
        assert result["abstract"] == "We present a residual learning framework.", result
        assert result["venue"] == "arXiv", result
        assert result["full_text_url"] == "https://arxiv.org/pdf/1512.03385", result
        assert result["authors"] == ["Kaiming He"], result



def arxiv_feed(published: bytes | None) -> bytes:
    stamp = b"" if published is None else b"<published>" + published + b"</published>"
    return (
        b"<?xml version='1.0' encoding='UTF-8'?>\n"
        b'<feed xmlns="http://www.w3.org/2005/Atom">\n'
        b"<entry><title>Deep Residual Learning</title>" + stamp +
        b"<summary>We present a residual learning framework.</summary></entry>\n"
        b"</feed>"
    )


def crossref_message(**dates) -> bytes:
    message = {"DOI": "10.1000/example", "title": ["Example"], **dates}
    return json.dumps({"status": "ok", "message": message}).encode()


class PublicationYearTests(unittest.TestCase):
    """The year is read off the response actually received -- arXiv's
    `<published>`, Crossref's `issued` (else `published`) date-parts -- and
    stays `None` when the response carries no readable one, never guessed."""

    def test_arxiv_year_comes_from_published(self) -> None:
        cases = {b"2015-12-10T17:38:12Z": 2015, None: None, b"": None,
                 b"not a date": None}
        for published, expected in cases.items():
            with self.subTest(published=published):
                self.assertEqual(paper_resolve._parse_arxiv(arxiv_feed(published))["year"],
                                 expected)

    def test_crossref_year_comes_from_issued_then_published(self) -> None:
        cases = [
            ({"issued": {"date-parts": [[2016, 6, 27]]}}, 2016),
            ({"issued": {"date-parts": [[2016]]},
              "published": {"date-parts": [[2015, 1]]}}, 2016),
            ({"published": {"date-parts": [[2014, 3]]}}, 2014),
            ({"issued": {"date-parts": [[None]]},
              "published": {"date-parts": [[2013]]}}, 2013),
            ({"issued": {"date-parts": [[None]]}}, None),
            ({"issued": {"date-parts": []}}, None),
            ({"issued": "2016"}, None),
            ({"issued": {"date-parts": [["2016"]]}}, None),
            ({"issued": {"date-parts": [[True]]}}, None),
            ({}, None),
        ]
        for dates, expected in cases:
            with self.subTest(dates=dates):
                self.assertEqual(paper_resolve._parse_crossref(crossref_message(**dates))["year"],
                                 expected)

    def test_the_cache_key_is_the_response_digest_not_the_parsed_record(self) -> None:
        """A cache written before the year was read (`year: null`) keeps
        reading under the same key: the key is the digest of the raw
        response, which reading one more field does not move."""
        raw = arxiv_feed(b"2015-12-10T17:38:12Z")
        original = paper_resolve._get
        paper_resolve._get = lambda url, *, config: raw
        self.addCleanup(setattr, paper_resolve, "_get", original)
        fresh = paper_resolve.resolve_identifier(
            "1512.03385", resolver="arxiv", role="resolution", config=CONFIG)
        self.assertEqual(fresh["metadata_digest"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(fresh["year"], 2015)
        with tempfile.TemporaryDirectory() as box:
            paper_dir = Path(box)
            legacy = {**fresh, "year": None}
            paper_resolve.cache_metadata(paper_dir, legacy)
            read = paper_resolve.read_cached_metadata(paper_dir, fresh["metadata_digest"])
            self.assertEqual(read, legacy)

class SemanticScholarResolverTests(unittest.TestCase):
    """The Semantic Scholar Graph API connector: keyless, scheme-prefixed,
    same seven metadata fields the other parsers answer (S2 of
    odd/tasks/spark-to-paper-enhancements.md). The transport is stubbed."""

    CONFIG = {
        "paper_writing": {
            "roles": {"resolution": ["semantic-scholar"], "full-text": [], "discovery": []},
            "contact": "",
        }
    }

    RECORD = json.dumps({
        "paperId": "abc123", "title": "Deep Residual Learning",
        "year": 2015, "venue": "arXiv", "abstract": "We present a residual learning framework.",
        "authors": [{"name": "Kaiming He"}, {"name": None}, {"name": " Xiangyu Zhang "}],
        "externalIds": {"DOI": "10.1109/CVPR.2016.90", "ArXiv": "1512.03385"},
        "openAccessPdf": {"url": "https://arxiv.org/pdf/1512.03385"},
    }).encode()

    def stub_get(self, payload: bytes) -> list[str]:
        seen: list[str] = []
        original = paper_resolve._get

        def fake(url: str, *, config: dict) -> bytes:
            seen.append(url)
            return payload

        paper_resolve._get = fake
        self.addCleanup(setattr, paper_resolve, "_get", original)
        return seen

    def test_a_bare_doi_queries_the_doi_prefixed_endpoint(self) -> None:
        seen = self.stub_get(self.RECORD)
        result = paper_resolve.resolve_identifier(
            "10.1109/CVPR.2016.90", resolver="semantic-scholar", role="resolution",
            config=self.CONFIG)
        assert "graph/v1/paper/DOI:10.1109%2FCVPR.2016.90" in seen[0].replace("%2F", "%2F") or \
            "graph/v1/paper/DOI:10.1109/CVPR.2016.90" in seen[0], seen
        assert "x-api-key" not in seen[0]
        assert result["title"] == "Deep Residual Learning", result
        assert result["doi"] == "10.1109/CVPR.2016.90", result
        assert result["year"] == 2015, result
        assert result["venue"] == "arXiv", result
        assert result["authors"] == ["Kaiming He", "Xiangyu Zhang"], result
        assert result["abstract"].startswith("We present"), result
        assert result["full_text_url"] == "https://arxiv.org/pdf/1512.03385", result

    def test_an_arxiv_identifier_queries_the_arxiv_scheme(self) -> None:
        seen = self.stub_get(self.RECORD)
        paper_resolve.resolve_identifier(
            "arXiv:1512.03385", resolver="semantic-scholar", role="resolution",
            config=self.CONFIG)
        assert "graph/v1/paper/ARXIV:1512.03385" in seen[0], seen

    def test_not_configured_for_the_role_refuses_by_name(self) -> None:
        with self.assertRaises(Refused) as ctx:
            paper_resolve.resolve_identifier(
                "10.1109/CVPR.2016.90", resolver="semantic-scholar", role="resolution",
                config=CONFIG)
        assert ctx.exception.code == "RESOLVER_ROLE_EMPTY", ctx.exception.code

    def test_transport_failure_refuses_resolver_unreachable(self) -> None:
        original = paper_resolve._get

        def fake(url: str, *, config: dict) -> bytes:
            raise paper_resolve._Unreachable("https://api.semanticscholar.org: down")

        paper_resolve._get = fake
        self.addCleanup(setattr, paper_resolve, "_get", original)
        with self.assertRaises(Refused) as ctx:
            paper_resolve.resolve_identifier(
                "10.1109/CVPR.2016.90", resolver="semantic-scholar", role="resolution",
                config=self.CONFIG)
        assert ctx.exception.code == "RESOLVER_UNREACHABLE", ctx.exception.code

    def test_semantic_scholar_is_a_registered_resolver(self) -> None:
        assert "semantic-scholar" in paper_resolve.RESOLVERS


if __name__ == "__main__":
    unittest.main()
