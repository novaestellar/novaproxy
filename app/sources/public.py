"""Public no-auth proxy firehoses. Raw ip:port feeds + JSON APIs."""
import asyncio, re
import aiohttp

RAW = {
    "http": [
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt",
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
        "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
        "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
        "https://api.openproxylist.xyz/http.txt",
        "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt",
        "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/https.txt",
        "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.txt",
        "https://www.proxy-list.download/api/v1/get?type=http",
        "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/http.txt",
        "https://raw.githubusercontent.com/proxy4parsing/proxy-list/main/http.txt",
        "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt",
        "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=http&proxy_format=ipport&format=text",
        "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/http.txt",
        "https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt",
    ],
    "socks4": [
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks4&timeout=10000",
        "https://api.openproxylist.xyz/socks4.txt",
        "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks4.txt",
        "https://www.proxy-list.download/api/v1/get?type=socks4",
        "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/socks4.txt",
        "https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks4.txt",
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS4_RAW.txt",
    ],
    "socks5": [
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/socks5/data.txt",
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=10000",
        "https://api.openproxylist.xyz/socks5.txt",
        "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt",
        "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/socks5.txt",
        "https://www.proxy-list.download/api/v1/get?type=socks5",
        "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/socks5.txt",
        "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
        "https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks5.txt",
    ],
}

GEONODE = "https://proxylist.geonode.com/api/proxy-list"

_PLAIN = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3}):(\d{2,5})$")
_TYPED = re.compile(r"(https?|socks[45])://(\d{1,3}(?:\.\d{1,3}){3}:\d{2,5})")


async def _fetch_text(session, url, proto_hint: str) -> list[tuple[str, str]]:
    out = []
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
            if r.status != 200:
                return out
            for line in (await r.text()).splitlines():
                line = line.strip()
                m = _TYPED.search(line)
                if m:
                    proto = "http" if m.group(1) in ("http", "https") else m.group(1)
                    out.append((proto, m.group(2)))
                    continue
                if _PLAIN.match(line):
                    out.append((proto_hint, line))
    except Exception:
        pass
    return out


async def _fetch_geonode(session, protocols: set[str]) -> list[tuple[str, str]]:
    out, page = [], 1
    while page <= 6:
        try:
            async with session.get(
                GEONODE,
                params={"limit": 500, "page": page, "sort_by": "lastChecked",
                        "sort_type": "desc"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                data = await r.json()
        except Exception:
            break
        rows = data.get("data", [])
        for p in rows:
            if set(p.get("protocols", [])) & protocols:
                out.append((next(iter(set(p["protocols"]) & protocols)),
                            f"{p['ip']}:{p['port']}"))
        if len(rows) < 500:
            break
        page += 1
    return out


async def enabled_sources(protocols: set[str]) -> list[tuple[str, str]]:
    """(protocol, url) pairs the registry says are live.

    The table is the source of truth once seeded, so an operator can add a new
    gate from the UI without touching code. Falls back to the built-in list if
    the table is empty or unreachable.
    """
    from app.database import db

    marks = ",".join("?" * len(protocols))
    try:
        async with db().execute(
            f"SELECT protocol, url FROM sources WHERE enabled=1 "
            f"AND protocol IN ({marks})", tuple(protocols)
        ) as cur:
            rows = [(r["protocol"], r["url"]) for r in await cur.fetchall()]
    except Exception:
        rows = []
    if not rows:
        rows = [(p, u) for p in protocols for u in RAW.get(p, [])]
    return rows


async def probe(url: str, protocol: str) -> tuple[int, str]:
    """Fetch one feed and report how many addresses it yields."""
    connector = aiohttp.TCPConnector(limit=4)
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            entries = await _fetch_text(session, url, protocol)
        except Exception as exc:  # noqa: BLE001
            return 0, f"{type(exc).__name__}: {exc}"
    return len(entries), "ok"


async def fetch_all(protocols: set[str]) -> list[tuple[str, str]]:
    """Returns [(protocol, 'ip:port')] deduplicated."""
    sources = await enabled_sources(protocols)
    connector = aiohttp.TCPConnector(limit=40)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [_fetch_text(session, url, proto) for proto, url in sources]
        tasks.append(_fetch_geonode(session, protocols))
        results = await asyncio.gather(*tasks)

    seen, out = set(), []
    for batch in results:
        for entry in batch:
            if entry[0] not in protocols or entry in seen:
                continue
            seen.add(entry)
            out.append(entry)
    return out