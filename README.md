<p align="center">
  <strong>Self-hosted proxy harvesting console</strong><br>
  Harvest Â· validate Â· dedupe Â· geo-enrich Â· test any URL through the pool
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-asyncio-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black" alt="React">
  <img src="https://img.shields.io/badge/SQLite-WAL-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/port-12000-8b5cf6?style=flat-square" alt="Port">
</p>

---

## What this is

NovaProxy is a local control panel for building and maintaining a working proxy
pool, and for serving it as one endpoint. You set a target count; it pulls public
proxy feeds, validates every candidate against live judges, keeps the survivors,
removes duplicates, enriches them with geo data â€” then a built-in gateway exposes
the pool as local SOCKS5 and HTTP, with rotation, failover, byte accounting and
per-proxy quotas.

It replaces the job of hand-editing a `proxies.txt`, guessing which entries still
work, and never knowing why a request failed.

![NovaProxy overview](docs/novaproxy-demo-poster.png)

| | |
|---|---|
| **Backend** | Python 3.12+, FastAPI, asyncio, aiohttp, aiosqlite |
| **Frontend** | React 19, TypeScript, Vite 6, Tailwind CSS v4 |
| **Storage** | SQLite (WAL, 10 s busy timeout) |
| **Realtime** | Server-sent events, one status frame per second |
| **Auth** | PBKDF2 (200k iterations), HttpOnly `np_session` cookie |

## NovaProxy vs. novastar

They solve different layers. Neither is a replacement for the other.

| | NovaProxy | novastar |
|---|---|---|
| **Supply** | Public feeds, no accounts | ipstar.io farm / paid account |
| **IP class** | Datacenter | Residential |
| **Quota** | Optional per-proxy cap, byte-accurate | 2 GB per farm account, metered per account |
| **Validation** | 2 judges, anonymity + HTTPS classified, 3-strike death | Repo-level, no per-proxy health history |
| **Dedupe** | SQL window function, 5 trigger points | Not applicable |
| **Geo enrichment** | ip-api batch, 100 per call | Not applicable |
| **URL test** | Up to 200 alive proxies per check | Not available |
| **Gateway** | SOCKS5 `:11500` + HTTP `:12500`, rotation + failover | SOCKS5 `:1080` + HTTP `:8118`, rotation + failover |
| **Analytics** | Traffic samples, quota buckets, protocol split | Pool table with per-account bytes |
| **UI** | React SPA, live SSE, multi-user | Single admin page |
| **Failure mode** | Yield drops when public lists rot | Whole pool dies when entitlement is revoked |

Rule of thumb:

- **Bulk, non-identity traffic** (scraping, rate-limit spreading, geo checks,
  load distribution) â†’ NovaProxy. Free, unlimited, disposable.
- **Identity-sensitive traffic** (signup, anti-bot, per-account isolation) â†’
  residential. NovaProxy cannot help there, by design.

If the residential lane is already covered, NovaProxy is strictly additional
capacity: it never expires, costs nothing, and can be rebuilt from zero in one
click.

## Demo

A 52-second walkthrough (login â†’ live run â†’ pool â†’ site check â†’ logs â†’ settings):

- [`docs/novaproxy-demo.mp4`](docs/novaproxy-demo.mp4) â€” H.264, 1440Ã—900
- [`docs/novaproxy-demo-poster.png`](docs/novaproxy-demo-poster.png) â€” poster frame

Regenerate it against a local server:

```bash
python run.py
.venv/Scripts/python.exe scripts/record_demo.py    # Windows
# source .venv/bin/activate && python scripts/record_demo.py   # macOS / Linux
```

The recorder needs Playwright Chromium (`playwright install chromium`); the
optional MP4 copy needs `pip install imageio-ffmpeg`.

## Requirements

- Python **3.12+**
- Node.js **20+** â€” only to rebuild the frontend (a prebuilt `web/dist` is included)
- Playwright Chromium â€” only for signup-gated sources and the demo recorder

## Install and run

```bash
cd D:\Labs\novaproxy
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Open **http://127.0.0.1:12000**.

The React build in `web/dist` is served by FastAPI, so no second process is
needed. If `web/dist` is missing, the API returns a 503 with build instructions.

### Frontend development

```bash
# terminal 1
python run.py

