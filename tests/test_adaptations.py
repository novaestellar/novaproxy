"""Burned ledger, fallback exit, and the new metric fields."""
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
    await gw._burn(proxy, "second")
    async with database.db().execute(
        "SELECT strikes, reason FROM burned_exits WHERE ip='10.4.0.2'"
    ) as cur:
        row = await cur.fetchone()
    assert row["strikes"] == 2
    assert row["reason"] == "second"


async def test_pick_skips_burned_rows_even_if_alive(database, gw):
    await add_proxy(database, "10.4.1.1", 8080)
    await add_proxy(database, "10.4.1.2", 8080)
    await gw._burn({"ip": "10.4.1.1", "port": 8080, "protocol": "http"}, "test")

    picks = {(await gw._pick())["ip"] for _ in range(6)}
    assert picks == {"10.4.1.2"}


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
