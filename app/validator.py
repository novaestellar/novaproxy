"""Concurrent proxy health/anonymity checker."""
import asyncio
import os
import time

import aiohttp
from aiohttp_socks import ProxyConnector

JUDGES = ["http://httpbin.org/get", "http://ip-api.com/json"]

# The host a row must be able to carry for it to be useful. A generic judge
# (httpbin.org) says nothing about the host a consumer actually wants: measured
# 2026-11-24 the pool looked healthy while the consumer's target was
# unreachable through it. Configurable per deployment.
PROBE_TARGETS = [u.strip() for u in os.getenv(
    "NP_PROBE_TARGETS",
    "https://httpbin.org/get,https://api.ipify.org/").split(",") if u.strip()]


def _connector(protocol: str, proxy_url: str):
    if protocol == "http":
        return aiohttp.TCPConnector()
    return ProxyConnector.from_url(f"{protocol}://{proxy_url}", rdns=True)


async def check(ip: str, port: int, protocol: str,
                timeout: float = 8.0) -> dict | None:
    proxy_url = f"{ip}:{port}"
    proxy = f"http://{proxy_url}" if protocol == "http" else None
    result = {"ip": ip, "port": port, "protocol": protocol,
              "latency_ms": None, "anonymity": "unknown", "https": 0,
              "origin": None, "headers": {}}

    try:
        conn = _connector(protocol, proxy_url)
        async with aiohttp.ClientSession(connector=conn) as s:
            body = None
            for judge in JUDGES:
                attempt = time.monotonic()
                try:
                    async with s.get(judge, proxy=proxy,
                                     timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                        if r.status == 200:
                            body = await r.json(content_type=None)
                            # measure only the attempt that actually answered
                            result["latency_ms"] = int((time.monotonic() - attempt) * 1000)
                            break
                except Exception:
                    continue
            if body is None:
                raise RuntimeError("all judges failed")

            result["origin"] = body.get("origin") or body.get("query") or ""
            raw_headers = body.get("headers")
            # only httpbin echoes request headers; ip-api says nothing about
            # anonymity, so leave it unknown instead of guessing "elite".
            if isinstance(raw_headers, dict):
                hdrs = {k.lower(): v for k, v in raw_headers.items()}
                result["headers"] = hdrs
                via = hdrs.get("via", "")
                xff = hdrs.get("x-forwarded-for", "")
                if not via and not xff:
                    result["anonymity"] = "elite"
                elif xff and result["origin"].split(",")[0].strip() in xff:
                    result["anonymity"] = "transparent"
                else:
                    result["anonymity"] = "anonymous"

            # TLS through the tunnel is a separate capability from plain HTTP:
            # many public proxies answer http:// and then drop CONNECT. Probe it
            # for every protocol so the gateway can filter on it.
            #
            # The probe target is configurable (NP_PROBE_TARGETS). Probing a
            # generic judge says nothing about the host a consumer wants, so
            # the target list is what the deployment cares about.
            for target in PROBE_TARGETS:
                try:
                    async with s.get(target, proxy=proxy,
                                     timeout=aiohttp.ClientTimeout(total=6)) as r:
                        if r.status < 400:
                            result["https"] = 1
                            break
                except Exception:
                    continue
        return result
    except Exception:
        return None


async def check_batch(items: list[tuple[str, int, str]],
                      concurrency: int,
                      on_result,
                      on_progress,
                      should_stop=None,
                      timeout: float = 8.0):
    """Validate items concurrently.

    ``on_result(res, item)`` receives the check result (or ``None``).
    ``should_stop`` is polled before each check so a stop request is honoured
    without waiting for the whole batch.
    """
    sem = asyncio.Semaphore(concurrency)

    async def worker(item):
        if should_stop and should_stop():
            return
        async with sem:
            if should_stop and should_stop():
                return
            res = await check(*item, timeout=timeout)
            await on_result(res, item)
            on_progress()

    await asyncio.gather(*(worker(i) for i in items))
