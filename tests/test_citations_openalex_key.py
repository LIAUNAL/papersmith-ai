"""`citations_cli rank`'s accepted-lab lookup sends the operator's OpenAlex key.

The lab check stays OpenAlex plus the operator (Asta gives affiliations as free
text, never ROR ids). It now rides the operator's OpenAlex key when one is
configured, for its larger budget; without one the request is byte-identical to
before, and a failure still returns `None`, so no key reaches a message.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skills._core.results import citations_cli

from test_api_keys import load_api_keys

api_keys = load_api_keys()
KEY = "openalex-key-ABCDEFGH"
WORK = {"publication_year": 2023, "authorships": [
    {"institutions": [{"ror": "https://ror.org/00njsd438"}]}]}


class _Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class OpenAlexKeyTests(unittest.TestCase):
    def setUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        patcher = mock.patch.dict(os.environ, {api_keys.STORE_DIR_ENV: str(Path(holder.name) / "keys")})
        patcher.start()
        self.addCleanup(patcher.stop)
        for variable in ("ASTA_API_KEY", "OPENALEX_API_KEY"):
            os.environ.pop(variable, None)
        self.urls: list[str] = []

    def fake(self, answer):
        def urlopen(request, timeout=None):
            self.urls.append(request.full_url)
            if isinstance(answer, Exception):
                raise answer
            return _Answer(json.dumps(answer).encode("utf-8"))
        return mock.patch.object(citations_cli.urllib.request, "urlopen", side_effect=urlopen)

    def test_without_a_key_the_request_is_unchanged(self) -> None:
        with self.fake(WORK):
            found = citations_cli._openalex_institutions("2401.00001")
        assert found == {"rors": ["00njsd438"], "year": 2023}
        assert self.urls == ["https://api.openalex.org/works/doi:10.48550/arxiv.2401.00001"
                             "?select=publication_year,authorships"]

    def test_a_configured_key_rides_the_lookup(self) -> None:
        api_keys.store("openalex", KEY)
        with self.fake(WORK):
            citations_cli._openalex_institutions("2401.00001")
        assert self.urls[0].endswith(f"&api_key={KEY}")

    def test_a_refused_key_is_a_quiet_none(self) -> None:
        api_keys.store("openalex", KEY)
        import urllib.error

        refused = urllib.error.HTTPError("https://api.openalex.org/x", 401, "no", {}, None)
        with self.fake(refused):
            assert citations_cli._openalex_institutions("2401.00001") is None


if __name__ == "__main__":
    unittest.main()
