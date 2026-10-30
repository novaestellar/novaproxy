import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="np-tests-"))
os.environ["NP_DB"] = str(_TMP / "test.db")
os.environ["NP_AUTH"] = "local"
os.environ["NP_AUTOPOOL"] = "0"
os.environ.setdefault("NP_ADMIN_PASS", "test-pass")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402


@pytest_asyncio.fixture
async def database():
    from app import database as db_module

    conn = await db_module.init_db()
    await db_module.execute("DELETE FROM proxies")
    await db_module.execute("DELETE FROM target_hits")
    yield db_module
    await conn.close()


@pytest_asyncio.fixture
async def gw(database):
    from app.gateway import Gateway

    gateway = Gateway()
    gateway.settings.update({
        "retries": 2,
        "deadline": 1.5,
        "hedge_delay": 0.2,
        "max_per_proxy": 2,
        "host_block_minutes": 10,
        "verified_window": 600,
        "max_fails": 2,
    })
    return gateway


async def add_proxy(database, ip, port, protocol="http", **fields):
    base = {
        "ip": ip, "port": port, "protocol": protocol, "alive": 1,
        "excluded": 0, "https": 1, "latency_ms": 100, "quota_bytes": 0,
        "bytes_in": 0, "bytes_out": 0,
    }
    base.update(fields)
    await database.execute(
        "INSERT INTO proxies (ip, port, protocol, alive, excluded, https, "
        "latency_ms, quota_bytes, bytes_in, bytes_out, checks_failed) "
        "VALUES (:ip, :port, :protocol, :alive, :excluded, :https, "
        ":latency_ms, :quota_bytes, :bytes_in, :bytes_out, 0)", base)
    return base
