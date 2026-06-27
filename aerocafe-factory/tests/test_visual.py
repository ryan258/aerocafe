"""Headless Playwright rendering tests: the page must load clean and lay out."""
from pathlib import Path

import pytest

from playwright.sync_api import sync_playwright  # hard gate: spec requires Playwright

OUTPUT = Path(__file__).parents[1] / "output" / "index.html"


@pytest.fixture()
def page():
    assert OUTPUT.exists(), "output/index.html missing — run factory.py first"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        yield pg
        browser.close()


def test_no_console_errors(page):
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(OUTPUT.as_uri())
    assert not errors, f"console errors: {errors}"


def test_headline_visible(page):
    page.goto(OUTPUT.as_uri())
    assert page.locator("h1").is_visible()


def test_content_fits_mobile(page):
    page.set_viewport_size({"width": 375, "height": 800})
    page.goto(OUTPUT.as_uri())
    # no horizontal scroll on a phone-width viewport
    overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    assert not overflow, "content overflows mobile viewport"
