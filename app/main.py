import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request, Form
from fastapi.responses import (JSONResponse, RedirectResponse, PlainTextResponse,
                               HTMLResponse, FileResponse, StreamingResponse)
from fastapi.staticfiles import StaticFiles

from app.config import (ADMIN_USERNAME, ADMIN_PASSWORD, ADMIN_PASSWORD_GENERATED,
                        SIGNUP_SOURCES,
                        VALIDATE_TIMEOUT, VALIDATE_CONCURRENCY, MAX_FAILED_CHECKS,
                        MAX_CANDIDATES, AUTO_DEDUPE, GEO_ENRICH, GEO_MAX,
                        SITE_CHECK_TIMEOUT, SITE_CHECK_LIMIT, SITE_CHECK_CONCURRENCY,
                        AUTH_MODE)
from app.database import init_db, db, execute, executemany
from app.security import (create_user, get_user, verify_password,
                          create_session, session_user, destroy_session)
from app.engine import engine
from app.gateway import gateway
from app.sources import public
from app import sitecheck

DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await gateway.load_settings()
    if AUTO_DEDUPE:
        removed = await engine.dedupe()
        if removed:
            print(f"dedupe removed {removed} duplicate listings at startup")
    async with db().execute("SELECT COUNT(*) c FROM users") as cur:
        if (await cur.fetchone())["c"] == 0:
            await create_user(ADMIN_USERNAME, ADMIN_PASSWORD, is_admin=True)
            if ADMIN_PASSWORD_GENERATED:
                print(f"!! bootstrapped admin '{ADMIN_USERNAME}' with a generated "
                      f"password: {ADMIN_PASSWORD}")
                print("   save it now - only the hash is stored")
            else:
                print(f"!! bootstrapped admin '{ADMIN_USERNAME}' from NP_ADMIN_PASS")
    autopool_task = asyncio.create_task(_autopool_loop())
    yield
    autopool_task.cancel()
    await gateway.stop()


app = FastAPI(title="novaproxy", lifespan=lifespan)

PUBLIC_PREFIXES = ("/login", "/register", "/api/login", "/api/register",
                   "/assets/", "/favicon")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if AUTH_MODE == "local" and path in ("/login", "/register"):
        # No login screen in the local build: it exists to be used.
        return RedirectResponse("/", status_code=303)
    if path.startswith(PUBLIC_PREFIXES):
        return await call_next(request)
    user = await session_user(request.cookies.get("np_session"))
    if not user and AUTH_MODE == "local":
        # This console binds to loopback and exists to be used, not signed into.
        # A request that already reached 127.0.0.1 is the operator; anything
        # arriving from another host still needs a session.
        client = request.client.host if request.client else ""
        host = request.url.hostname or ""
        if client in ("127.0.0.1", "::1") or host in ("127.0.0.1", "localhost"):
            user = await get_user(ADMIN_USERNAME)
    if not user:
        if path.startswith("/api/"):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return RedirectResponse("/login", status_code=303)
    request.state.user = user
    return await call_next(request)


# ── auth api ───────────────────────────────────────────────────────────
@app.post("/api/login")
async def api_login(username: str = Form(...), password: str = Form(...)):
    user = await get_user(username)
    if not user or not verify_password(password, user["pass_hash"]):
        return JSONResponse({"error": "Invalid credentials"}, status_code=401)
    token = await create_session(user["id"])
    resp = JSONResponse({"ok": True})
    resp.set_cookie("np_session", token, httponly=True, samesite="lax", max_age=7 * 24 * 3600)
    return resp


@app.post("/api/register")
async def api_register(username: str = Form(...), password: str = Form(...)):
    if len(username) < 3 or len(password) < 6:
        return JSONResponse({"error": "username ≥3 chars, password ≥6 chars"}, status_code=400)
    try:
        await create_user(username, password)
    except Exception:
        return JSONResponse({"error": "username taken"}, status_code=400)
    user = await get_user(username)
    token = await create_session(user["id"])
    resp = JSONResponse({"ok": True})
    resp.set_cookie("np_session", token, httponly=True, samesite="lax", max_age=7 * 24 * 3600)
    return resp


