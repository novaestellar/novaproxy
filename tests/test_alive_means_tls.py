"""A row may only be "alive" if it can carry TLS to a real target.

Measured 2026-11-24 on the live pool (1443 rows):

    alive=1              891 rows
    alive=1 AND https=1   52 rows   <- the only ones that can carry HTTPS

A row that answered plain HTTP and then failed TLS was still stored as
`alive=1`, so the pool advertised 891 usable exits while only 52 could carry
HTTPS to a target. A consumer of this pool (the novamini session) burned a
full 30 s timeout on `agent.minimax.io` because the exit it was handed could
not do TLS.

The rule: `alive` means "can carry HTTPS". A row that failed TLS is not
usable for any HTTPS target, so it must not be counted as alive.
"""
import asyncio
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import validator
from app.engine import Engine


class _Resp:
    def __init__(self, status=200, body=None):
        self.status = status
        self._body = body or {"origin": "1.2.3.4", "headers": {}}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def json(self, content_type=None):
        return self._body


def _fake_session(monkeypatch, https_raises=None):
    class FakeSession:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        def get(self, url, proxy=None, timeout=None):
            if url.startswith("https://"):
                if https_raises is not None:
                    raise https_raises
                return _Resp()
            return _Resp()

    monkeypatch.setattr(validator.aiohttp, "ClientSession",
                        lambda *a, **kw: FakeSession())


async def test_a_row_that_fails_tls_is_not_alive(database, monkeypatch):
    """The stored row must not claim to be alive when TLS failed."""
    import ssl

    _fake_session(monkeypatch,
                  https_raises=ssl.SSLCertVerificationError("self-signed"))
    res = await validator.check("1.2.3.4", 8080, "http", timeout=5)
    assert res is not None
    assert res["https"] == 0

    engine = Engine()
    await engine.store_result(res, "test")
    async with database.db().execute(
        "SELECT alive, https FROM proxies WHERE ip='1.2.3.4'"
    ) as cur:
        row = await cur.fetchone()
    assert row["alive"] == 0, \
        "a row that cannot carry TLS must not be stored as alive"


async def test_a_row_that_carries_tls_is_alive(database, monkeypatch):
    _fake_session(monkeypatch)
    res = await validator.check("5.6.7.8", 8080, "http", timeout=5)
    assert res["https"] == 1

    engine = Engine()
    await engine.store_result(res, "test")
    async with database.db().execute(
        "SELECT alive, https FROM proxies WHERE ip='5.6.7.8'"
    ) as cur:
        row = await cur.fetchone()
    assert row["alive"] == 1
    assert row["https"] == 1


async def test_the_alive_count_only_counts_tls_capable_rows(database, monkeypatch):
    """The pool's headline number must mean "can carry HTTPS"."""
    _fake_session(monkeypatch,
                  https_raises=RuntimeError("CONNECT refused"))
    engine = Engine()
    await engine.store_result(
        {"ip": "9.9.9.9", "port": 8080, "protocol": "http",
         "anonymity": "unknown", "latency_ms": 50, "https": 0,
         "origin": None, "headers": {}}, "test")
    alive = await engine.alive_count()
    assert alive == 0
