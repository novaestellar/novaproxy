"""A pool must know WHICH hosts an exit can reach.

Measured 2026-11-24 from the novamini session: novaproxy reported 519 alive
rows, yet the consumer's target (`agent.minimax.io`) timed out through them.
The site-check only tested `example.com`, and the `https` flag only meant "once
carried TLS to some host" -- so a row that could reach example.com but not the
consumer's target looked perfectly usable.

What is missing:
  * the site-check result has to be stored per host, so a row that fails
    `agent.minimax.io` is not offered for that host;
  * the pool's own validation has to probe the host the consumer cares about,
    not a generic judge.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import database as db_mod


async def test_site_check_result_is_kept_per_host(database):
    """A row that fails one host but passes another must be told apart."""
    await database.execute(
        "INSERT INTO proxies (ip, port, protocol, alive, excluded, https, "
        "latency_ms, quota_bytes, bytes_in, bytes_out, checks_failed) "
        "VALUES ('10.30.0.1', 8080, 'http', 1, 0, 1, 100, 0, 0, 0, 0)")

    await database.execute(
        "INSERT INTO site_checks (ip, port, protocol, url, ok, status, "
        "latency_ms, error, checked_at) VALUES (?,?,?,?,?,?,?,?,?)",
        ("10.30.0.1", 8080, "http", "https://agent.minimax.io/", 0, None,
         None, "TimeoutError", "2026-11-24T00:00:00"))

    rows = await db_mod.db().execute(
        "SELECT ip, port, protocol, url, ok FROM site_checks "
        "WHERE url='https://agent.minimax.io/'")
    found = [dict(r) for r in await rows.fetchall()]
    assert len(found) == 1
    assert found[0]["ok"] == 0


async def test_a_row_failing_a_host_can_be_filtered_out_for_that_host(database):
    """The pool must be able to say 'not for this host'."""
    from app.gateway import Gateway

    await database.execute(
        "INSERT INTO proxies (ip, port, protocol, alive, excluded, https, "
        "latency_ms, quota_bytes, bytes_in, bytes_out, checks_failed) "
        "VALUES ('10.30.0.2', 8080, 'http', 1, 0, 1, 100, 0, 0, 0, 0)")
    await database.execute(
        "INSERT INTO site_checks (ip, port, protocol, url, ok, status, "
        "latency_ms, error, checked_at) VALUES (?,?,?,?,?,?,?,?,?)",
        ("10.30.0.2", 8080, "http", "https://agent.minimax.io/", 0, None,
         None, "TimeoutError", "2026-11-24T00:00:00"))

    gw = Gateway()
    blocked = await gw._blocked_for("agent.minimax.io")
    assert ("10.30.0.2", 8080, "http") in blocked, \
        "a row that failed this host must be excluded from it"