@app.post("/api/logout")
async def api_logout(request: Request):
    token = request.cookies.get("np_session")
    if token:
        await destroy_session(token)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("np_session")
    return resp


@app.get("/api/me")
async def api_me(request: Request):
    return {"username": request.state.user["username"],
            "is_admin": bool(request.state.user["is_admin"])}


# ── engine api ─────────────────────────────────────────────────────────
@app.post("/api/collect")
async def api_collect(request: Request):
    body = await request.json()
    target = max(1, min(int(body.get("target", 100)), 50_000))
    protocols = [p for p in body.get("protocols", ["http"]) if p in ("http", "socks4", "socks5")]
    rounds = max(1, min(int(body.get("rounds", 3)), 10))
    use_custom = bool(body.get("use_custom", True))
    if not protocols:
        return JSONResponse({"error": "pick at least one protocol"}, status_code=400)
    ok = await engine.start(target, protocols, rounds, use_custom)
    return {"ok": ok, "error": None if ok else "engine busy"}


@app.post("/api/stop")
async def api_stop():
    engine.stop()
    return {"ok": True}


async def _status_payload() -> dict:
    st = dict(engine.state)
    if st["running"] and st["started_at"]:
        st["elapsed_s"] = int(time.time() - st["started_at"])
    async with db().execute("SELECT COUNT(*) c FROM proxies WHERE alive=1") as cur:
        st["alive"] = (await cur.fetchone())["c"]
    async with db().execute("SELECT COUNT(*) c FROM proxies WHERE alive=0") as cur:
        st["dead"] = (await cur.fetchone())["c"]
    st["logs"] = [{"ts": t, "level": l, "msg": m} for t, l, m in list(engine.logs)[-150:]]
    st["signup_sources"] = len(SIGNUP_SOURCES)
    return st


@app.get("/api/status")
async def api_status():
    return await _status_payload()


@app.get("/api/stream")
async def api_stream(request: Request):
    async def gen():
        while True:
            if await request.is_disconnected():
                break
            payload = await _status_payload()
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    })


# ── stats api ──────────────────────────────────────────────────────────
@app.get("/api/stats")
async def api_stats():
    async def one(sql: str, params: tuple = ()):
        async with db().execute(sql, params) as cur:
            return [dict(r) for r in await cur.fetchall()]

    totals = (await one(
        "SELECT SUM(alive=1) alive, SUM(alive=0) dead, COUNT(*) total FROM proxies"
    ))[0]
    protocols = await one(
        "SELECT protocol, COUNT(*) c, AVG(latency_ms) avg_ms FROM proxies "
        "WHERE alive=1 GROUP BY protocol ORDER BY c DESC")
    anonymity = await one(
        "SELECT anonymity, COUNT(*) c FROM proxies WHERE alive=1 GROUP BY anonymity")
    countries = await one(
        "SELECT country_code code, country, COUNT(*) c FROM proxies "
        "WHERE alive=1 AND country_code IS NOT NULL GROUP BY country_code "
        "ORDER BY c DESC LIMIT 8")
    latency = await one(
        """SELECT CASE
             WHEN latency_ms IS NULL THEN 'n/a'
             WHEN latency_ms < 250 THEN '<250'
             WHEN latency_ms < 500 THEN '250-500'
             WHEN latency_ms < 1000 THEN '500-1k'
             WHEN latency_ms < 2000 THEN '1-2k'
             ELSE '2s+' END bucket, COUNT(*) c
           FROM proxies WHERE alive=1 GROUP BY bucket""")
    duplicates = (await one(
        "SELECT COUNT(*) - COUNT(DISTINCT ip || ':' || port) c FROM proxies"
    ))[0]["c"] or 0
    return {
        "totals": {"alive": totals["alive"] or 0, "dead": totals["dead"] or 0,
                   "total": totals["total"] or 0, "duplicates": duplicates},
        "protocols": protocols,
        "anonymity": anonymity,
        "countries": countries,
        "latency": latency,
    }