# terminal 2
cd web
npm install
npm run dev      # http://127.0.0.1:5173, /api proxied to :12000
```

| Command | Purpose |
|---|---|
| `npm run dev` | Vite dev server with hot reload |
| `npm run build` | Production build into `web/dist` |
| `npm run typecheck` | `tsc --noEmit` |

### Docker

```bash
docker build -t novaproxy .
docker run -d --name novaproxy -p 12000:12000 \
  -e NP_ADMIN_USER=admin -e NP_ADMIN_PASS=change-me \
  -e NP_DB=/app/data/novaproxy.db \
  -v "$(pwd)/data:/app/data" novaproxy
```

The image builds the frontend in a Node stage, then serves it from Python.

## First run

1. Sign in with the bootstrap account, or create a new one from the login page.
2. Start a collection, pick a target and protocols, and watch the quota fill.
3. Open **Pool** to filter, copy, export or recheck proxies.
4. Open **Site check** to verify the pool against your own target URL.

Bootstrap credentials come from the environment:

```bash
NP_ADMIN_USER=admin
NP_ADMIN_PASS=change-me
```

They are used **only when the users table is empty**. Set a strong password
before the first start; changing the variables later does not reset an existing
admin.

Registration is open by default. To make the instance invite-only, remove
`/register` and `/api/register` from `PUBLIC_PREFIXES` in `app/main.py`.

## How it works

```
Browser â”€â”€ React SPA â”€â”€ /api â”€â”€ FastAPI â”€â”€ SQLite
                              â”‚
                              â”œâ”€â”€ sources/public.py   12+ public feeds + GeoNode
                              â”œâ”€â”€ sources/custom.py   temp-mail + Playwright
                              â”œâ”€â”€ validator.py        concurrent judges
                              â””â”€â”€ sitecheck.py        arbitrary URL tests
```

### Collection loop

1. Fetch every enabled public feed and drop entries checked in the last 30 minutes.
2. Sample down to `MAX_CANDIDATES` (12,000) to keep rounds bounded.
3. Validate at `VALIDATE_CONCURRENCY` (300) with `VALIDATE_TIMEOUT` (8 s) per judge.
4. Store successes, count a strike for known failures; three strikes mark a proxy dead.
5. Deduplicate, enrich geo data, then repeat if the target is still unmet.

Rounds after the first wait 10 minutes, because free lists rotate hourly.
Final states: `done`, `stopped`, `exhausted`.

### Judges

Each candidate is tried against two independent judges, in order:

1. `http://httpbin.org/get` â€” echoes request headers, used for anonymity class.
2. `http://ip-api.com/json` â€” independent reachability + egress IP.

Latency is measured only on the attempt that actually answered. Anonymity is
classified as `elite` (no `Via`, no `X-Forwarded-For`), `anonymous` (headers
present, origin not leaked) or `transparent` (origin appears in `X-Forwarded-For`).
HTTPS capability is probed separately for HTTP proxies.

### Deduplication

Rows are partitioned by `ip:port`. The survivor is chosen by:

1. alive before dead
2. HTTPS-capable before plain
3. lowest latency
4. most recent check

Duplicates are removed at startup, when a run starts, after every round, after a
recheck, and from **Settings â†’ Remove duplicates**. The number removed is written
to the engine log.

### Site check

- Runs only against proxies currently marked alive.
- The request is made **through each proxy** to the URL you enter.
- Passed means the response status is below 400.
- The hard ceiling per proxy is `timeout + 2 s`, so a stalling proxy cannot hold
  the whole batch.
- Results are upserted into `site_checks` and are available from
  `GET /api/site-checks`.

### Geo enrichment

Alive proxies without a country are sent to the ip-api batch endpoint in groups
of 100, capped at `GEO_MAX` per run, with a 4-second gap between groups.

## Gateway

The gateway turns the pool into one local endpoint, so applications do not need a
proxy list â€” they need one address.

| Listener | Default | Protocol |
|---|---|---|
| SOCKS5 | `127.0.0.1:11500` | SOCKS5 CONNECT, no auth on the client side |
| HTTP | `127.0.0.1:12500` | `CONNECT` tunnels + absolute-URI forwarding |

```bash
# HTTP
curl -x http://127.0.0.1:12500 https://api.ipify.org

# SOCKS5
curl --socks5-hostname 127.0.0.1:11500 https://api.ipify.org
```

Behaviour, mirroring what novastar's residential gateway got right:

- **Rotation** â€” `round_robin`, `least_used` or `fastest`, selected in Settings.
- **Failover** â€” one failed upstream does not fail the request; the next eligible
  proxy is tried. Failures accrue; three marks the row dead.
