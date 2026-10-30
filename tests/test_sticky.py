"""Sticky listener: one upstream per session, proven before it is pinned."""
import time

import pytest

from .conftest import add_proxy

pytestmark = pytest.mark.asyncio


class _Writer:
    def close(self):
        pass


@pytest.fixture(autouse=True)
def fake_open(monkeypatch):
    """The pin now proves itself with a real CONNECT; stub that probe."""
    async def ok(self, proxy, host, port):
        return object(), _Writer()
    monkeypatch.setattr("app.gateway.Gateway._open", ok, raising=True)


async def test_same_session_gets_same_proxy(database, gw):
    await add_proxy(database, "10.3.0.1", 8080)
    await add_proxy(database, "10.3.0.2", 8080)

    first = await gw._sticky_proxy("reg-1", "ipstar.io")
    assert first is not None
    for _ in range(6):
        again = await gw._sticky_proxy("reg-1", "ipstar.io")
        assert (again["ip"], again["port"]) == (first["ip"], first["port"])
    assert len(gw._sticky) == 1


async def test_sessions_are_independent(database, gw):
    await add_proxy(database, "10.3.1.1", 8080)
    await add_proxy(database, "10.3.1.2", 8080)

    a = await gw._sticky_proxy("reg-a", "ipstar.io")
    b = await gw._sticky_proxy("reg-b", "ipstar.io")
    assert len(gw._sticky) == 2
    assert (await gw._sticky_proxy("reg-a", "ipstar.io"))["ip"] == a["ip"]
    assert (await gw._sticky_proxy("reg-b", "ipstar.io"))["ip"] == b["ip"]


async def test_pin_expires_after_ttl(database, gw):
    await add_proxy(database, "10.3.2.1", 8080)
    gw.settings["sticky_ttl"] = 1
    assert await gw._sticky_proxy("reg-ttl", "ipstar.io") is not None
    gw._sticky["reg-ttl"]["last"] = time.time() - 5
    gw._sticky_prune()
    assert "reg-ttl" not in gw._sticky


async def test_drop_forces_new_pick(database, gw):
    await add_proxy(database, "10.3.3.1", 8080)
    await gw._sticky_proxy("reg-drop", "ipstar.io")
    assert "reg-drop" in gw._sticky
    gw._sticky_drop("reg-drop")
    assert "reg-drop" not in gw._sticky


async def test_sticky_respects_pool_rules(database, gw):
    await add_proxy(database, "10.3.4.1", 8080, https=0)
    assert await gw._sticky_proxy("reg-tls", "ipstar.io") is None

    await add_proxy(database, "10.3.4.2", 8080, excluded=1)
    assert await gw._sticky_proxy("reg-ex", "ipstar.io") is None

    await add_proxy(database, "10.3.4.3", 8080)
    pinned = await gw._sticky_proxy("reg-ok", "ipstar.io")
    assert pinned["ip"] == "10.3.4.3"


async def test_broken_exit_is_not_pinned(database, gw, monkeypatch):
    from app.gateway import Gateway

    await add_proxy(database, "10.3.5.1", 8080)

    async def fail(self, proxy, host, port):
        raise OSError("CONNECT refused")

    monkeypatch.setattr(Gateway, "_open", fail, raising=True)
    assert await gw._sticky_proxy("reg-bad", "ipstar.io") is None
    assert "reg-bad" not in gw._sticky
