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

# ------------------------------------------------- the pin is a promise ------
class _Reader:
    """Feeds one request head to the sticky listener."""

    def __init__(self, data: bytes):
        self._buf = data

    async def read(self, n: int) -> bytes:
        chunk, self._buf = self._buf[:n], self._buf[n:]
        return chunk


class _Stream:
    """Minimal asyncio writer: collects bytes, answers peername."""

    def __init__(self):
        self.chunks = []
        self.closed = False

    def write(self, data):
        self.chunks.append(bytes(data))

    async def drain(self):
        pass

    def get_extra_info(self, name, default=None):
        return ("127.0.0.1", 5000) if name == "peername" else default

    def close(self):
        self.closed = True


async def test_dead_pin_is_repinned_not_rotated(database, gw, monkeypatch):
    """The sticky listener promises a stable exit.

    If the pinned upstream dies mid-session, the session must be re-pinned.
    Falling back to the rotating path would hand the caller a different IP while
    it still believes its session holds -- the exact defect this listener exists
    to prevent.
    """
    from app.gateway import Gateway

    await add_proxy(database, "10.4.0.1", 8080)
    await add_proxy(database, "10.4.0.2", 8080)
    await gw._sticky_proxy("sess-1", "example.com", 443)

    opens = {"n": 0}
    rotated = {"n": 0}

    async def flaky_open(self, proxy, host, port):
        opens["n"] += 1
        if opens["n"] == 1:
            raise OSError("pinned upstream went dark")
        return object(), _Writer()

    async def no_connect(self, *a, **kw):
        rotated["n"] += 1
        raise AssertionError("sticky must re-pin, not rotate")

    monkeypatch.setattr(Gateway, "_open", flaky_open, raising=True)
    monkeypatch.setattr(Gateway, "_connect", no_connect, raising=True)

    reader = _Reader(b"CONNECT example.com:443 HTTP/1.1\r\n"
                     b"X-NP-Session: sess-1\r\n\r\n")
    writer = _Stream()
    await gw._handle_sticky(reader, writer)

    assert rotated["n"] == 0, "rotated instead of re-pinning"
    assert opens["n"] >= 2, "did not retry the tunnel"
    assert any(b"200 Connection Established" in c for c in writer.chunks)
    assert "sess-1" in gw._sticky


async def test_dead_pinned_proxy_is_replaced(database, gw):
    """Serving a pin whose row died hands the caller a dead exit forever.

    Pins used to be trusted blindly for the whole TTL, so once the pinned row
    went dead every request of that session kept failing while a healthy pool
    sat right behind it.
    """
    await add_proxy(database, "10.5.0.1", 8080)
    await add_proxy(database, "10.5.0.2", 8080)

    first = await gw._sticky_proxy("sess-dead", "ipstar.io")
    assert first is not None
    await database.execute("UPDATE proxies SET alive=0 WHERE ip=?", (first["ip"],))

    again = await gw._sticky_proxy("sess-dead", "ipstar.io")
    assert again is not None
    assert again["ip"] != first["ip"]


async def test_new_session_still_picks_when_every_pool_row_is_pinned(database, gw):
    """Pins are only a preference, never a lock.

    Every new session avoids the exits already pinned to other sessions. Once
    the pool is smaller than the pin count that avoidance set covered the whole
    pool, _pick returned nothing, and the listener answered every fresh session
    with no exit (observed live as 0/5 while a healthy pool sat idle).
    """
    await add_proxy(database, "10.6.0.1", 8080)
    await add_proxy(database, "10.6.0.2", 8080)

    assert await gw._sticky_proxy("pin-a", "ipstar.io") is not None
    assert await gw._sticky_proxy("pin-b", "ipstar.io") is not None
    assert len(gw._sticky) == 2

    extra = await gw._sticky_proxy("pin-c", "ipstar.io")
    assert extra is not None, "fresh session got no exit while every row was pinned"


async def test_capabilities_are_declared(gw):
    """A consumer must be able to read what this endpoint is."""
    status = await gw.snapshot()
    assert status["class"] == "public-pool"
    assert status["capabilities"]["session_pin"] is True
    assert status["capabilities"]["cloudflare_clearance"] is False