@app.get("/api/settings")
async def api_settings():
    return {
        "validate_timeout": VALIDATE_TIMEOUT,
        "validate_concurrency": VALIDATE_CONCURRENCY,
        "max_failed_checks": MAX_FAILED_CHECKS,
        "max_candidates": MAX_CANDIDATES,
        "auto_dedupe": AUTO_DEDUPE,
        "site_check_timeout": SITE_CHECK_TIMEOUT,
        "site_check_limit": SITE_CHECK_LIMIT,
        "geo_enrich": GEO_ENRICH,
        "geo_max": GEO_MAX,
        "signup_sources": [s.get("name", "unnamed") for s in SIGNUP_SOURCES],
        "gateway": await gateway.snapshot(),
    }


# ── proxy data api ─────────────────────────────────────────────────────
SORTS = {
    "latency": "latency_ms IS NULL, latency_ms",
    "port": "port",
    "last_checked": "last_checked DESC",
    "country": "country IS NULL, country",
}


@app.get("/api/proxies")
async def api_proxies(protocol: str | None = None, country: str | None = None,
                      anonymity: str | None = None, q: str | None = None,
                      sort: str = "latency", offset: int = 0, limit: int = 500):
    where = "WHERE alive=1"
    params: list = []
    if protocol:
        where += " AND protocol=?"; params.append(protocol)
    if country:
        where += " AND country_code=?"; params.append(country)
    if anonymity:
        where += " AND anonymity=?"; params.append(anonymity)
    if q:
        where += " AND (ip LIKE ? OR isp LIKE ? OR country LIKE ?)"
        params += [f"%{q}%"] * 3

    async with db().execute(f"SELECT COUNT(*) c FROM proxies {where}", tuple(params)) as cur:
        total = (await cur.fetchone())["c"]

    order = SORTS.get(sort, SORTS["latency"])
    async with db().execute(
        f"SELECT * FROM proxies {where} ORDER BY {order} LIMIT ? OFFSET ?",
        tuple(params) + (min(limit, 5000), max(offset, 0)),
    ) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    async with db().execute(
        "SELECT DISTINCT country_code FROM proxies WHERE alive=1 AND country_code IS NOT NULL"
    ) as cur:
        countries = sorted(r["country_code"] for r in await cur.fetchall())
    return {"proxies": rows, "countries": countries, "total": total}


@app.get("/api/proxies/export")
async def api_export(protocol: str | None = None, fmt: str = "txt"):
    sql = "SELECT ip, port, protocol, anonymity, latency_ms, country_code FROM proxies WHERE alive=1"
    params: list = []
    if protocol:
        sql += " AND protocol=?"; params.append(protocol)
    sql += " ORDER BY latency_ms IS NULL, latency_ms"
    async with db().execute(sql, tuple(params)) as cur:
        rows = await cur.fetchall()
    if fmt == "json":
        return JSONResponse([dict(r) for r in rows])
    lines = [f'{r["protocol"]}://{r["ip"]}:{r["port"]}' for r in rows]
    return PlainTextResponse("\n".join(lines), headers={
        "Content-Disposition": "attachment; filename=proxies.txt"})


@app.post("/api/proxies/purge-dead")
async def api_purge_dead():
    async with db().execute("SELECT COUNT(*) c FROM proxies WHERE alive=0") as cur:
        removed = (await cur.fetchone())["c"]
    await execute("DELETE FROM proxies WHERE alive=0")
    engine.log("info", f"purged {removed} dead proxies")
    return {"ok": True, "removed": removed}


@app.post("/api/proxies/recheck")
async def api_recheck():
    ok = await engine.start_recheck()
    if not ok:
        return JSONResponse({"ok": False, "error": "engine busy"}, status_code=409)
    return {"ok": True}


# ── dedupe + site checks ───────────────────────────────────────────────
@app.post("/api/proxies/dedupe")
async def api_dedupe():
    if engine.busy():
        return JSONResponse({"ok": False, "error": "engine busy"}, status_code=409)
    removed = await engine.dedupe()
    engine.log("info", f"dedupe removed {removed} duplicate listings")
    return {"ok": True, "removed": removed}


