"""The pool's validation must test the host the consumer actually uses.

The validator probes `httpbin.org` for TLS and `example.com` for reachability.
Those are generic judges: a row that carries them says nothing about the
host a consumer wants. Measured 2026-11-24, the pool looked healthy (891
alive rows) while the consumer's target was unreachable through them.

So the pool needs a configurable probe target: a row is "alive" for a host
only if it carries THAT host.
"""
import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import validator


def test_validator_has_a_configurable_probe_target():
    """The TLS probe target must be settable, not hard-coded to httpbin."""
    assert hasattr(validator, "PROBE_TARGETS"), \
        "the validator needs a configurable probe target list"
    assert validator.PROBE_TARGETS, "the probe target list must not be empty"


def test_the_configured_target_is_used_for_the_tls_probe(monkeypatch):
    """The TLS probe must hit the configured host, not httpbin."""
    seen = []

    class _Resp:
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
            seen.append(url)
            return _Resp()

    monkeypatch.setattr(validator.aiohttp, "ClientSession",
                        lambda *a, **kw: FakeSession())
    monkeypatch.setattr(validator, "PROBE_TARGETS",
                        ["https://agent.minimax.io/"])

    asyncio.run(validator.check("1.2.3.4", 8080, "http", timeout=5))

    assert any("agent.minimax.io" in u for u in seen), \
        f"the configured probe target was not used: {seen}"
