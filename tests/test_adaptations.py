"""Burned ledger, fallback exit, and the new metric fields."""
import time

import pytest

from .conftest import add_proxy

pytestmark = pytest.mark.asyncio


class _W:
    def close(self):
        pass


async def test_failure_lands_in_burned_ledger(database, gw):
    await add_proxy(database, "10.4.0.1", 8080)
    gw.settings["max_fails"] = 1
    await gw._mark_failed({"ip": "10.4.0.1", "port": 8080, "protocol": "http"}, "boom")

    async with database.db().execute(
        "SELECT strikes, reason FROM burned_exits WHERE ip='10.4.0.1'"
    ) as cur:
        row = await cur.fetchone()
    assert row is not None
    assert row["strikes"] == 1
    assert "boom" in (row["reason"] or "")


async def test_burn_accumulates_strikes(database, gw):
    proxy = {"ip": "10.4.0.2", "port": 8080, "protocol": "http"}
    await gw._burn(proxy, "first")
    await database.execute(
        "UPDATE burned_exits SET last_seen='2026-11-22T12:00:00' WHERE ip=?",
        (proxy["ip"],),
    )
    await gw._burn(proxy, "second")
    async with database.db().execute(
        "SELECT strikes, reason FROM burned_exits WHERE ip='10.4.0.2'"
    ) as cur:
        row = await cur.fetchone()
    assert row["strikes"] == 2
    assert row["reason"] == "second"


async def test_successful_recheck_clears_burn_record(database, gw):
    proxy = {"ip": "10.4.0.6", "port": 8080, "protocol": "http"}
    await add_proxy(database, proxy["ip"], proxy["port"])
    await gw._burn(proxy, "transient connect error")
    await gw._mark_ok(proxy, 140)
    async with database.db().execute(
        "SELECT COUNT(*) c FROM burned_exits WHERE ip='10.4.0.6'"
    ) as cur:
        assert (await cur.fetchone())["c"] == 0
    async with database.db().execute(
        "SELECT checks_failed FROM proxies WHERE ip='10.4.0.6'"
    ) as cur:
        assert (await cur.fetchone())["checks_failed"] == 0


async def test_pick_uses_strike_threshold_then_cooldown(database, gw):
    """One hit is tolerated; repeated evidence quarantines until expiry."""
    await add_proxy(database, "10.4.1.1", 8080)
    await add_proxy(database, "10.4.1.2", 8080)
    proxy = {"ip": "10.4.1.1", "port": 8080, "protocol": "http"}
    await gw._burn(proxy, "first")
    assert {(await gw._pick())["ip"] for _ in range(6)} == {"10.4.1.1", "10.4.1.2"}

    await gw._burn(proxy, "second")
    await gw._burn(proxy, "third")
    await database.execute(
        "UPDATE burned_exits SET strikes=3, last_seen=? WHERE ip=? AND port=? AND protocol=?",
        (time.strftime("%Y-%m-%dT%H:%M:%S"), proxy["ip"], proxy["port"], proxy["protocol"]),
    )
    assert {(await gw._pick())["ip"] for _ in range(6)} == {"10.4.1.2"}

    await database.execute(
        "UPDATE burned_exits SET last_seen='2000-01-01T00:00:00' "
        "WHERE ip=? AND port=? AND protocol=?",
        (proxy["ip"], proxy["port"], proxy["protocol"]),
    )
    assert {(await gw._pick())["ip"] for _ in range(6)} == {"10.4.1.1", "10.4.1.2"}



async def test_soft_failure_does_not_enter_the_burn_ledger(database, gw):
    """Probe/health failures already cost a checks_failed strike; writing them
    into the burn ledger too is what made one timeout look like a dead exit."""
    await add_proxy(database, "10.4.1.5", 8080)
    gw.settings["max_fails"] = 5
    await gw._mark_failed({"ip": "10.4.1.5", "port": 8080, "protocol": "http"},
                          "health probe failed", burn=False)

    async with database.db().execute(
        "SELECT COUNT(*) c FROM burned_exits WHERE ip='10.4.1.5'"
    ) as cur:
        assert (await cur.fetchone())["c"] == 0
    async with database.db().execute(
        "SELECT checks_failed, alive FROM proxies WHERE ip='10.4.1.5'"
    ) as cur:
        row = await cur.fetchone()
    assert row["checks_failed"] == 1
    assert row["alive"] == 1


async def test_fallback_is_used_when_pool_is_empty(database, gw, monkeypatch):
    gw.fallback = {"ip": "10.4.2.9", "port": 9999, "protocol": "http"}

    async def ok(proxy, host, port):
        return object(), _W()

    monkeypatch.setattr(gw, "_open", ok)
    _r, _w, proxy, _started = await gw._connect("example.test", 443, True)
    assert proxy["ip"] == "10.4.2.9"
    assert gw.fallback_hits == 1
    gw._release(proxy)


async def test_fallback_is_not_used_when_a_pooled_row_works(database, gw, monkeypatch):
    await add_proxy(database, "10.4.3.1", 8080)
    gw.fallback = {"ip": "10.4.2.9", "port": 9999, "protocol": "http"}

    async def ok(proxy, host, port):
        return object(), _W()

    monkeypatch.setattr(gw, "_open", ok)
    _r, _w, proxy, _started = await gw._connect("example.test", 443, True)
    assert proxy["ip"] == "10.4.3.1"
    assert gw.fallback_hits == 0
    gw._release(proxy)


async def test_snapshot_carries_the_new_metrics(database, gw):
    await add_proxy(database, "10.4.4.1", 8080, latency_ms=100)
    await add_proxy(database, "10.4.4.2", 8080, latency_ms=300,
                    quota_bytes=10, bytes_in=20, bytes_out=0)
    await gw._burn({"ip": "10.4.4.3", "port": 1, "protocol": "http"}, "dead")

    snap = await gw.snapshot()
    assert snap["pool"]["median_ms"] == 300
    assert snap["pool"]["burned"] == 1
    assert snap["pool"]["quota_full"] == 1
    assert snap["pool"]["quota_used"] >= 20
    assert "exit_ips" in snap and "fallback" in snap