@app.post("/api/proxies/test")
async def api_test_proxies(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)

    url = str(body.get("url", "")).strip()
    if not url.startswith(("http://", "https://")):
        return JSONResponse({"error": "url must start with http:// or https://"},
                            status_code=400)

    protocol = body.get("protocol") or None
    country = body.get("country") or None
    anonymity = body.get("anonymity") or None
    limit = max(1, min(int(body.get("limit", SITE_CHECK_LIMIT)), 200))
    timeout = max(2.0, min(float(body.get("timeout", SITE_CHECK_TIMEOUT)), 30.0))

    sql = "SELECT ip, port, protocol, country_code, isp FROM proxies WHERE alive=1"
    params: list = []
    if protocol:
        sql += " AND protocol=?"; params.append(protocol)
    if country:
        sql += " AND country_code=?"; params.append(country)
    if anonymity:
        sql += " AND anonymity=?"; params.append(anonymity)
    sql += " ORDER BY latency_ms IS NULL, latency_ms LIMIT ?"
    params.append(limit)
    async with db().execute(sql, tuple(params)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]

    if not rows:
        return {"url": url, "total": 0, "passed": 0, "failed": 0,
                "avg_latency_ms": None, "results": []}

    items = [(r["ip"], r["port"], r["protocol"]) for r in rows]
    results = await sitecheck.test_many(
        items, url, timeout=timeout, concurrency=SITE_CHECK_CONCURRENCY)
    meta = {(r["ip"], r["port"], r["protocol"]): r for r in rows}
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    merged = []
    for result in results:
        source = meta.get((result["ip"], result["port"], result["protocol"]), {})
        merged.append({
            **result,
            "country_code": source.get("country_code"),
            "isp": source.get("isp"),
            "checked_at": checked_at,
        })

    await executemany(
        """INSERT INTO site_checks
             (ip, port, protocol, url, ok, status, latency_ms, error, checked_at)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(ip, port, protocol, url) DO UPDATE SET
             ok=excluded.ok, status=excluded.status,
             latency_ms=excluded.latency_ms, error=excluded.error,
             checked_at=excluded.checked_at""",
        [(r["ip"], r["port"], r["protocol"], url, int(r["ok"]), r["status"],
          r["latency_ms"], r["error"], checked_at) for r in merged],
    )

    passed = sum(1 for r in merged if r["ok"])
    latencies = [r["latency_ms"] for r in merged if r["ok"] and r["latency_ms"] is not None]
    return {
        "url": url,
        "total": len(merged),
        "passed": passed,
        "failed": len(merged) - passed,
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
        "results": merged,
    }