- **Quota** â€” every relayed byte is counted per proxy (`bytes_in`, `bytes_out`),
  with an optional allowance in MB. A proxy at its cap is skipped before the
  connection opens, not after the upstream rejects it.
- **Exclusion** â€” drop a proxy from rotation without deleting it; restore it in
  one click.
- **Live counters** â€” connections, active relays, failures, bytes both ways.

Ports and quota are persisted in the database (table `kv`), so a restart keeps
them. Changing ports requires stopping and starting the gateway.

## Analytics

The Analytics page reads aggregates over the same database: pool composition,
relayed bytes per protocol, quota distribution (`fresh` / `half` / `exhausted` /
`unlimited`), the busiest proxies, site-check pass rate, and a traffic sparkline
built from 30-second samples written while the gateway is running.

## Configuration

Environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `NP_DB` | `novaproxy.db` | SQLite database path |
| `NP_ADMIN_USER` | `admin` | Bootstrap username |
| `NP_ADMIN_PASS` | `admin123` | Bootstrap password, first run only |

`app/config.py`:

| Key | Default | Meaning |
|---|---|---|
| `VALIDATE_TIMEOUT` | `8` | Seconds per judge attempt |
| `VALIDATE_CONCURRENCY` | `300` | Simultaneous validations |
| `MAX_FAILED_CHECKS` | `3` | Consecutive failures before dead |
| `MAX_CANDIDATES` | `12000` | Candidates sampled per round |
| `AUTO_DEDUPE` | `True` | Remove duplicates automatically |
| `SITE_CHECK_TIMEOUT` | `10` | Default per-proxy timeout in seconds |
| `SITE_CHECK_LIMIT` | `100` | Default proxies per site check |
| `SITE_CHECK_CONCURRENCY` | `50` | Parallel site checks |
| `GEO_ENRICH` | `True` | Enable ip-api enrichment |
| `GEO_MAX` | `2000` | Proxies enriched per run |
| `SIGNUP_SOURCES` | `[]` | Optional signup-gated source definitions |
| `GATEWAY` | see below | Gateway runtime settings, persisted in `kv` |

Gateway defaults (editable from the UI, stored in the database):

| Key | Default | Meaning |
|---|---|---|
| `socks_port` | `11500` | SOCKS5 listener |
| `http_port` | `12500` | HTTP listener |
| `strategy` | `round_robin` | `round_robin` Â· `least_used` Â· `fastest` |
| `quota_mb` | `0` | Per-proxy allowance; `0` = unlimited |
| `timeout` | `12` | Upstream connect timeout (seconds) |
| `max_fails` | `3` | Failures before a proxy is marked dead |

## Signup-gated sources

Sources behind a free registration wall can be driven by the optional temp-mail +
headless Chromium flow. Define them in `SIGNUP_SOURCES`:

```python
SIGNUP_SOURCES = [{
    "name": "example",
    "signup_url": "https://example.com/register",
    "login_url": "https://example.com/login",
    "proxies_url": "https://example.com/dashboard/proxies",
    "email_verification": True,
    "verification_mode": "link",          # or "code"
    "code_selector": "input[name=code]",  # only for "code"
    "accounts": 3,
    "selectors": {
        "email": "input[name=email]",
        "password": "input[name=password]",
        "submit": "button[type=submit]",
        "proxies": ".proxy-list",
    },
}]
```

Install the browser once:

```bash
playwright install chromium
```

Keep **Signup-gated sources** enabled in the collection dialog to use them.
Sites protected by CAPTCHA are out of scope for this flow.

## API

