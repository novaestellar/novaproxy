"""A site-check against the consumer's real target must feed back into the pool.

The site-check endpoint already accepts the target URL and records the result
per row. What it did NOT do was change the pool: a row that failed the
consumer's target stayed `alive=1` and kept being handed out. That is how the
novamini session kept receiving an exit that could not carry
`agent.minimax.io`.

So:
  * a row that fails the site-check must lose its alive flag;
  * a row that passes must keep it.
"""
import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import sitecheck


def _fake_test_many(passed: bool):
    async def fake(items, url, timeout=8, concurrency=8):
        out = []
        for ip, port, protocol in items:
            out.append({
                "ip": ip, "port": port, "protocol": protocol,
                "ok": passed, "status": 200 if passed else 0,
                "latency_ms": 100 if passed else None,
                "error": None if passed else "CONNECT refused",
            })
        return out
    return fake


async def test_a_row_failing_the_target_site_check_loses_its_alive_flag(
        database, monkeypatch):
    from app import main as main_mod

    await database.execute(
        "INSERT INTO proxies (ip, port, protocol, alive, excluded, https, "
        "latency_ms, quota_bytes, bytes_in, bytes_out, checks_failed) "
        "VALUES ('10.20.0.1', 8080, 'http', 1, 0, 1, 100, 0, 0, 0, 0)")

    monkeypatch.setattr(sitecheck, "test_many", _fake_test_many(False))

    resp = await main_mod.api_test_proxies(
        _Body({"url": "https://agent.minimax.io/", "limit": 50}))

    assert resp["passed"] == 0
    async with database.db().execute(
        "SELECT alive FROM proxies WHERE ip='10.20.0.1'"
    ) as cur:
        row = await cur.fetchone()
    assert row["alive"] == 0, \
        "a row that cannot reach the consumer's target must not stay alive"


async def test_a_row_passing_the_target_site_check_keeps_its_alive_flag(
        database, monkeypatch):
    from app import main as main_mod

    await database.execute(
        "INSERT INTO proxies (ip, port, protocol, alive, excluded, https, "
        "latency_ms, quota_bytes, bytes_in, bytes_out, checks_failed) "
        "VALUES ('10.20.0.2', 8080, 'http', 1, 0, 1, 100, 0, 0, 0, 0)")

    monkeypatch.setattr(sitecheck, "test_many", _fake_test_many(True))

    resp = await main_mod.api_test_proxies(
        _Body({"url": "https://agent.minimax.io/", "limit": 50}))

    assert resp["passed"] == 1
    async with database.db().execute(
        "SELECT alive FROM proxies WHERE ip='10.20.0.2'"
    ) as cur:
        row = await cur.fetchone()
    assert row["alive"] == 1


class _Body(dict):
    """Starlette parses the JSON body before the handler sees it."""

    def __init__(self, data):
        super().__init__(data)

    async def json(self):
        return dict(self)