@app.get("/api/site-checks")
async def api_site_checks(url: str | None = None, limit: int = 100):
    sql = "SELECT * FROM site_checks"
    params: list = []
    if url:
        sql += " WHERE url=?"
        params.append(url)
    sql += " ORDER BY checked_at DESC LIMIT ?"
    params.append(max(1, min(limit, 500)))
    async with db().execute(sql, tuple(params)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    return {"checks": rows}


# ── gateway api ────────────────────────────────────────────────────────
@app.get("/api/gateway")
async def api_gateway():
    return await gateway.snapshot()


@app.post("/api/gateway/start")
async def api_gateway_start():
    return await gateway.start()


@app.post("/api/gateway/stop")
async def api_gateway_stop():
    return await gateway.stop()


@app.post("/api/gateway/drop-dead")
async def api_gateway_drop_dead():
    """Persistently exclude every proxy currently marked dead."""
    async with db().execute("SELECT COUNT(*) c FROM proxies WHERE alive=0 AND excluded=0") as cur:
        count = (await cur.fetchone())["c"]
    await execute("UPDATE proxies SET excluded=1 WHERE alive=0")
    return {"ok": True, "dropped": count}


@app.post("/api/gateway/restore")
async def api_gateway_restore():
    """Return every excluded proxy to rotation."""
    async with db().execute("SELECT COUNT(*) c FROM proxies WHERE excluded=1") as cur:
        count = (await cur.fetchone())["c"]
    await execute("UPDATE proxies SET excluded=0")
    return {"ok": True, "restored": count}


@app.post("/api/gateway/scan")
async def api_gateway_scan():
    """Re-validate the eligible pool before trusting the alive flag.

    novastar probes every credential before serving; the same discipline is
    needed here because public lists rot between harvests.
    """
    from app.validator import check_batch

    async with db().execute(
        "SELECT ip, port, protocol FROM proxies WHERE alive=1 AND excluded=0"
    ) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    if not rows:
        return {"ok": True, "checked": 0, "alive": 0}

    items = [(r["ip"], r["port"], r["protocol"]) for r in rows]
    passed: list[tuple] = []
    failed: list[tuple] = []
    done = [0]

    async def on_result(res, item):
        if res:
            passed.append((res["anonymity"], res["latency_ms"], res["https"],
                           time.strftime("%Y-%m-%dT%H:%M:%S"), *item))
        else:
            failed.append(item)

    def progress():
        done[0] += 1

    await check_batch(items, min(200, max(20, len(items))), on_result, progress,
                      timeout=8.0)
    if passed:
        await executemany(
            "UPDATE proxies SET anonymity=?, latency_ms=?, https=?, last_checked=?, "
            "checks_failed=0 WHERE ip=? AND port=? AND protocol=?",
            passed,
        )
    if failed:
        await executemany(
            "UPDATE proxies SET checks_failed = checks_failed + 1, "
            "alive = CASE WHEN checks_failed + 1 >= ? THEN 0 ELSE alive END, "
            "last_checked=? WHERE ip=? AND port=? AND protocol=?",
            [(MAX_FAILED_CHECKS, time.strftime("%Y-%m-%dT%H:%M:%S"),
              i[0], i[1], i[2]) for i in failed],
        )
    alive = (await (await db().execute(
        "SELECT COUNT(*) c FROM proxies WHERE alive=1 AND excluded=0")).fetchone())["c"]
    engine.log("info", f"gateway scan: {len(passed)}/{len(items)} alive, {len(failed)} failed")
    return {"ok": True, "checked": len(items), "alive": alive,
            "passed": len(passed), "failed": len(failed)}


@app.post("/api/gateway/settings")
async def api_gateway_settings(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "expected an object"}, status_code=400)
    return await gateway.apply_settings(body)


@app.post("/api/proxies/quota")
async def api_set_quota(request: Request):
    """Set the byte allowance for one proxy, a list, or the whole pool."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    mb = max(0.0, float(body.get("mb", 0)))
    quota = int(mb * 1024 * 1024)
    if body.get("scope") == "all":
        await execute("UPDATE proxies SET quota_bytes=?", (quota,))
        return {"ok": True, "updated": "all", "quota_bytes": quota}
    items = body.get("items") or []
    if not items:
        return JSONResponse({"error": "items or scope=all required"}, status_code=400)
    await executemany(
        "UPDATE proxies SET quota_bytes=? WHERE ip=? AND port=? AND protocol=?",
        [(quota, i["ip"], int(i["port"]), i["protocol"]) for i in items],
    )
    return {"ok": True, "updated": len(items), "quota_bytes": quota}


@app.post("/api/proxies/exclude")
async def api_set_excluded(request: Request):
    """Drop rows from gateway rotation without deleting them."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    excluded = 1 if body.get("excluded", True) else 0
    if body.get("scope") == "all":
        await execute("UPDATE proxies SET excluded=?", (excluded,))
        return {"ok": True, "updated": "all", "excluded": bool(excluded)}
    items = body.get("items") or []
    if not items:
        return JSONResponse({"error": "items or scope=all required"}, status_code=400)
    await executemany(
        "UPDATE proxies SET excluded=? WHERE ip=? AND port=? AND protocol=?",
        [(excluded, i["ip"], int(i["port"]), i["protocol"]) for i in items],
    )
    return {"ok": True, "updated": len(items), "excluded": bool(excluded)}


