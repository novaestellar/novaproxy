"""Selection rules: quota, exclusion, TLS capability, concurrency, host blocks."""
import pytest

from .conftest import add_proxy

pytestmark = pytest.mark.asyncio


async def test_skips_excluded_and_dead(database, gw):
    await add_proxy(database, "10.0.0.1", 8080, excluded=1)
    await add_proxy(database, "10.0.0.2", 8080, alive=0)
    await add_proxy(database, "10.0.0.3", 8080)

    picked = [await gw._pick() for _ in range(6)]
    assert {(p["ip"], p["port"]) for p in picked} == {("10.0.0.3", 8080)}


async def test_quota_exhausted_is_not_offered(database, gw):
    await add_proxy(database, "10.0.1.1", 8080, quota_bytes=1000, bytes_in=900, bytes_out=200)
    await add_proxy(database, "10.0.1.2", 8080, quota_bytes=1000, bytes_in=10, bytes_out=10)

    for _ in range(4):
        assert (await gw._pick())["ip"] == "10.0.1.2"


async def test_quota_zero_means_unlimited(database, gw):
    await add_proxy(database, "10.0.2.1", 8080, quota_bytes=0, bytes_in=10**9, bytes_out=10**9)
    assert (await gw._pick()) is not None


async def test_tunnel_requires_https_capability(database, gw):
    await add_proxy(database, "10.0.3.1", 8080, https=0)
    await add_proxy(database, "10.0.3.2", 8080, https=1)

    for _ in range(4):
        picked = await gw._pick(require_tunnel=True)
        assert picked["ip"] == "10.0.3.2"


async def test_concurrency_cap_skips_busy_rows(database, gw):
    await add_proxy(database, "10.0.4.1", 8080)
    await add_proxy(database, "10.0.4.2", 8080)

    busy = {"ip": "10.0.4.1", "port": 8080, "protocol": "http"}
    gw._reserve(busy)
    gw._reserve(busy)

    seen = set()
    for _ in range(6):
        picked = await gw._pick()
        assert picked is not None
        seen.add(picked["ip"])
    assert seen == {"10.0.4.2"}

    gw._release(busy)
    gw._release(busy)
    assert gw._inflight == {}


async def test_release_never_goes_negative(gw):
    row = {"ip": "10.0.5.1", "port": 1, "protocol": "http"}
    gw._release(row)
    assert gw._inflight == {}


async def test_protocol_filter(database, gw):
    await add_proxy(database, "10.0.6.1", 1080, protocol="socks5")
    gw.settings["enabled_protocols"] = ["http"]
    assert (await gw._pick()) is None
