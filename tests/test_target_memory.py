"""Per-target memory: good exits are preferred, rate-limited ones are skipped."""
import pytest

from .conftest import add_proxy

pytestmark = pytest.mark.asyncio


async def test_record_and_lookup(database, gw):
    proxy = {"ip": "10.1.0.1", "port": 8080, "protocol": "http"}
    await gw._record_target("example.test", proxy, True)

    good = await gw._target_good("example.test")
    assert ("10.1.0.1", 8080, "http") in good

    other = await gw._target_good("other.test")
    assert other == set()


async def test_block_makes_row_invisible_for_that_host(database, gw):
    await add_proxy(database, "10.1.1.1", 8080)
    await add_proxy(database, "10.1.1.2", 8080)
    blocked = {"ip": "10.1.1.1", "port": 8080, "protocol": "http"}

    await gw._block_host("api.test", blocked)
    rows = await gw._blocked_for("api.test")
    assert ("10.1.1.1", 8080, "http") in rows

    picks = {(await gw._pick(host="api.test"))["ip"] for _ in range(6)}
    assert picks == {"10.1.1.2"}

    # another host is unaffected
    picks2 = {(await gw._pick(host="elsewhere.test"))["ip"] for _ in range(8)}
    assert "10.1.1.1" in picks2


async def test_expired_block_is_ignored(database, gw):
    proxy = {"ip": "10.1.2.1", "port": 8080, "protocol": "http"}
    await gw._block_host("api.test", proxy)
    # force the block into the past
    await database.execute(
        "UPDATE target_hits SET blocked_until='2000-01-01T00:00:00' "
        "WHERE host='api.test'")
    gw._blocked_cache.clear()

    assert await gw._blocked_for("api.test") == set()


async def test_failure_record_increments(database, gw):
    proxy = {"ip": "10.1.3.1", "port": 8080, "protocol": "http"}
    await gw._record_target("flaky.test", proxy, False)
    async with database.db().execute(
        "SELECT fail FROM target_hits WHERE host='flaky.test'"
    ) as cur:
        row = await cur.fetchone()
    assert row["fail"] == 1
