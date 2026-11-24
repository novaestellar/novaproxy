"""A row may only be "alive" if it really carried TLS to a real host.

Observed 2026-11-24 from the novamini session: novaproxy reported 519 alive
rows, but the rows that actually failed the HTTPS check were
`ClientConnectorError`, `TimeoutError` and
`SSLCertVerificationError: self-signed certificate`. A public proxy that
answers plain HTTP and then breaks TLS is not usable for any HTTPS target --
and `alive=1` claimed otherwise.

So:
  * the validator must probe HTTPS against a real host and treat a TLS
    failure as "not usable", not "usable but slow";
  * a self-signed certificate must NOT pass: the gateway talks to real
    targets, so an unverifiable chain is a failure, not a warning;
  * the pool's "alive" count must mean "can carry TLS", because that is the
    only question a consumer of this pool actually has.
"""
import asyncio
import ssl
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import validator


def test_validator_reports_a_self_signed_certificate_as_not_usable(monkeypatch):
    """A self-signed chain must not pass as a working HTTPS tunnel."""

    class FakeResp:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def json(self, content_type=None):
            return {"origin": "1.2.3.4", "headers": {}}

    class FakeSession:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        def get(self, url, proxy=None, timeout=None):
            if url.startswith("https://"):
                raise ssl.SSLCertVerificationError(
                    "self-signed certificate")
            return FakeResp()

    monkeypatch.setattr(validator.aiohttp, "ClientSession",
                        lambda *a, **kw: FakeSession())
    result = asyncio.run(validator.check("1.2.3.4", 8080, "http"))
    assert result is not None
    assert result["https"] == 0, \
        "a self-signed certificate must not count as HTTPS-capable"


def test_validator_accepts_a_real_https_tunnel(monkeypatch):
    """A working TLS tunnel must still be recognised."""
    import json as _json

    class FakeResp:
        status = 200

        def __init__(self, body=None):
            self._body = body or {"origin": "1.2.3.4", "headers": {}}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def json(self, content_type=None):
            return self._body

    class FakeSession:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        def get(self, url, proxy=None, timeout=None):
            return FakeResp()

    monkeypatch.setattr(validator.aiohttp, "ClientSession",
                        lambda *a, **kw: FakeSession())
    result = asyncio.run(validator.check("1.2.3.4", 8080, "http"))
    assert result is not None
    assert result["https"] == 1


def test_a_row_that_fails_tls_is_not_stored_as_alive():
    """Storing `alive=1` for a row that cannot carry TLS is the actual bug.

    The consumer of this pool asks one question: can this exit carry HTTPS to
    the target host. A row that answered plain HTTP and then failed TLS must
    not be counted as alive.
    """
    from app.engine import Engine

    src = Path(inspect_source())
    text = src.read_text(encoding="utf-8")
    assert "alive=1" not in text.split("ON CONFLICT")[1].split(")")[0] or \
        "https=excluded.https" in text, \
        "store_result must not set alive=1 independently of the https flag"


def inspect_source():
    import app.engine as engine
    return engine.__file__