All routes except login/register require the `np_session` cookie.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/login` | Form login, sets the session cookie |
| `POST` | `/api/register` | Create an account and sign in |
| `POST` | `/api/logout` | Destroy the session |
| `GET` | `/api/me` | Current user |
| `POST` | `/api/collect` | `{target, protocols[], rounds, use_custom}` |
| `POST` | `/api/stop` | Cancel the active run or recheck |
| `GET` | `/api/status` | Snapshot including the last 150 log lines |
| `GET` | `/api/stream` | Server-sent events, one status frame per second |
| `GET` | `/api/stats` | Pool totals, protocol, anonymity, country and latency aggregates |
| `GET` | `/api/settings` | Effective runtime configuration |
| `GET` | `/api/proxies` | Filters: `protocol, country, anonymity, q, sort, offset, limit` |
| `GET` | `/api/proxies/export` | `?fmt=txt\|json`, optional `?protocol=` |
| `POST` | `/api/proxies/recheck` | Revalidate the alive pool |
| `POST` | `/api/proxies/purge-dead` | Delete dead rows |
| `POST` | `/api/proxies/dedupe` | Remove duplicate endpoints |
| `POST` | `/api/proxies/test` | Test alive proxies against a URL |
| `GET` | `/api/site-checks` | Stored site-check results |
| `GET` | `/api/gateway` | Gateway state, counters, warnings |
| `POST` | `/api/gateway/start` | Start SOCKS5 + HTTP listeners |
| `POST` | `/api/gateway/stop` | Stop listeners |
| `POST` | `/api/gateway/settings` | Patch ports, strategy, quota, timeout, max fails |
| `GET` | `/api/analytics` | Pool, traffic, quota and site-check aggregates |
| `POST` | `/api/proxies/quota` | `{mb, scope:"all"}` or `{mb, items:[...]}` |
| `POST` | `/api/proxies/exclude` | `{excluded, scope:"all"}` or `{excluded, items:[...]}` |

Example:

```bash
curl -c cookies.txt \
  -d 'username=admin&password=change-me' \
  http://127.0.0.1:12000/api/login

curl -b cookies.txt \
  'http://127.0.0.1:12000/api/proxies/export?protocol=socks5' \
  -o socks5.txt
```

## Data

- `novaproxy.db` â€” users, sessions, proxy pool, site-check history
- SQLite runs in WAL mode with a 10-second busy timeout
- Delete the database to start over; the admin account is recreated from the
  environment on the next start

## Project layout

```
novaproxy/
â”œâ”€â”€ run.py
â”œâ”€â”€ requirements.txt
â”œâ”€â”€ Dockerfile
â”œâ”€â”€ .env.example
â”œâ”€â”€ app/
â”‚   â”œâ”€â”€ main.py          API, auth, SSE, SPA hosting
â”‚   â”œâ”€â”€ engine.py        collection loop, dedupe, recheck
â”‚   â”œâ”€â”€ gateway.py       SOCKS5 + HTTP gateway, rotation, quota metering
â”‚   â”œâ”€â”€ validator.py     concurrent proxy judges
â”‚   â”œâ”€â”€ sitecheck.py     URL tests through proxies
â”‚   â”œâ”€â”€ sources/
â”‚   â”‚   â”œâ”€â”€ public.py
â”‚   â”‚   â””â”€â”€ custom.py
â”‚   â”œâ”€â”€ security.py
â”‚   â”œâ”€â”€ database.py
â”‚   â”œâ”€â”€ tempmail.py
â”‚   â””â”€â”€ config.py
â”œâ”€â”€ web/
â”‚   â”œâ”€â”€ src/             React pages, components, API client
â”‚   â”œâ”€â”€ dist/            production build served by FastAPI
â”‚   â””â”€â”€ package.json
â”œâ”€â”€ scripts/
â”‚   â””â”€â”€ record_demo.py   demo recorder
â””â”€â”€ docs/
    â”œâ”€â”€ novaproxy-demo.mp4
    â””â”€â”€ novaproxy-demo-poster.png
```

## Packaging

When creating a zip for distribution, exclude generated or local-only files:

```
.venv/
web/node_modules/
**/__pycache__/
*.db
*.db-wal
*.db-shm
docs/raw/
```

Include `web/dist/` if you want the app to run without a Node build step.
Exclude the database to ship a clean instance that bootstraps the admin from
`NP_ADMIN_USER` / `NP_ADMIN_PASS` on first start.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Frontend not built` (503) | `cd web && npm install && npm run build` |
| 0 alive after a full round | Raise rounds, enable SOCKS, or run again later |
| SOCKS validation errors | `pip install aiohttp-socks` |
| Site check always fails | Free proxies often reject HTTPS `CONNECT`; try an `http://` target or another protocol |
| Signup module does nothing | Configure `SIGNUP_SOURCES` and run `playwright install chromium` |
| SSE badge reconnecting | A reverse proxy is buffering; the endpoint sends `X-Accel-Buffering: no` for nginx |

## Legal

NovaProxy aggregates proxies published openly and for free by their maintainers.
Respect each source's terms of service. Free proxies are operated by strangers â€”
never send credentials, personal data or anything sensitive through them. Use the
tool for legitimate testing, scraping and research.
