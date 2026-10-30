import aiosqlite
from app.config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    pass_hash TEXT NOT NULL,
    is_admin INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS proxies (
    ip TEXT NOT NULL,
    port INTEGER NOT NULL,
    protocol TEXT NOT NULL,
    anonymity TEXT DEFAULT 'unknown',
    latency_ms INTEGER,
    https INTEGER DEFAULT 0,
    country TEXT,
    country_code TEXT,
    city TEXT,
    isp TEXT,
    source TEXT,
    alive INTEGER DEFAULT 1,
    checks_failed INTEGER DEFAULT 0,
    last_checked TEXT,
    added_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ip, port, protocol)
);
CREATE INDEX IF NOT EXISTS idx_alive ON proxies(alive, protocol);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS traffic_samples (
    ts TEXT PRIMARY KEY,
    bytes_in INTEGER NOT NULL DEFAULT 0,
    bytes_out INTEGER NOT NULL DEFAULT 0,
    requests INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS site_checks (
    ip TEXT NOT NULL,
    port INTEGER NOT NULL,
    protocol TEXT NOT NULL,
    url TEXT NOT NULL,
    ok INTEGER NOT NULL DEFAULT 0,
    status INTEGER,
    latency_ms INTEGER,
    error TEXT,
    checked_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ip, port, protocol, url)
);
CREATE INDEX IF NOT EXISTS idx_site_checks_url ON site_checks(url, checked_at);

CREATE TABLE IF NOT EXISTS target_hits (
    host TEXT NOT NULL,
    ip TEXT NOT NULL,
    port INTEGER NOT NULL,
    protocol TEXT NOT NULL,
    ok INTEGER NOT NULL DEFAULT 0,
    fail INTEGER NOT NULL DEFAULT 0,
    last_ok TEXT,
    last_fail TEXT,
    PRIMARY KEY (host, ip, port, protocol)
);
CREATE INDEX IF NOT EXISTS idx_target_hits_host ON target_hits(host, ok);

CREATE TABLE IF NOT EXISTS sources (
    url TEXT NOT NULL,
    protocol TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    builtin INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    added_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_ok TEXT,
    last_rows INTEGER DEFAULT 0,
    PRIMARY KEY (url, protocol)
);
"""

_PROXY_MIGRATIONS = {
    # column: DDL fragment appended to ALTER TABLE proxies ADD COLUMN
    "bytes_in": "INTEGER NOT NULL DEFAULT 0",
    "bytes_out": "INTEGER NOT NULL DEFAULT 0",
    "requests": "INTEGER NOT NULL DEFAULT 0",
    "quota_bytes": "INTEGER NOT NULL DEFAULT 0",
    "excluded": "INTEGER NOT NULL DEFAULT 0",
    "last_used": "TEXT",
    "verified_at": "TEXT",
}



async def init_db() -> aiosqlite.Connection:
    global _conn, _write_lock
    _conn = await aiosqlite.connect(DB_PATH, timeout=10)
    _conn.row_factory = aiosqlite.Row
    await _conn.execute("PRAGMA journal_mode=WAL")
    await _conn.execute("PRAGMA busy_timeout=10000")
    await _conn.executescript(_SCHEMA)
    await _migrate(_conn)
    await _seed_sources(_conn)
    await _conn.commit()
    _write_lock = __import__("asyncio").Lock()
    return _conn


async def _migrate(conn: aiosqlite.Connection) -> None:
    """Add columns introduced after the first schema revision (idempotent)."""
    async with conn.execute("PRAGMA table_info(proxies)") as cur:
        existing = {row["name"] for row in await cur.fetchall()}
    for column, ddl in _PROXY_MIGRATIONS.items():
        if column not in existing:
            await conn.execute(f"ALTER TABLE proxies ADD COLUMN {column} {ddl}")



async def _seed_sources(conn: aiosqlite.Connection) -> None:
    """Install the built-in feeds once; the table is the live registry after."""
    from app.sources import public

    rows = [(url, protocol, 1, 1)
            for protocol, urls in public.RAW.items()
            for url in urls]
    await conn.executemany(
        "INSERT OR IGNORE INTO sources (url, protocol, enabled, builtin) "
        "VALUES (?,?,?,?)", rows)


def db() -> aiosqlite.Connection:
    assert _conn is not None, "database not initialised"
    return _conn


async def execute(sql: str, params: tuple = ()):
    async with _write_lock:
        cur = await db().execute(sql, params)
        await db().commit()
        return cur


async def executemany(sql: str, rows):
    async with _write_lock:
        await db().executemany(sql, rows)
        await db().commit()