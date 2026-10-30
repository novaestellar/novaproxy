import os
import secrets

DB_PATH = os.getenv("NP_DB", "novaproxy.db")

# Admin bootstrap (created on first run, only while the users table is empty).
# There is no baked-in default: without NP_ADMIN_PASS a random password is
# generated and printed once. A hardcoded default in a public repo is a login
# waiting to be found.
ADMIN_USERNAME = os.getenv("NP_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("NP_ADMIN_PASS") or secrets.token_urlsafe(12)
ADMIN_PASSWORD_GENERATED = os.getenv("NP_ADMIN_PASS") is None

SESSION_TTL = 7 * 24 * 3600          # 7 days

VALIDATE_TIMEOUT = 8                  # seconds per proxy check
VALIDATE_CONCURRENCY = 300
MAX_FAILED_CHECKS = 3                 # before a proxy is marked dead
MAX_CANDIDATES = 12000                # sampled per round after dedupe
AUTO_DEDUPE = True                    # drop rows sharing ip:port after each round

SITE_CHECK_TIMEOUT = 10               # seconds per proxy when testing a URL
SITE_CHECK_LIMIT = 100                # default proxies per site check
SITE_CHECK_CONCURRENCY = 50

GEO_ENRICH = True                     # ip-api.com batch enrichment
GEO_MAX = 2000                        # cap enrichment per run

# ── Signup-gated sources ─────────────────────────────────────────────
# Driven by temp-mail + headless Chrome. Point these at the free-tier
# signup form of the gated source you use. Selectors are config, not
# code. You are responsible for complying with each site's ToS.
SIGNUP_SOURCES = [
    # {
    #     "name": "getproxy",
    #     "signup_url":    "https://example-site.com/register",
    #     "login_url":     "https://example-site.com/login",
    #     "proxies_url":   "https://example-site.com/dashboard/proxies",
    #     "email_verification": True,          # click link or enter code from temp mail
    #     "verification_mode": "link",          # "link" | "code"
    #     "code_selector": "input[name=code]",  # only if mode == "code"
    #     "accounts": 3,                         # temp-mail accounts to farm
    #     "selectors": {
    #         "email":    "input[name=email]",
    #         "password": "input[name=password]",
    #         "submit":   "button[type=submit]",
    #         "proxies":  ".proxy-list",         # container holding ip:port text
    #     },
    # },
]
# Console auth. "local" trusts loopback (the normal desktop case) and still
# demands a session for anything arriving from another host; "on" always
# requires a login even on 127.0.0.1.
AUTH_MODE = os.getenv("NP_AUTH", "local")

# Auto-harvest loop. Disable with NP_AUTOPOOL=0 (tests, or when you
# want the pool to stay exactly as it is).
AUTOPOOL_ENABLED = os.getenv("NP_AUTOPOOL", "1") != "0"
