"""Health sweep sizing, connect deadline, and the hedged ladder's guarantees."""
import asyncio
import time

import pytest

from .conftest import add_proxy

pytestmark = pytest.mark.asyncio


async def test_health_batch_scales_with_pool(database, gw, monkeypatch):
    from app import validator

    calls = []

    async def fake_check(ip, port, protocol, timeout=8.0):
        calls.append((ip, port))
        return None

    monkeypatch.setattr(validator, "check", fake_check)

    for i in range(1500):
        await add_proxy(database, f"10.9.{i // 250}.{i % 250}", 8080)

    gw.settings["health_batch"] = 40
    await gw._health_pass()

    # alive // 30 = 50, which is above the configured floor of 40
    assert len(calls) == 50


async def test_connect_times_out_instead_of_hanging(database, gw, monkeypatch):
    await add_proxy(database, "10.2.0.1", 8080)
    gw.settings["deadline"] = 0.6
    gw.settings["retries"] = 1

    async def never(proxy, host, port):
        await asyncio.sleep(30)

    monkeypatch.setattr(gw, "_open", never)

    started = time.monotonic()
    with pytest.raises(TimeoutError):
        await gw._connect("example.test", 443, True)
    assert time.monotonic() - started < 2.0
    assert gw._inflight == {}


async def test_connect_returns_and_reserves(database, gw, monkeypatch):
    await add_proxy(database, "10.2.1.1", 8080)

    class FakeWriter:
        closed = False

        def close(self):
            self.closed = True

    async def ok(proxy, host, port):
        return object(), FakeWriter()

    monkeypatch.setattr(gw, "_open", ok)

    up_r, up_w, proxy, started = await gw._connect("example.test", 443, True)
    assert gw._inflight[(proxy["ip"], int(proxy["port"]), proxy["protocol"])] == 1
    gw._release(proxy)
    assert gw._inflight == {}


async def test_connect_skips_avoided_rows(database, gw, monkeypatch):
    await add_proxy(database, "10.2.2.1", 8080)
    await add_proxy(database, "10.2.2.2", 8080)

    async def ok(proxy, host, port):
        class W:
            def close(self):
                pass
        return object(), W()

    monkeypatch.setattr(gw, "_open", ok)

    avoided = {("10.2.2.1", 8080, "http")}
    for _ in range(4):
        _, _, proxy, _ = await gw._connect("example.test", 443, True, avoid=avoided)
        assert proxy["ip"] == "10.2.2.2"
        gw._release(proxy)


async def test_all_attempts_failing_marks_rows(database, gw, monkeypatch):
    await add_proxy(database, "10.2.3.1", 8080)
    gw.settings["retries"] = 1

    async def boom(proxy, host, port):
        raise OSError("refused")

    monkeypatch.setattr(gw, "_open", boom)

    with pytest.raises(Exception):
        await gw._connect("example.test", 443, True)

    async with database.db().execute(
        "SELECT checks_failed FROM proxies WHERE ip='10.2.3.1'"
    ) as cur:
        row = await cur.fetchone()
    assert row["checks_failed"] == 1
