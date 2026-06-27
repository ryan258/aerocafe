"""Deterministic HTML/CSS sanity checks on the generated output."""
from pathlib import Path

from bs4 import BeautifulSoup

OUTPUT = Path(__file__).parents[1] / "output" / "index.html"


def soup():
    assert OUTPUT.exists(), "output/index.html missing — run factory.py first"
    return BeautifulSoup(OUTPUT.read_text(), "html.parser")


def test_has_title():
    assert soup().title and soup().title.text.strip()


def test_single_h1():
    assert len(soup().find_all("h1")) == 1


def test_three_sections():
    assert len(soup().find_all("section")) == 3


def test_cta_present_and_linked():
    cta = soup().select_one("a.cta")
    assert cta and cta.text.strip()
    assert cta.get("href"), "CTA has no href"


def test_no_empty_links():
    assert all(a.get("href", "").strip() for a in soup().find_all("a"))


def test_no_dangerous_href_schemes():
    for a in soup().find_all("a"):
        href = a.get("href", "").strip().lower()
        assert not href.startswith(("javascript:", "data:", "vbscript:")), href


def test_palette_locked():
    # check the CSS only, not body copy (model text may mention "gradient" etc.)
    style = soup().find("style")
    css = style.text if style else ""
    assert "#d98e3b" in css, "accent color missing from stylesheet"
    assert "linear-gradient" not in css, "gradients are off-brand"