# ── analytics api ──────────────────────────────────────────────────────
@app.get("/api/analytics")
async def api_analytics():
    async def rows(sql: str, params: tuple = ()):
        async with db().execute(sql, params) as cur:
            return [dict(r) for r in await cur.fetchall()]

    totals = (await rows(
        "SELECT COUNT(*) total, SUM(alive=1) alive, SUM(alive=0) dead, "
        "SUM(excluded=1) excluded, "
        "SUM(CASE WHEN quota_bytes>0 AND bytes_in+bytes_out>=quota_bytes "
        "THEN 1 ELSE 0 END) exhausted, "
        "COALESCE(SUM(requests),0) requests, "
        "COALESCE(SUM(bytes_in),0) bytes_in, "
        "COALESCE(SUM(bytes_out),0) bytes_out "
        "FROM proxies"))[0]
    protocols = await rows(
        "SELECT protocol, COUNT(*) c, "
        "COALESCE(SUM(bytes_in+bytes_out),0) bytes, "
        "COALESCE(SUM(requests),0) requests, "
        "AVG(latency_ms) avg_ms "
        "FROM proxies WHERE alive=1 GROUP BY protocol ORDER BY c DESC")
    top = await rows(
        "SELECT ip, port, protocol, requests, bytes_in, bytes_out, quota_bytes, "
        "latency_ms, country_code FROM proxies "
        "WHERE bytes_in+bytes_out > 0 ORDER BY bytes_in+bytes_out DESC LIMIT 10")
    quota = await rows(
        "SELECT CASE WHEN quota_bytes=0 THEN 'unlimited' "
        "WHEN bytes_in+bytes_out >= quota_bytes THEN 'exhausted' "
        "WHEN (bytes_in+bytes_out)*2 >= quota_bytes THEN 'half' "
        "ELSE 'fresh' END bucket, COUNT(*) c FROM proxies GROUP BY bucket")
    samples = await rows(
        "SELECT ts, bytes_in, bytes_out, requests FROM traffic_samples "
        "ORDER BY ts DESC LIMIT 60")
    checks = (await rows(
        "SELECT COUNT(*) c, SUM(ok=1) passed FROM (SELECT ok FROM site_checks "
        "ORDER BY checked_at DESC LIMIT 200)"))[0]
    return {
        "totals": {k: (v or 0) for k, v in totals.items()},
        "protocols": protocols,
        "top": top,
        "quota": quota,
        "samples": list(reversed(samples)),
        "site_checks": {"recent": checks["c"] or 0, "passed": checks["passed"] or 0},
        "gateway": await gateway.snapshot(),
    }



# ── source registry + auto pool ────────────────────────────────────────
AUTOPOOL_DEFAULTS = {
    "enabled": True,
    "min_alive": 250,
    "min_tls": 35,
    "interval_min": 20,
    "target": 500,
}


async def _kv_get(key: str) -> dict:
    async with db().execute("SELECT value FROM kv WHERE key=?", (key,)) as cur:
        row = await cur.fetchone()
    if not row:
        return {}
    try:
        return json.loads(row["value"])
    except Exception:
        return {}


async def _kv_set(key: str, value: dict) -> None:
    await execute(
        "INSERT INTO kv (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value)),
    )


async def _autopool_cfg() -> dict:
    cfg = dict(AUTOPOOL_DEFAULTS)
    cfg.update(await _kv_get("autopool"))
    return cfg


async def _pool_counts() -> dict:
    async with db().execute(
        "SELECT COALESCE(SUM(alive),0) alive, "
        "COALESCE(SUM(CASE WHEN alive=1 AND https=1 THEN 1 ELSE 0 END),0) tls, "
        "COUNT(*) total FROM proxies"
    ) as cur:
        row = await cur.fetchone()
    return {"alive": row["alive"], "tls": row["tls"], "total": row["total"]}


