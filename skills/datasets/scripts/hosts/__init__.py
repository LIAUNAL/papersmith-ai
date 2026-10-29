"""Remote dataset hosts, discovered rather than listed.

Every module in this package is one host. It declares ``NAME`` and a
``search(query, http, limit)`` that returns hits as
``{"ref", "title", "url", "license"}`` dicts, and may declare a ``PUBLISHER``
(an object with ``create_argv``, ``version_argv``, ``status_argv``,
``validate_metadata`` and ``mount_hint``) when the host can receive an upload,
and may declare ``ref_from_url(url)`` -> ``"owner/slug"`` or ``None`` when a
job's runner can attach one of its public dataset pages by ref.

The front door (``datasets_cli.py``) never names a host: it asks
:func:`discover` what is here, so a host is added by adding one file, and the
one service this skill publishes to is named only inside its own module.

The HTTP layer is a callable ``http(method, url, body=None, headers=None,
timeout=20) -> (status, text)``; :func:`urllib_http` is the default and tests
inject their own, so no test opens a socket.
"""

from __future__ import annotations

import importlib
import pkgutil
import urllib.error
import urllib.request
from types import ModuleType

USER_AGENT = "papersmith-datasets/1"


def urllib_http(method, url, body=None, headers=None, timeout=20):
    """The default HTTP layer: ``(status, text)``; a non-2xx answer raises."""
    data = body.encode("utf-8") if isinstance(body, str) else body
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise OSError(f"HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise OSError(f"unreachable: {exc.reason}") from exc


def discover() -> dict[str, ModuleType]:
    """``{NAME: module}`` for every host module in this package, sorted."""
    found: dict[str, ModuleType] = {}
    for info in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"{__name__}.{info.name}")
        name = getattr(module, "NAME", None)
        if isinstance(name, str) and callable(getattr(module, "search", None)):
            found[name] = module
    return dict(sorted(found.items()))


def publisher() -> tuple[str, object] | None:
    """The one host that can receive an upload, as ``(NAME, PUBLISHER)``."""
    for name, module in discover().items():
        candidate = getattr(module, "PUBLISHER", None)
        if candidate is not None:
            return name, candidate
    return None


def ref_from_url(url) -> tuple[str, str] | None:
    """``(NAME, ref)`` for the host whose ``ref_from_url`` recognizes ``url``
    as one of its public dataset pages, or ``None``."""
    for name, module in discover().items():
        parse = getattr(module, "ref_from_url", None)
        ref = parse(url) if callable(parse) else None
        if ref:
            return name, ref
    return None
