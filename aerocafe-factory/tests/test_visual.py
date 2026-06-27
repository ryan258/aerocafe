"""Headless Playwright rendering tests: each page loads clean and lays out."""
import pytest

from playwright.sync_api import sync_playwright  # hard gate: spec requires Playwright

from helpers import out_dir

PAGES = ["index.html", "styleguide.html"]


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.mark.parametrize("name", PAGES)
def test_no_console_errors(browser, name):
    f = out_dir() / name
    assert f.exists(), f"{name} missing — run factory.py first"
    page = browser.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f.as_uri())
    assert not errors, f"{name} console errors: {errors}"
    page.close()


@pytest.mark.parametrize("name", PAGES)
def test_headline_visible(browser, name):
    page = browser.new_page()
    page.goto((out_dir() / name).as_uri())
    assert page.locator("h1").first.is_visible()
    page.close()


@pytest.mark.parametrize("name", PAGES)
def test_no_mobile_overflow(browser, name):
    page = browser.new_page()
    page.set_viewport_size({"width": 375, "height": 800})
    page.goto((out_dir() / name).as_uri())
    overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    assert not overflow, f"{name} overflows mobile viewport"
    page.close()