async def _autopool_loop() -> None:
    """Keep the pool from draining: harvest again when it falls below the floor.

    The loop polls every 30 s so a settings change takes effect immediately,
    and remembers when it last ran so `interval_min` still throttles it.
    """
    last = 0.0
    while True:
        try:
            cfg = await _autopool_cfg()
            interval = max(60.0, float(cfg["interval_min"]) * 60.0)
            if cfg["enabled"] and not engine.busy() and time.time() - last >= interval:
                counts = await _pool_counts()
                if counts["alive"] < cfg["min_alive"] or counts["tls"] < cfg["min_tls"]:
                    last = time.time()
                    engine.log("info", f"auto-pool: alive {counts['alive']} / tls "
                                       f"{counts['tls']} below floor — harvesting "
                                       f"{cfg['target']}")
                    await engine.start(int(cfg["target"]),
                                       ["http", "socks4", "socks5"], 2, False)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            engine.log("warn", f"auto-pool error: {type(exc).__name__}: {exc}")
        await asyncio.sleep(30)


@app.get("/api/sources")
async def api_sources():
    async with db().execute(
        "SELECT url, protocol, enabled, builtin, note, added_at, last_ok, last_rows "
        "FROM sources ORDER BY enabled DESC, builtin DESC, protocol, url"
    ) as cur:
        items = [dict(r) for r in await cur.fetchall()]
    return {"items": items}


@app.post("/api/sources")
async def api_source_add(request: Request):
    body = await request.json()
    url = str(body.get("url", "")).strip()
    protocol = str(body.get("protocol", "http"))
    if not url.startswith(("http://", "https://")) or protocol not in ("http", "socks4", "socks5"):
        return JSONResponse(
            {"error": "url must start with http(s):// and protocol be http|socks4|socks5"},
            status_code=400)
    rows, detail = await public.probe(url, protocol)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    await execute(
        "INSERT INTO sources (url, protocol, enabled, builtin, note, last_rows, last_ok) "
        "VALUES (?,?,?,?,?,?,?) ON CONFLICT(url, protocol) DO UPDATE SET "
        "enabled=1, last_rows=excluded.last_rows, last_ok=excluded.last_ok, "
        "note=excluded.note",
        (url, protocol, 1, 0, body.get("note"), rows, now if rows else None),
    )
    return {"ok": True, "rows": rows, "detail": detail}


@app.post("/api/sources/toggle")
async def api_source_toggle(request: Request):
    body = await request.json()
    await execute("UPDATE sources SET enabled=? WHERE url=? AND protocol=?",
                  (1 if body.get("enabled") else 0, body.get("url"), body.get("protocol")))
    return {"ok": True}


@app.post("/api/sources/remove")
async def api_source_remove(request: Request):
    body = await request.json()
    await execute("DELETE FROM sources WHERE url=? AND protocol=? AND builtin=0",
                  (body.get("url"), body.get("protocol")))
    return {"ok": True}


@app.get("/api/autopool")
async def api_autopool():
    cfg = await _autopool_cfg()
    return {**cfg, "counts": await _pool_counts(), "busy": engine.busy()}


@app.post("/api/autopool")
async def api_autopool_set(request: Request):
    body = await request.json()
    cfg = await _autopool_cfg()
    for key in AUTOPOOL_DEFAULTS:
        if key in body:
            cfg[key] = bool(body[key]) if key == "enabled" else int(body[key])
    await _kv_set("autopool", cfg)
    return cfg


if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

@app.get("/{full_path:path}", response_class=HTMLResponse)
async def spa(full_path: str):
    if full_path.startswith("api/"):
        return JSONResponse({"error": "not found"}, status_code=404)
    candidate = (DIST / full_path).resolve()
    if full_path and candidate.is_file() and DIST.resolve() in candidate.parents:
        return FileResponse(candidate)
    index = DIST / "index.html"
    if not index.exists():
        return HTMLResponse(
            "<h1>Frontend not built</h1><p>Run <code>cd web &amp;&amp; npm install &amp;&amp; npm run build</code>.</p>",
            status_code=503)
    return FileResponse(index)
