"""NovaProxy gateway — one local SOCKS5/HTTP endpoint in front of the pool.

Adapted from novastar's gateway: rotation, failover, per-proxy byte accounting
and quota enforcement. The difference is where the pool comes from — there are
no credentials here, only the validated proxy rows NovaProxy already keeps.

    app -> 127.0.0.1:1080  (SOCKS5)  \
           127.0.0.1:8120  (HTTP)     -> pool -> rotating exit
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
    "socks_port": 11080,
    "http_port": 8120,
    "strategy": "round_robin",      # round_robin | least_used | fastest
    "quota_mb": 0,                   # 0 = unlimited, applied to new rows on start
    "timeout": 12.0,
    "max_fails": 3,
    "enabled_protocols": ["http", "socks5", "socks4"],
}


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
        self._load_lock = asyncio.Lock()
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
        return self.settings

    async def apply_settings(self, patch: dict) -> dict:
        allowed = set(DEFAULT_SETTINGS)
        for key, value in patch.items():
            if key not in allowed:
                continue
            if key in ("socks_port", "http_port", "max_fails"):
                value = int(value)
            elif key in ("timeout", "quota_mb"):
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
        await self._flush_all()
        return {"ok": True}

    # ── pool selection ──────────────────────────────────────────────
    async def _pick(self) -> dict | None:
        protocols = self.settings["enabled_protocols"] or ["http"]
        marks = ",".join("?" * len(protocols))
        where = (f"WHERE alive=1 AND excluded=0 AND protocol IN ({marks}) "
                 "AND (quota_bytes=0 OR bytes_in + bytes_out < quota_bytes)")
        order = {
            "round_robin": "latency_ms IS NULL, latency_ms",
            "least_used": "requests ASC, latency_ms IS NULL, latency_ms",
            "fastest": "latency_ms IS NULL, latency_ms, requests ASC",
        }.get(self.settings["strategy"], "latency_ms IS NULL, latency_ms")
        async with self._load_lock:
            async with db().execute(
                f"SELECT ip, port, protocol, latency_ms FROM proxies {where} "
                f"ORDER BY {order} LIMIT 32",
                tuple(protocols),
            ) as cur:
                rows = [dict(r) for r in await cur.fetchall()]
            if not rows:
                return None
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

    # ── upstream tunnels ────────────────────────────────────────────
    async def _open(self, proxy: dict, host: str, port: int):
        timeout = float(self.settings["timeout"])
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
        except Exception:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            raise

    # ── relay ───────────────────────────────────────────────────────
    async def _relay(self, client_r, client_w, up_r, up_w, proxy: dict) -> None:
        session = Session((proxy["ip"], int(proxy["port"]), proxy["protocol"]))
        sid = id(session)
        self.sessions[sid] = session
        self.active += 1

        async def pump(src, dst, direction: str):
            try:
                while True:
                    chunk = await src.read(65536)
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

        try:
            await asyncio.gather(
                pump(client_r, up_w, "in"),
                pump(up_r, client_w, "out"),
            )
        finally:
            self.sessions.pop(sid, None)
            self.active -= 1
            await self._persist_session(session)

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

            proxy = await self._pick()
            if not proxy:
                writer.write(b"\x05\x01\x00\x01" + b"\x00" * 6)
                await writer.drain()
                return
            try:
                up_r, up_w = await self._open(proxy, host, port)
            except Exception as exc:
                self.fails += 1
                self.last_error = f"{type(exc).__name__}: {exc}"
                await self._mark_failed(proxy, str(exc))
                writer.write(b"\x05\x05\x00\x01" + b"\x00" * 6)
                await writer.drain()
                return

            writer.write(b"\x05\x00\x00\x01" + b"\x00" * 6)
            await writer.drain()
            self.connections += 1
            await self._relay(reader, writer, up_r, up_w, proxy)
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
                proxy = await self._pick()
                if not proxy:
                    writer.write(b"HTTP/1.1 503 No Proxy\r\nContent-Length: 0\r\n\r\n")
                    await writer.drain()
                    return
                try:
                    up_r, up_w = await self._open(proxy, host, port)
                except Exception as exc:
                    self.fails += 1
                    self.last_error = f"{type(exc).__name__}: {exc}"
                    await self._mark_failed(proxy, str(exc))
                    msg = f"upstream failed: {exc}".encode()
                    writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: "
                                 + str(len(msg)).encode() + b"\r\n\r\n" + msg)
                    await writer.drain()
                    return
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
                self.connections += 1
                await self._relay(reader, writer, up_r, up_w, proxy)
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
            proxy = await self._pick()
            if not proxy:
                writer.write(b"HTTP/1.1 503 No Proxy\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                return
            try:
                up_r, up_w = await self._open(proxy, host, port)
            except Exception as exc:
                self.fails += 1
                self.last_error = f"{type(exc).__name__}: {exc}"
                await self._mark_failed(proxy, str(exc))
                writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                return
            up_w.write(rewritten)
            await up_w.drain()
            self.connections += 1
            await self._relay(reader, writer, up_r, up_w, proxy)
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
            "SUM(CASE WHEN quota_bytes>0 THEN 1 ELSE 0 END) q "
            "FROM proxies WHERE alive=1 AND excluded=0 "
            "AND (quota_bytes=0 OR bytes_in + bytes_out < quota_bytes)"
        ) as cur:
            row = await cur.fetchone()
        pool = {"eligible": row["c"], "bytes": row["b"],
                "requests": row["r"], "quota_rows": row["q"] or 0}
        warnings = []
        if not self.running:
            warnings.append("gateway is stopped")
        if pool["eligible"] == 0:
            warnings.append("no eligible proxy — collect a pool or clear quotas")
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
