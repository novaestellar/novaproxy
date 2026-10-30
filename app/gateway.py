"""novaproxy gateway — one local SOCKS5/HTTP endpoint in front of the pool.

Adapted from novastar's gateway: rotation, failover, per-proxy byte accounting
and quota enforcement. The difference is where the pool comes from — there are
no credentials here, only the validated proxy rows novaproxy already keeps.

    app -> 127.0.0.1:11500 (SOCKS5)  \
           127.0.0.1:12500 (HTTP)     -> pool -> rotating exit

Three things keep the success rate up on a pool of free proxies:

* every request gets a retry ladder, so one rotten row costs a retry, not a 502;
* selection prefers rows that recently carried real traffic (`verified_at`);
* a background health pass re-probes the stalest rows and keeps `https` honest.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
import struct
import time
from urllib.parse import urlsplit

from app.database import db, execute

DEFAULT_SETTINGS = {
    "host": "127.0.0.1",
    "socks_port": 11500,
    "http_port": 12500,
    "strategy": "round_robin",      # round_robin | least_used | fastest
    "quota_mb": 0,                   # 0 = unlimited, applied to new rows on start
    "timeout": 8.0,
    "max_fails": 2,
    "retries": 4,                    # upstream attempts per client request
    "hedge_delay": 0.6,              # start the next attempt this early
    "deadline": 3.0,                 # hard ceiling for opening a tunnel
    "first_byte_timeout": 2.5,       # give up if upstream stays silent
    "idle_timeout": 3.8,             # cut a tunnel that stops moving bytes
    "verified_window": 600,          # seconds a proven row keeps its rank
    "health_interval": 30.0,         # seconds between background re-probes
    "health_batch": 40,              # rows re-probed per pass
    "enabled_protocols": ["http", "socks5", "socks4"],
}


class NoProxyAvailable(RuntimeError):
    """Nothing eligible could be picked — distinct from a proxy that failed."""


def _addr_bytes(host: str) -> tuple[int, bytes]:
    try:
        ip = ipaddress.ip_address(host)
        return (0x01, ip.packed) if ip.version == 4 else (0x04, ip.packed)
    except ValueError:
        h = host.encode()
        if len(h) > 255:
            raise ValueError("hostname too long")
        return 0x03, bytes([len(h)]) + h


class Session:
    """Byte counters for one relayed connection, flushed periodically."""

    __slots__ = ("key", "bytes_in", "bytes_out", "started")

    def __init__(self, key: tuple[str, int, str]):
        self.key = key
        self.bytes_in = 0
        self.bytes_out = 0
        self.started = time.time()


class Gateway:
    def __init__(self) -> None:
        self.settings = dict(DEFAULT_SETTINGS)
        self.running = False
        self.started_at = 0.0
        self.servers: list[asyncio.AbstractServer] = []
        self.sessions: dict[int, Session] = {}
        self.connections = 0
        self.fails = 0
        self.bytes_in = 0
        self.bytes_out = 0
        self.active = 0
        self.last_error = ""
        self._rr = 0
        self._flush_task: asyncio.Task | None = None
        self._health_task: asyncio.Task | None = None
        self._warm_task: asyncio.Task | None = None
        self._load_lock = asyncio.Lock()
        self._hot = 0
        self._hot_at = 0.0
        self._target_cache: dict[str, tuple[float, set]] = {}
        self._pick_n = 0
        self._sample = {"in": 0, "out": 0, "req": 0, "at": time.time()}

    # ── settings ────────────────────────────────────────────────────
    async def load_settings(self) -> dict:
        async with db().execute("SELECT value FROM kv WHERE key='gateway'") as cur:
            row = await cur.fetchone()
        if row:
            try:
                stored = json.loads(row["value"])
                for key, value in stored.items():
                    if key in DEFAULT_SETTINGS:
                        self.settings[key] = value
            except Exception:
                pass
        # Old builds shipped 11080/8120. Move them once so an existing database
        # does not keep binding ports the operator no longer wants.
        if self.settings["socks_port"] == 11080:
            self.settings["socks_port"] = DEFAULT_SETTINGS["socks_port"]
        if self.settings["http_port"] == 8120:
            self.settings["http_port"] = DEFAULT_SETTINGS["http_port"]
        # 12 s per upstream attempt made a dead proxy feel like a hang; the
        # retry ladder covers the same ground faster.
        if float(self.settings["timeout"]) == 12.0:
            self.settings["timeout"] = DEFAULT_SETTINGS["timeout"]
        return self.settings

    async def apply_settings(self, patch: dict) -> dict:
        allowed = set(DEFAULT_SETTINGS)
        for key, value in patch.items():
            if key not in allowed:
                continue
            if key in ("socks_port", "http_port", "max_fails", "retries",
                       "health_batch", "verified_window"):
                value = int(value)
            elif key in ("timeout", "quota_mb", "health_interval", "hedge_delay",
                         "deadline", "first_byte_timeout", "idle_timeout"):
                value = float(value)
            elif key == "enabled_protocols":
                value = [p for p in value if p in ("http", "socks4", "socks5")]
            self.settings[key] = value
        await execute(
            "INSERT INTO kv (key, value) VALUES ('gateway', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (json.dumps(self.settings),),
        )
        if self.settings["quota_mb"]:
            await execute(
                "UPDATE proxies SET quota_bytes=? WHERE quota_bytes=0",
                (int(float(self.settings["quota_mb"]) * 1024 * 1024),),
            )
        return self.settings

    # ── lifecycle ───────────────────────────────────────────────────
    async def start(self) -> dict:
        if self.running:
            return {"ok": True, "already": True}
        await self.load_settings()
        host = self.settings["host"]
        try:
            self.servers = [
                await asyncio.start_server(self._handle_socks, host,
                                           int(self.settings["socks_port"])),
                await asyncio.start_server(self._handle_http, host,
                                           int(self.settings["http_port"])),
            ]
        except OSError as exc:
            await self.stop()
            return {"ok": False, "error": f"bind failed: {exc}"}
        self.running = True
        self.started_at = time.time()
        self.last_error = ""
        self._flush_task = asyncio.create_task(self._flush_loop())
        self._health_task = asyncio.create_task(self._health_loop())
        # Warm one pass immediately: a gateway that starts on stale flags serves
        # yesterday's pool for the first half minute otherwise.
        self._warm_task = asyncio.create_task(self._health_pass())
        return {"ok": True,
                "socks": f"{host}:{self.settings['socks_port']}",
                "http": f"{host}:{self.settings['http_port']}"}

    async def stop(self) -> dict:
        self.running = False
        for server in self.servers:
            server.close()
            try:
                await server.wait_closed()
            except Exception:
                pass
        self.servers = []
        if self._flush_task:
            self._flush_task.cancel()
            self._flush_task = None
        if self._health_task:
            self._health_task.cancel()
            self._health_task = None
        if self._warm_task:
            self._warm_task.cancel()
            self._warm_task = None
        await self._flush_all()
        return {"ok": True}

    # ── pool selection ──────────────────────────────────────────────
    async def _pick(self, require_tunnel: bool = False,
                    avoid: set[tuple[str, int, str]] | None = None,
                    host: str | None = None) -> dict | None:
        protocols = self.settings["enabled_protocols"] or ["http"]
        marks = ",".join("?" * len(protocols))
        where = (f"WHERE alive=1 AND excluded=0 AND protocol IN ({marks}) "
                 "AND (quota_bytes=0 OR bytes_in + bytes_out < quota_bytes)")
        params: list = list(protocols)
        if require_tunnel:
            # A proxy that answers http:// but drops CONNECT/TLS cannot serve an
            # https:// client. The validator records that capability in `https`
            # for every protocol, so only tunnel-capable rows may serve CONNECT.
            where += " AND https=1"
            # Once enough rows have proven themselves recently, serve only from
            # that set: the fresh half of a free pool is where the success rate
            # actually lives. Below the floor, fall back to the wider pool.
            cutoff = time.strftime(
                "%Y-%m-%dT%H:%M:%S",
                time.localtime(time.time() - float(self.settings["verified_window"])))
            if time.time() - self._hot_at > 5:
                async with db().execute(
                    "SELECT COUNT(*) c FROM proxies WHERE alive=1 AND excluded=0 "
                    "AND https=1 AND verified_at >= ?", (cutoff,)
                ) as cur:
                    self._hot = (await cur.fetchone())["c"]
                self._hot_at = time.time()
            if self._hot >= 12 and self.active < 6:
                where += " AND verified_at >= ?"
                params.append(cutoff)
        # Freshness beats raw latency on a pool that rots by the minute, but
        # rotation still has to spread: hammering the same verified exits gets
        # the whole pool 429'd by the target that matters.
        fresh = "verified_at IS NULL, verified_at DESC"
        spread = "last_used IS NULL, last_used ASC"
        order = {
            "round_robin": f"{spread}, {fresh}, latency_ms IS NULL, latency_ms",
            "least_used": f"requests ASC, {spread}, {fresh}",
            "fastest": f"{fresh}, latency_ms IS NULL, latency_ms, requests ASC",
        }.get(self.settings["strategy"], spread)
        async with self._load_lock:
            async with db().execute(
                f"SELECT ip, port, protocol, latency_ms FROM proxies {where} "
                f"ORDER BY {order} LIMIT 48",
                tuple(params),
            ) as cur:
                rows = [dict(r) for r in await cur.fetchall()]
            if avoid:
                rows = [r for r in rows
                        if (r["ip"], int(r["port"]), r["protocol"]) not in avoid]
            if not rows:
                return None
            if host:
                # Per-target memory: a proxy that already carried traffic to
                # this exact host is worth more than a stranger with the same
                # latency. Two picks in three come from that set; the third
                # keeps exploring so the pool does not collapse onto a handful
                # of exits and get the whole target rate-limiting us.
                good = await self._target_good(host)
                if good:
                    local = [r for r in rows
                             if (r["ip"], int(r["port"]), r["protocol"]) in good]
                    self._pick_n += 1
                    if len(local) >= 4 and self._pick_n % 3:
                        rows = local
            self._rr = (self._rr + 1) % len(rows)
            return rows[self._rr]

    async def _mark_failed(self, proxy: dict, error: str) -> None:
        max_fails = int(self.settings["max_fails"])
        await execute(
            "UPDATE proxies SET checks_failed = checks_failed + 1, "
            "alive = CASE WHEN checks_failed + 1 >= ? THEN 0 ELSE alive END "
            "WHERE ip=? AND port=? AND protocol=?",
            (max_fails, proxy["ip"], proxy["port"], proxy["protocol"]),
        )

    async def _target_good(self, host: str) -> set[tuple[str, int, str]]:
        """Proxies that recently carried traffic to this exact host."""
        now = time.time()
        cached = self._target_cache.get(host)
        if cached and now - cached[0] < 10:
            return cached[1]
        cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now - 1800))
        good: set[tuple[str, int, str]] = set()
        async with db().execute(
            "SELECT ip, port, protocol FROM target_hits "
            "WHERE host=? AND ok>0 AND (last_ok IS NULL OR last_ok >= ?) "
            "ORDER BY last_ok DESC LIMIT 240",
            (host, cutoff),
        ) as cur:
            for row in await cur.fetchall():
                good.add((row["ip"], int(row["port"]), row["protocol"]))
        self._target_cache[host] = (now, good)
        return good

    async def _record_target(self, host: str, proxy: dict, ok: bool) -> None:
        if not host:
            return
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            await execute(
                "INSERT INTO target_hits (host, ip, port, protocol, ok, fail, "
                "last_ok, last_fail) VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(host, ip, port, protocol) DO UPDATE SET "
                "ok = ok + excluded.ok, fail = fail + excluded.fail, "
                "last_ok = COALESCE(excluded.last_ok, target_hits.last_ok), "
                "last_fail = COALESCE(excluded.last_fail, target_hits.last_fail)",
                (host, proxy["ip"], proxy["port"], proxy["protocol"],
                 1 if ok else 0, 0 if ok else 1,
                 now if ok else None, None if ok else now),
            )
        except Exception:
            pass
        self._target_cache.pop(host, None)

    async def _mark_ok(self, proxy: dict, latency_ms: int) -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        await execute(
            "UPDATE proxies SET checks_failed=0, verified_at=?, last_used=?, "
            "latency_ms=CASE WHEN ? > 0 THEN ? ELSE latency_ms END "
            "WHERE ip=? AND port=? AND protocol=?",
            (now, now, latency_ms, latency_ms,
             proxy["ip"], proxy["port"], proxy["protocol"]),
        )

    async def _connect(self, host: str, port: int, require_tunnel: bool):
        """Open a tunnel with a hedged retry ladder.

        Dead rows on a free pool hang instead of refusing, so waiting for one
        attempt to time out before starting the next is what makes the gateway
        feel stuck. The next proxy starts after `hedge_delay` seconds while the
        previous one is still trying; the first handshake that lands wins and
        the rest are cancelled.
        """
        tries = max(1, int(self.settings["retries"]))
        hedge = max(0.2, float(self.settings["hedge_delay"]))
        picks: list[dict] = []
        avoid: set[tuple[str, int, str]] = set()
        for _ in range(tries):
            proxy = await self._pick(require_tunnel, avoid, host)
            if not proxy:
                break
            avoid.add((proxy["ip"], int(proxy["port"]), proxy["protocol"]))
            picks.append(proxy)
        if not picks:
            raise NoProxyAvailable("no proxy available")

        async def attempt(proxy: dict, delay: float):
            if delay:
                await asyncio.sleep(delay)
            started = time.monotonic()
            up_r, up_w = await self._open(proxy, host, port)
            return up_r, up_w, proxy, started

        usage = {asyncio.create_task(attempt(p, i * hedge)): p
                 for i, p in enumerate(picks)}
        errors: list[Exception] = []
        deadline = float(self.settings["deadline"])
        try:
            async with asyncio.timeout(deadline):
                while usage:
                    done, _ = await asyncio.wait(list(usage),
                                                 return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        proxy = usage.pop(task)
                        exc = task.exception()
                        if exc is None:
                            up_r, up_w, proxy, started = task.result()
                            return up_r, up_w, proxy, started
                        errors.append(exc)
                        self.fails += 1
                        self.last_error = f"{type(exc).__name__}: {exc}"
                        await self._mark_failed(proxy, str(exc))
        except TimeoutError:
            self.fails += 1
            self.last_error = f"no tunnel within {deadline:.0f}s"
            raise
        finally:
            if usage:
                for task in usage:
                    task.cancel()
                await asyncio.gather(*usage, return_exceptions=True)
        raise errors[-1] if errors else NoProxyAvailable("no proxy available")

    # ── background health ───────────────────────────────────────────
    async def _health_loop(self) -> None:
        while self.running:
            try:
                await self._health_pass()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"health: {type(exc).__name__}: {exc}"[:200]
            await asyncio.sleep(max(10.0, float(self.settings["health_interval"])))

    async def _health_pass(self) -> None:
        """Re-probe the stalest rows so `alive` and `https` stay current."""
        from app.validator import check

        batch = max(1, int(self.settings["health_batch"]))
        async with db().execute(
            "SELECT ip, port, protocol FROM proxies "
            "WHERE alive=1 AND excluded=0 "
            "ORDER BY (verified_at IS NULL) DESC, verified_at ASC LIMIT ?",
            (batch,),
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
        if not rows:
            return
        sem = asyncio.Semaphore(min(32, len(rows)))
        now = time.strftime("%Y-%m-%dT%H:%M:%S")

        async def probe(row: dict) -> None:
            async with sem:
                result = await check(row["ip"], row["port"], row["protocol"],
                                     timeout=float(self.settings["timeout"]))
            if result:
                # Only a proxy that carried TLS counts as verified; plain-HTTP
                # reachability says nothing about its tunnel.
                verified = now if result["https"] else None
                await execute(
                    "UPDATE proxies SET checks_failed=0, verified_at=?, "
                    "latency_ms=?, anonymity=?, https=? "
                    "WHERE ip=? AND port=? AND protocol=?",
                    (verified, result["latency_ms"], result["anonymity"],
                     result["https"], row["ip"], row["port"], row["protocol"]),
                )
            else:
                await self._mark_failed(row, "health probe failed")

        await asyncio.gather(*(probe(row) for row in rows),
                             return_exceptions=True)


    # ── upstream tunnels ────────────────────────────────────────────
    async def _open(self, proxy: dict, host: str, port: int):
        # A live proxy finishes its handshake in well under a second. Spending
        # the full request budget on a dead one is what makes the gateway feel
        # hung, so the whole open phase gets a tight ceiling.
        timeout = min(float(self.settings["timeout"]), 5.0)
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(proxy["ip"], int(proxy["port"])), timeout)
        try:
            if proxy["protocol"] == "http":
                writer.write(f"CONNECT {host}:{port} HTTP/1.1\r\n".encode()
                             + f"Host: {host}:{port}\r\n\r\n".encode())
                await asyncio.wait_for(writer.drain(), timeout)
                status = await asyncio.wait_for(reader.readline(), timeout)
                if b" 200" not in status:
                    raise OSError(f"upstream CONNECT refused: {status[:60]!r}")
                while True:  # consume the rest of the headers
                    line = await asyncio.wait_for(reader.readline(), timeout)
                    if line in (b"\r\n", b"\n", b""):
                        break
            elif proxy["protocol"] == "socks5":
                writer.write(b"\x05\x01\x00")
                await asyncio.wait_for(writer.drain(), timeout)
                greeting = await asyncio.wait_for(reader.readexactly(2), timeout)
                if greeting[1] != 0x00:
                    raise OSError(f"socks5 auth required ({greeting[1]})")
                atyp, addr = _addr_bytes(host)
                writer.write(b"\x05\x01\x00" + bytes([atyp]) + addr
                             + struct.pack(">H", port))
                await asyncio.wait_for(writer.drain(), timeout)
                reply = await asyncio.wait_for(reader.readexactly(4), timeout)
                if reply[1] != 0x00:
                    raise OSError(f"socks5 connect refused (code={reply[1]})")
                if reply[3] == 0x01:
                    await reader.readexactly(6)
                elif reply[3] == 0x04:
                    await reader.readexactly(18)
                elif reply[3] == 0x03:
                    length = (await reader.readexactly(1))[0]
                    await reader.readexactly(length + 2)
            elif proxy["protocol"] == "socks4":
                ip = ipaddress.ip_address(socket.gethostbyname(host)).packed
                writer.write(b"\x04\x01" + struct.pack(">H", port) + ip
                             + b"\x00" + b"\x00")
                await asyncio.wait_for(writer.drain(), timeout)
                reply = await asyncio.wait_for(reader.readexactly(8), timeout)
                if reply[1] != 0x5A:
                    raise OSError(f"socks4 connect refused (code={reply[1]})")
            else:
                raise OSError(f"unsupported protocol {proxy['protocol']}")
            return reader, writer
        except BaseException:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            raise

    # ── relay ───────────────────────────────────────────────────────
    async def _relay(self, client_r, client_w, up_r, up_w, proxy: dict,
                     started: float | None = None, host: str | None = None) -> None:
        session = Session((proxy["ip"], int(proxy["port"]), proxy["protocol"]))
        sid = id(session)
        self.sessions[sid] = session
        self.active += 1

        async def pump(src, dst, direction: str):
            idle = float(self.settings["idle_timeout"])
            try:
                while True:
                    try:
                        chunk = await asyncio.wait_for(src.read(65536), idle)
                    except TimeoutError:
                        # Half a tunnel that stops moving is worse than a closed
                        # one: the client waits for its own timeout otherwise.
                        break
                    if not chunk:
                        break
                    dst.write(chunk)
                    await dst.drain()
                    if direction == "in":
                        session.bytes_out += len(chunk)
                    else:
                        session.bytes_in += len(chunk)
            except Exception:
                pass
            finally:
                try:
                    dst.close()
                except Exception:
                    pass

        pumps = [asyncio.create_task(pump(client_r, up_w, "in")),
                 asyncio.create_task(pump(up_r, client_w, "out"))]
        try:
            # A tunnel that completes its handshake and then says nothing is the
            # slowest failure mode there is: the client waits for its own
            # timeout. Give the upstream one short window to speak, then cut it.
            silence = float(self.settings["first_byte_timeout"])
            _, pending = await asyncio.wait(pumps, timeout=silence)
            if pending and session.bytes_in == 0:
                for task in pending:
                    task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        finally:
            self.sessions.pop(sid, None)
            self.active -= 1
            await self._persist_session(session)
            # Verification is evidence, not intention: a row counts as verified
            # only once the upstream actually sent bytes back. A row that
            # accepts CONNECT and then says nothing never earns the rank.
            latency = int((time.monotonic() - started) * 1000) if started else 0
            if session.bytes_in > 0:
                await self._mark_ok(proxy, latency)
                await self._record_target(host, proxy, True)
            elif session.bytes_out > 0:
                await self._mark_failed(proxy, "tunnel carried no upstream data")
                await self._record_target(host, proxy, False)

    async def _persist_session(self, session: Session) -> None:
        if not (session.bytes_in or session.bytes_out):
            return
        self.bytes_in += session.bytes_in
        self.bytes_out += session.bytes_out
        self._sample["in"] += session.bytes_in
        self._sample["out"] += session.bytes_out
        self._sample["req"] += 1
        await execute(
            "UPDATE proxies SET bytes_in = bytes_in + ?, bytes_out = bytes_out + ?, "
            "requests = requests + 1, last_used = ? "
            "WHERE ip=? AND port=? AND protocol=?",
            (session.bytes_in, session.bytes_out,
             time.strftime("%Y-%m-%dT%H:%M:%S"), *session.key),
        )

    async def _flush_loop(self) -> None:
        """Flush live counters every 2 s so long connections show progress."""
        while self.running:
            await asyncio.sleep(2)
            await self._flush_all()
            if time.time() - self._sample["at"] >= 30:
                await self._write_sample()

    async def _write_sample(self) -> None:
        sample, self._sample = self._sample, {"in": 0, "out": 0, "req": 0,
                                              "at": time.time()}
        if not (sample["in"] or sample["out"] or sample["req"]):
            return
        await execute(
            "INSERT INTO traffic_samples (ts, bytes_in, bytes_out, requests) "
            "VALUES (?,?,?,?) ON CONFLICT(ts) DO UPDATE SET "
            "bytes_in=bytes_in+excluded.bytes_in, "
            "bytes_out=bytes_out+excluded.bytes_out, "
            "requests=requests+excluded.requests",
            (time.strftime("%Y-%m-%dT%H:%M:%S"), sample["in"], sample["out"],
             sample["req"]),
        )

    async def _flush_all(self) -> None:
        for session in list(self.sessions.values()):
            if not (session.bytes_in or session.bytes_out):
                continue
            delta_in, delta_out = session.bytes_in, session.bytes_out
            session.bytes_in = session.bytes_out = 0
            self.bytes_in += delta_in
            self.bytes_out += delta_out
            self._sample["in"] += delta_in
            self._sample["out"] += delta_out
            try:
                await execute(
                    "UPDATE proxies SET bytes_in = bytes_in + ?, "
                    "bytes_out = bytes_out + ? WHERE ip=? AND port=? AND protocol=?",
                    (delta_in, delta_out, *session.key),
                )
            except Exception:
                pass

    # ── client handlers ─────────────────────────────────────────────
    async def _handle_socks(self, reader, writer) -> None:
        try:
            greeting = await asyncio.wait_for(reader.readexactly(2), 30)
            if greeting[0] != 0x05:
                return
            methods = await asyncio.wait_for(reader.readexactly(greeting[1]), 30)
            if 0x00 in methods:
                writer.write(b"\x05\x00")
                await writer.drain()
            elif 0x02 in methods:
                writer.write(b"\x05\x02")
                await writer.drain()
                await reader.readexactly(2)
                await reader.readexactly((await reader.readexactly(1))[0])
                await reader.readexactly((await reader.readexactly(1))[0])
                writer.write(b"\x01\x00")
                await writer.drain()
            else:
                writer.write(b"\x05\xff")
                await writer.drain()
                return

            head = await asyncio.wait_for(reader.readexactly(4), 30)
            if head[0] != 0x05 or head[1] != 0x01:
                writer.write(b"\x05\x07\x00\x01" + b"\x00" * 6)
                await writer.drain()
                return
            atyp = head[3]
            if atyp == 0x01:
                host = socket.inet_ntoa(await reader.readexactly(4))
            elif atyp == 0x04:
                host = socket.inet_ntop(socket.AF_INET6, await reader.readexactly(16))
            elif atyp == 0x03:
                host = (await reader.readexactly((await reader.readexactly(1))[0])).decode()
            else:
                return
            port = struct.unpack(">H", await reader.readexactly(2))[0]

            try:
                up_r, up_w, proxy, started = await self._connect(host, port, port == 443)
            except NoProxyAvailable:
                writer.write(b"\x05\x01\x00\x01" + b"\x00" * 6)
                await writer.drain()
                return
            except Exception:
                writer.write(b"\x05\x05\x00\x01" + b"\x00" * 6)
                await writer.drain()
                return

            writer.write(b"\x05\x00\x00\x01" + b"\x00" * 6)
            await writer.drain()
            self.connections += 1
            await self._relay(reader, writer, up_r, up_w, proxy, started, host)
        except Exception:
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass

    async def _handle_http(self, reader, writer) -> None:
        try:
            head = b""
            while b"\r\n\r\n" not in head and len(head) < 65536:
                chunk = await asyncio.wait_for(reader.read(4096), 30)
                if not chunk:
                    break
                head += chunk
            if not head:
                return
            first, _, rest = head.partition(b"\r\n")
            try:
                method, target, version = first.decode("latin-1").split()
            except ValueError:
                writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                return

            if method.upper() == "CONNECT":
                host, _, raw_port = target.rpartition(":")
                try:
                    port = int(raw_port)
                except ValueError:
                    host, port = target, 443
                try:
                    up_r, up_w, proxy, started = await self._connect(host, port, True)
                except NoProxyAvailable:
                    writer.write(b"HTTP/1.1 503 No Proxy\r\nContent-Length: 0\r\n\r\n")
                    await writer.drain()
                    return
                except Exception as exc:
                    msg = f"upstream failed: {exc}".encode()
                    writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: "
                                 + str(len(msg)).encode() + b"\r\n\r\n" + msg)
                    await writer.drain()
                    return
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
                self.connections += 1
                await self._relay(reader, writer, up_r, up_w, proxy, started, host)
                return

            parts = urlsplit(target)
            if not parts.hostname:
                writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                return
            host = parts.hostname
            port = parts.port or 80
            path = parts.path or "/"
            if parts.query:
                path += "?" + parts.query
            rewritten = f"{method} {path} {version}\r\n".encode() + rest
            try:
                up_r, up_w, proxy, started = await self._connect(host, port, port == 443)
            except NoProxyAvailable:
                writer.write(b"HTTP/1.1 503 No Proxy\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                return
            except Exception:
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                return
            up_w.write(rewritten)
            await up_w.drain()
            self.connections += 1
            await self._relay(reader, writer, up_r, up_w, proxy, started, host)
        except Exception:
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass

    # ── snapshot ────────────────────────────────────────────────────
    async def snapshot(self) -> dict:
        async with db().execute(
            "SELECT COUNT(*) c, COALESCE(SUM(bytes_in+bytes_out),0) b, "
            "COALESCE(SUM(requests),0) r, "
            "SUM(CASE WHEN quota_bytes>0 THEN 1 ELSE 0 END) q, "
            "SUM(CASE WHEN verified_at IS NOT NULL THEN 1 ELSE 0 END) v, "
            "SUM(CASE WHEN https=1 THEN 1 ELSE 0 END) t "
            "FROM proxies WHERE alive=1 AND excluded=0 "
            "AND (quota_bytes=0 OR bytes_in + bytes_out < quota_bytes)"
        ) as cur:
            row = await cur.fetchone()
        pool = {"eligible": row["c"], "bytes": row["b"],
                "requests": row["r"], "quota_rows": row["q"] or 0,
                "verified": row["v"] or 0, "tunnel_capable": row["t"] or 0}
        warnings = []
        if not self.running:
            warnings.append("gateway is stopped")
        if pool["eligible"] == 0:
            warnings.append("no eligible proxy — collect a pool or clear quotas")
        elif pool["tunnel_capable"] == 0:
            warnings.append("no TLS-capable proxy — run a pool scan before serving https")
        if self.fails and self.connections:
            rate = self.fails / max(1, self.connections + self.fails)
            if rate > 0.25:
                warnings.append(f"high upstream failure rate ({rate:.0%})")
        if self.last_error:
            warnings.append(f"last error: {self.last_error}")
        return {
            "running": self.running,
            "host": self.settings["host"],
            "socks_port": self.settings["socks_port"],
            "http_port": self.settings["http_port"],
            "strategy": self.settings["strategy"],
            "quota_mb": self.settings["quota_mb"],
            "timeout": self.settings["timeout"],
            "max_fails": self.settings["max_fails"],
            "retries": self.settings["retries"],
            "hedge_delay": self.settings["hedge_delay"],
            "deadline": self.settings["deadline"],
            "first_byte_timeout": self.settings["first_byte_timeout"],
            "idle_timeout": self.settings["idle_timeout"],
            "health_interval": self.settings["health_interval"],
            "health_batch": self.settings["health_batch"],
            "enabled_protocols": self.settings["enabled_protocols"],
            "connections": self.connections,
            "fails": self.fails,
            "active": self.active,
            "bytes_in": self.bytes_in,
            "bytes_out": self.bytes_out,
            "uptime_s": int(time.time() - self.started_at) if self.running else 0,
            "pool": pool,
            "warnings": warnings,
            "last_error": self.last_error,
        }


gateway = Gateway()
