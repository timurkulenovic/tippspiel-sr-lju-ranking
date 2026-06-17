from __future__ import annotations

import argparse
import asyncio
import json
import os
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from datetime import timedelta
from pathlib import Path

from crawlee.crawlers import PlaywrightCrawler
from crawlee.crawlers._playwright._playwright_crawling_context import PlaywrightCrawlingContext

from tippspiel_crawler.extractors import parse_ranking_row


@dataclass
class CrawlConfig:
    url: str
    out: Path
    timeout_ms: int
    headless: bool
    debug_browser: bool
    storage_state: Path | None
    credentials_file: Path


@dataclass
class AuthCredentials:
    email: str
    password: str


def resolve_credentials_path(path_value: str) -> Path:
    candidate = Path(path_value).expanduser()
    if candidate.is_absolute() or candidate.exists():
        return candidate

    # Support running `tippspiel-crawl` from outside the repository root.
    repo_relative = Path(__file__).resolve().parents[2] / candidate
    if repo_relative.exists():
        return repo_relative

    return candidate


def parse_args() -> CrawlConfig:
    parser = argparse.ArgumentParser(description="Crawl LAOLA1 Tippspiel group ranking")
    parser.add_argument("--url", default="https://tippspiel.laola1.at/gruppe/80/ranking")
    parser.add_argument("--out", default="ranking.json")
    parser.add_argument("--timeout", type=int, default=45000)
    parser.add_argument("--headed", action="store_true", help="Run browser with UI")
    parser.add_argument(
        "--debug-browser",
        action="store_true",
        help="Open a visible browser with slow motion and extra diagnostics",
    )
    parser.add_argument(
        "--storage-state",
        default=None,
        help="Path to Playwright storage state JSON for authenticated crawling",
    )
    parser.add_argument(
        "--credentials-file",
        default="config.toml",
        help="Path to TOML config file with auth.email/auth.password",
    )
    args = parser.parse_args()
    return CrawlConfig(
        url=args.url,
        out=Path(args.out),
        timeout_ms=args.timeout,
        headless=not (args.headed or args.debug_browser),
        debug_browser=args.debug_browser,
        storage_state=Path(args.storage_state) if args.storage_state else None,
        credentials_file=resolve_credentials_path(args.credentials_file),
    )


def load_credentials(config_file: Path) -> AuthCredentials:
    if not config_file.exists():
        raise RuntimeError(
            f"Credentials file not found: {config_file}. Create it from config.toml.example and fill auth.email/auth.password, "
            "or pass --credentials-file /absolute/path/to/config.toml."
        )

    data = tomllib.loads(config_file.read_text(encoding="utf-8"))
    auth = data.get("auth", {}) if isinstance(data, dict) else {}
    email = str(auth.get("email", "")).strip()
    password = str(auth.get("password", "")).strip()

    if not email or not password:
        raise RuntimeError(
            f"Credentials missing in {config_file}. Set auth.email and auth.password."
        )

    return AuthCredentials(email=email, password=password)


async def dismiss_cookie_banner(page) -> None:
    labels = [
        "Alle akzeptieren",
        "Akzeptieren",
        "Accept all",
        "Einverstanden",
    ]
    for label in labels:
        button = page.get_by_role("button", name=label)
        if await button.count() > 0:
            try:
                await button.first.click(timeout=1500)
                await page.wait_for_timeout(500)
                return
            except Exception:
                continue


async def dismiss_whats_new_popup(page, timeout_ms: int) -> None:
    popup_button = page.locator(".global-btn.group-predictions-whats-new__cta")
    if await popup_button.count() == 0:
        return

    try:
        await popup_button.first.click(timeout=min(timeout_ms, 3000), force=True)
        await page.locator(".popup-bg").first.wait_for(state="hidden", timeout=2000)
        await page.wait_for_timeout(300)
    except Exception:
        # Ignore intermittent UI timing issues and continue trying to read the table.
        pass


