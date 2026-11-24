"""A retired row must be able to come back.

Measured 2026-11-24: 717 rows were `alive=0` while still tunnel-capable, and
7 of 20 tested answered CONNECT. Two things kept them retired:

  * the health pass only re-probed rows with `alive=1`, so a wrongly retired
    row could never be re-checked -- the pool only ever shrank;
  * a row that answered again was not marked alive, so even a successful probe
    left it dead.

These tests pin both.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from app.gateway import Gateway


async def test_a_row_that_answers_again_is_alive_again(database, gw):
    from .conftest import add_proxy
    await add_proxy(database, "10.7.0.1", 8080, alive=0, checks_failed=9)

    await gw._revive({"ip": "10.7.0.1", "port": 8080, "protocol": "http"})

    async with database.db().execute(
        "SELECT alive, checks_failed FROM proxies WHERE ip='10.7.0.1'"
    ) as cur:
        row = await cur.fetchone()
    assert row["alive"] == 1
    assert row["checks_failed"] == 0


async def test_health_pass_rechecks_retired_rows(database, gw):
    """A retired row has to be re-probed, otherwise it can never come back."""
    from .conftest import add_proxy
    await add_proxy(database, "10.7.0.2", 8080, alive=0, checks_failed=1)

    seen = []

    async def fake_check(ip, port, protocol, timeout=8.0):
        seen.append((ip, port, protocol))
        return None

    import app.validator as validator
    original = validator.check
    validator.check = fake_check
    try:
        await gw._health_pass()
    finally:
        validator.check = original

    assert ("10.7.0.2", 8080, "http") in seen, \
        "a retired row was never re-probed"


async def test_rows_that_keep_failing_are_left_out(database, gw):
    """Reviving must not resurrect a row that has failed for good."""
    from .conftest import add_proxy
    await add_proxy(database, "10.7.0.3", 8080, alive=0)
    # add_proxy always writes checks_failed=0, so set it explicitly.
    await database.execute(
        "UPDATE proxies SET checks_failed=99 WHERE ip='10.7.0.3'")

    seen = []

    async def fake_check(ip, port, protocol, timeout=8.0):
        seen.append((ip, port, protocol))
        return None

    import app.validator as validator
    original = validator.check
    validator.check = fake_check
    try:
        await gw._health_pass()
    finally:
        validator.check = original

    assert ("10.7.0.3", 8080, "http") not in seen, \
        "a row that failed for good was re-probed forever"
