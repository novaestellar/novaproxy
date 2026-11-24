"""A proxy pool must not collapse onto one exit.

Two measured defects on 2026-11-24:

  1. `_pick()` prefers exits that already served the same host, two picks in
     three. That is a good idea for a real target, but the host used to READ
     THE EXIT IP is an IP-echo service (api.ipify.org) whose "good" set had
     collapsed to ONE exit. So every rotation converged on that single exit and
     the pool looked like it had ten members when it had one.

  2. The health probe marks a row dead after `max_fails` failed probes. A free
     pool loses rows to one bad minute: 717 rows were `alive=0` while still
     tunnel-capable, and 7 of 20 tested still answered CONNECT.

These tests pin the fixes.
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.gateway import ECHO_HOSTS, Gateway
import pytest


def _gw():
    return Gateway()


def test_echo_hosts_are_recognised_in_the_list():
    """The IP-echo services we use to read the exit IP must be listed."""
    assert "api.ipify.org" in ECHO_HOSTS
    assert "ifconfig.me" in ECHO_HOSTS
    # a real target must not be on the list
    assert "ipstar.io" not in ECHO_HOSTS


def test_echo_hosts_are_recognised_when_listed():
    gw = _gw()
    assert gw._is_echo_host("api.ipify.org") is True
    assert gw._is_echo_host("ipstar.io") is False


async def test_target_preference_is_skipped_for_echo_hosts(database, gw):
    """The preference must be skipped, not merely reduced."""
    from .conftest import add_proxy
    await add_proxy(database, "10.9.0.1", 8080)

    calls = []

    async def fake_good(host):
        calls.append(host)
        return set()

    gw._target_good = fake_good
    gw._target_cache = {}

    await gw._pick(host="api.ipify.org")
    assert "api.ipify.org" not in calls, \
        "the echo host still drives the target preference"


async def test_target_preference_still_applies_to_a_real_target(database, gw):
    """A real target keeps its preference -- the fix is scoped."""
    from .conftest import add_proxy
    await add_proxy(database, "10.9.0.2", 8080)

    calls = []

    async def fake_good(host):
        calls.append(host)
        return set()

    gw._target_good = fake_good
    gw._target_cache = {}

    await gw._pick(host="ipstar.io")
    assert "ipstar.io" in calls, \
        "the preference was dropped for a real target as well"


def test_dead_rows_keep_their_tunnel_capability():
    """A row that failed a few probes must not be written off for good.

    `max_fails` marks a row dead; that is correct for a row that refuses, but
    for a free pool it throws away exits that still work. The row has to stay
    usable until it has failed far more times than the pool can afford.
    """
    gw = _gw()
    assert gw.settings["max_fails"] >= 5, \
        "two failed probes must not retire a working exit"


def test_burn_needs_repeated_evidence():
    """One failure is not evidence that an exit is dead."""
    gw = _gw()
    assert gw.settings["burn_strikes"] >= 3
