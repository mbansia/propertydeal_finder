"""Headless-browser session for scraping anti-bot-protected portals.

Bayut, Dubizzle and Property Finder block plain HTTP clients (you get a 403 from
`requests`/`curl`). They serve content to real browsers, so we drive a headless
Chromium via Playwright with light stealth: a realistic UA/viewport/locale, a
Dubai timezone, `navigator.webdriver` removed, and images/fonts blocked for speed.

This is deliberately polite — one browser, sequential page loads, a delay between
requests. Respect each site's Terms and robots, and keep request rates low.
"""

from __future__ import annotations

import contextlib
import random
import time
from dataclasses import dataclass

# Playwright is an optional dependency: importing this module must not fail on
# machines that only run the scoring engine (e.g. CI). We import lazily in open().
try:  # pragma: no cover - import guard
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
window.chrome = { runtime: {} };
"""


@dataclass
class BrowseConfig:
    headless: bool = True
    min_delay: float = 2.0      # seconds between page loads (politeness)
    max_delay: float = 4.5
    nav_timeout_ms: int = 45_000
    block_assets: bool = True   # skip images/media/fonts for speed
    proxy: str | None = None    # e.g. "http://user:pass@host:port" if you use one


class BrowserSession:
    """Context manager yielding a configured Playwright page."""

    def __init__(self, cfg: BrowseConfig | None = None):
        self.cfg = cfg or BrowseConfig()
        self._pw = None
        self._browser = None
        self._ctx = None
        self._last_nav = 0.0

    def __enter__(self):
        if sync_playwright is None:
            raise RuntimeError(
                "Playwright is not installed. Run:\n"
                "  pip install playwright && playwright install --with-deps chromium"
            )
        self._pw = sync_playwright().start()
        launch_kwargs = {"headless": self.cfg.headless}
        if self.cfg.proxy:
            launch_kwargs["proxy"] = {"server": self.cfg.proxy}
        self._browser = self._pw.chromium.launch(
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            **launch_kwargs,
        )
        self._ctx = self._browser.new_context(
            user_agent=UA,
            locale="en-US",
            timezone_id="Asia/Dubai",
            viewport={"width": 1366, "height": 900},
        )
        self._ctx.add_init_script(_STEALTH_JS)
        if self.cfg.block_assets:
            self._ctx.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in {"image", "media", "font"}
                else route.continue_(),
            )
        self.page = self._ctx.new_page()
        self.page.set_default_navigation_timeout(self.cfg.nav_timeout_ms)
        return self

    def goto(self, url: str, wait_selector: str | None = None) -> bool:
        """Navigate politely; return True if the page looks loaded."""
        elapsed = time.time() - self._last_nav
        gap = random.uniform(self.cfg.min_delay, self.cfg.max_delay)
        if elapsed < gap:
            time.sleep(gap - elapsed)
        try:
            self.page.goto(url, wait_until="domcontentloaded")
            if wait_selector:
                self.page.wait_for_selector(wait_selector, timeout=self.cfg.nav_timeout_ms)
            else:
                self.page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            return False
        finally:
            self._last_nav = time.time()
        return True

    def __exit__(self, *exc):
        for closer in (self._ctx, self._browser):
            with contextlib.suppress(Exception):
                closer and closer.close()
        with contextlib.suppress(Exception):
            self._pw and self._pw.stop()
