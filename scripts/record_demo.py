"""Record a product demo video of the NovaProxy console.

Requires the server on http://127.0.0.1:12000, Playwright Chromium
(`playwright install chromium`) and optionally imageio-ffmpeg for the MP4 copy.
Usage: .venv/Scripts/python.exe scripts/record_demo.py
"""
import asyncio
import shutil
from pathlib import Path

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:12000"
ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
RAW = DOCS / "raw"
FINAL = DOCS / "novaproxy-demo.webm"


async def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for old in RAW.glob("*.webm"):
        old.unlink()

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1,
            record_video_dir=str(RAW),
            record_video_size={"width": 1440, "height": 900},
        )
        page = await context.new_page()
        page.set_default_timeout(20_000)

        # ── login ────────────────────────────────────────────────────
        await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        await page.wait_for_selector("#username")
        await page.locator("#username").click()
        await page.locator("#username").press_sequentially("admin", delay=90)
        await page.wait_for_timeout(250)
        await page.locator("#password").click()
        await page.locator("#password").press_sequentially("admin123", delay=70)
        await page.wait_for_timeout(400)
        await page.get_by_role("button", name="Continue").click()
        await page.wait_for_selector("text=Collection quota")

        # ── overview + live run ──────────────────────────────────────
        await page.wait_for_timeout(1600)
        await page.get_by_role("button", name="New collection").click()
        dialog = page.locator("[role=dialog]")
        await dialog.wait_for()
        await dialog.locator("#target").fill("5000")
        await dialog.locator("select").select_option("1")
        await dialog.get_by_role("button", name="SOCKS5").click()
        await page.wait_for_timeout(500)
        await dialog.get_by_role("button", name="Start collecting").click()
        await page.get_by_text("Running", exact=True).wait_for()
        await page.wait_for_timeout(5000)
        await page.evaluate("window.scrollTo({top: 380, behavior: 'smooth'})")
        await page.wait_for_timeout(1800)
        await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        await page.wait_for_timeout(700)

        # ── pool ─────────────────────────────────────────────────────
        await page.click('a[href="/pool"]')
        await page.wait_for_selector('h1:has-text("Pool")')
        await page.wait_for_timeout(1400)
        await page.locator("select").first.select_option("http")
        await page.wait_for_timeout(1400)
        await page.evaluate("window.scrollTo({top: 300, behavior: 'smooth'})")
        await page.wait_for_timeout(1300)
        await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        await page.wait_for_timeout(600)

        # ── site check ───────────────────────────────────────────────
        await page.click('a[href="/check"]')
        await page.wait_for_selector('h1:has-text("Site check")')
        await page.wait_for_timeout(1000)
        await page.fill("input[placeholder='https://example.com']", "https://www.google.com")
        await page.locator("select").first.select_option("http")
        await page.locator("select").nth(1).select_option("25")
        await page.wait_for_timeout(900)
        await page.get_by_role("button", name="Run check").click()
        await page.wait_for_function(
            "document.querySelectorAll('table tbody tr').length > 5", timeout=35_000)
        await page.wait_for_timeout(1600)
        await page.evaluate("window.scrollTo({top: 300, behavior: 'smooth'})")
        await page.wait_for_timeout(2200)
        await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        await page.wait_for_timeout(700)

        # ── logs ─────────────────────────────────────────────────────
        await page.click('a[href="/logs"]')
        await page.wait_for_selector('h1:has-text("Logs")')
        await page.wait_for_timeout(2000)

        # ── settings ─────────────────────────────────────────────────
        await page.click('a[href="/settings"]')
        await page.wait_for_selector('h1:has-text("Settings")')
        await page.wait_for_timeout(1400)
        await page.evaluate("window.scrollTo({top: 420, behavior: 'smooth'})")
        await page.wait_for_timeout(2000)
        await page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        await page.wait_for_timeout(600)

        # ── back to overview, then stop the run ─────────────────────
        await page.click('a[href="/"]')
        await page.wait_for_selector("text=Collection quota")
        await page.wait_for_timeout(1500)
        await page.get_by_role("button", name="Stop").click()
        await page.get_by_text("stopped by user").first.wait_for()
        await page.wait_for_timeout(2200)

        await context.close()
        await browser.close()

    videos = sorted(RAW.glob("*.webm"), key=lambda v: v.stat().st_mtime)
    if not videos:
        raise SystemExit("no recording produced")
    shutil.move(str(videos[-1]), FINAL)
    shutil.rmtree(RAW, ignore_errors=True)
    print(f"wrote {FINAL} ({FINAL.stat().st_size / 1024 / 1024:.1f} MB)")

    # H.264 copy for players that do not take VP9 (needs imageio-ffmpeg).
    mp4 = DOCS / "novaproxy-demo.mp4"
    poster = DOCS / "novaproxy-demo-poster.png"
    try:
        import subprocess

        import imageio_ffmpeg

        ff = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [ff, "-y", "-hide_banner", "-loglevel", "error", "-i", str(FINAL),
             "-c:v", "libx264", "-preset", "medium", "-crf", "22",
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)],
            check=True,
        )
        subprocess.run(
            [ff, "-y", "-hide_banner", "-loglevel", "error",
             "-ss", "12", "-i", str(mp4), "-frames:v", "1", str(poster)],
            check=True,
        )
        print(f"wrote {mp4} ({mp4.stat().st_size / 1024 / 1024:.1f} MB)")
        print(f"wrote {poster}")
    except Exception as exc:  # pragma: no cover - tooling only
        print(f"MP4 transcoding skipped: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