async def extract_rows(page, timeout_ms: int) -> list[list[str]]:
    await dismiss_cookie_banner(page)
    await dismiss_whats_new_popup(page, timeout_ms)
    try:
        await page.wait_for_selector("table tbody tr.row", timeout=timeout_ms)
    except Exception as exc:
        h1 = await page.locator("h1").first.text_content()
        title = await page.title()
        raise RuntimeError(
            f"Ranking table not found. title='{title}', h1='{(h1 or '').strip()}'"
        ) from exc

    # Expand the ranking table beyond the initial 50 visible rows.
    max_clicks = 100
    previous_count = await page.locator("table tbody tr.row").count()
    for _ in range(max_clicks):
        await dismiss_whats_new_popup(page, timeout_ms)
        load_more = page.locator("div.btn-box button.global-sec-btn")
        if await load_more.count() == 0:
            break

        button = load_more.first
        if await button.is_disabled():
            break

        try:
            await button.click(timeout=timeout_ms)
        except Exception as exc:
            # A popup can appear after initial table load and block pointer events.
            await dismiss_whats_new_popup(page, timeout_ms)
            try:
                await button.click(timeout=min(timeout_ms, 5000))
            except Exception:
                raise exc
        await page.wait_for_timeout(300)

        current_count = await page.locator("table tbody tr.row").count()
        if current_count <= previous_count:
            break
        previous_count = current_count

    return await page.eval_on_selector_all(
        "table tbody tr.row",
        """
        (rows) => rows
          .map((tr) => Array.from(tr.querySelectorAll('td')).map((td) => (td.textContent || '').trim()))
          .filter((cells) => cells.length >= 6 && (cells[1] || '').trim().length > 0)
        """,
    )


async def login_with_credentials(page, creds: AuthCredentials, timeout_ms: int) -> None:
    await page.goto("https://tippspiel.laola1.at/profile", wait_until="domcontentloaded", timeout=timeout_ms)
    await page.wait_for_timeout(1500)
    await dismiss_cookie_banner(page)

    login_frame = next((f for f in page.frames if "login.laola1.at/auth/login" in f.url), None)
    if not login_frame:
        # No login frame typically means the session is already authenticated.
        return

    await login_frame.locator("input[type='email']").fill(creds.email, timeout=timeout_ms)
    await login_frame.locator("input[type='password']").fill(creds.password, timeout=timeout_ms)

    submit = login_frame.locator("button.submit-button")
    if await submit.count() > 0:
        await submit.first.click(timeout=timeout_ms)
    else:
        await login_frame.locator("button[type='submit']").first.click(timeout=timeout_ms)

    # Give the app a moment to update auth state in parent page.
    await page.wait_for_timeout(2500)

    # If login form is still present, credentials were likely rejected.
    still_on_login = any("login.laola1.at/auth/login" in f.url for f in page.frames)
    if still_on_login:
        raise RuntimeError("Login failed. Check email/password in config file.")


async def run_crawl(config: CrawlConfig) -> dict:
    result: dict[str, object] = {}
    credentials = None if config.storage_state else load_credentials(config.credentials_file)
    context_options = {
        "user_agent": "tippspiel-crawler/1.0 (+respectful; contact-local)",
    }
    if config.storage_state:
        context_options["storage_state"] = str(config.storage_state)

    launch_options: dict[str, object] = {}
    if config.debug_browser:
        # Slow motion makes UI interactions easier to visually inspect.
        launch_options["slow_mo"] = 250

    # Disable sandbox in CI environments to avoid "Chromium sandboxing failed" errors.
    if os.getenv("CI") or os.getenv("GITHUB_ACTIONS"):
        launch_options["args"] = ["--no-sandbox", "--disable-setuid-sandbox"]

    crawler = PlaywrightCrawler(
        headless=config.headless,
        max_requests_per_crawl=1,
        max_request_retries=0,
        navigation_timeout=timedelta(milliseconds=config.timeout_ms),
        request_handler_timeout=timedelta(milliseconds=config.timeout_ms + 15000),
        browser_launch_options=launch_options,
        browser_new_context_options=context_options,
    )

    @crawler.router.default_handler
    async def handle_request(context: PlaywrightCrawlingContext) -> None:
        try:
            if credentials is not None:
                await login_with_credentials(context.page, credentials, config.timeout_ms)
                await context.page.goto(config.url, wait_until="domcontentloaded", timeout=config.timeout_ms)

            rows = await extract_rows(context.page, config.timeout_ms)
            parsed = [parse_ranking_row(cells) for cells in rows]
            result.update(
                {
                    "sourceUrl": context.request.url,
                    "crawledAt": datetime.now(timezone.utc).isoformat(),
                    "rowCount": len(parsed),
                    "ranking": parsed,
                    "rawRows": rows,
                }
            )
        except Exception:
            if config.debug_browser:
                await context.page.screenshot(path="debug-last-page.png", full_page=True)
            raise

    await crawler.run([config.url])

    if not result:
        raise RuntimeError("No data captured; ranking table was not found")

    return result


def write_output(payload: dict, output_path: Path) -> None:
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


async def async_main() -> int:
    config = parse_args()
    try:
        payload = await run_crawl(config)
        write_output(payload, config.out)
        print(f"Saved {payload['rowCount']} rows to {config.out}")
        return 0
    except Exception as exc:
        print(f"Crawl failed: {exc}")
        return 1


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()

