from __future__ import annotations

import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

from murdoku_v2.site_builder import build_site


VIEWPORTS = {
    "desktop": {"width": 1440, "height": 1000},
    "mobile": {"width": 390, "height": 844},
}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def main() -> None:
    artifacts = Path("qa-artifacts")
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="maridoku-qa-") as temp:
        site = Path(temp)
        build_site(site)
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            partial(QuietHandler, directory=site),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as playwright:
                for browser_name in ("chromium", "firefox", "webkit"):
                    browser = getattr(playwright, browser_name).launch()
                    try:
                        for viewport_name, viewport in VIEWPORTS.items():
                            page = browser.new_page(viewport=viewport)
                            errors: list[str] = []
                            page.on("pageerror", lambda error: errors.append(str(error)))
                            page.on(
                                "console",
                                lambda message: errors.append(message.text)
                                if message.type == "error" else None,
                            )
                            for level in range(1, 4):
                                page.goto(f"{base_url}/levels/{level:03d}.html")
                                page.wait_for_load_state("networkidle")
                                assert page.locator("table[aria-label='Tablero']").is_visible()
                                assert page.locator(".card").count() >= 6
                                assert page.evaluate(
                                    "document.documentElement.scrollWidth <= "
                                    "document.documentElement.clientWidth"
                                )
                                page.screenshot(
                                    path=artifacts / f"{browser_name}-{viewport_name}-{level:03d}.png",
                                    full_page=True,
                                )
                            assert not errors, f"{browser_name}/{viewport_name}: {errors}"
                            page.close()
                    finally:
                        browser.close()
        finally:
            server.shutdown()


if __name__ == "__main__":
    main()
