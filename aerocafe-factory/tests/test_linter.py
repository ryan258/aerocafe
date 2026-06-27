"""Deterministic sanity checks on the generated brand deliverables."""
import json
import re

from bs4 import BeautifulSoup

from helpers import out_dir


def _soup(name):
    p = out_dir() / name
    assert p.exists(), f"{name} missing — run factory.py first"
    return BeautifulSoup(p.read_text(), "html.parser")


def brand():
    p = out_dir() / "brand.json"
    assert p.exists(), "brand.json missing — run factory.py first"
    return json.loads(p.read_text())


# --- brand spec -----------------------------------------------------------
def test_spec_has_required_keys():
    b = brand()
    for k in ("name", "tagline", "palette", "typography", "voice", "logo",
              "values", "microsite", "applications"):
        assert b.get(k), f"brand.json missing/empty: {k}"


def test_palette_hexes_valid():
    for c in brand()["palette"]:
        assert re.fullmatch(r"#[0-9a-fA-F]{6}", c["hex"]), c
        assert c.get("role") and c.get("usage")


def test_one_accent_only():
    roles = [c["role"] for c in brand()["palette"]]
    assert roles.count("accent") == 1, f"brand wants exactly one accent: {roles}"


# --- logo -----------------------------------------------------------------
def test_logo_svg_clean():
    svg = (out_dir() / "logo.svg").read_text()
    assert svg.lstrip().lower().startswith("<svg"), "logo.svg is not an SVG"
    low = svg.lower()
    assert "<script" not in low and "javascript:" not in low
    assert not re.search(r"\son\w+\s*=", svg), "inline event handler in SVG"


# --- style guide ----------------------------------------------------------
def test_styleguide_has_all_sections():
    text = (out_dir() / "styleguide.html").read_text().lower()
    for heading in ("logo", "color", "typography", "voice", "applications"):
        assert heading in text, f"style guide missing section: {heading}"


def test_styleguide_one_swatch_per_color():
    sg = _soup("styleguide.html")
    assert len(sg.select(".swatch")) == len(brand()["palette"])


def test_styleguide_no_gradients_in_css():
    css = _soup("styleguide.html").find("style").text
    assert "linear-gradient" not in css and "radial-gradient" not in css


# --- microsite ------------------------------------------------------------
def test_microsite_single_h1():
    assert len(_soup("index.html").find_all("h1")) == 1


def test_microsite_three_sections():
    assert len(_soup("index.html").find_all("section")) == 3


def test_microsite_cta_linked():
    cta = _soup("index.html").select_one("a.cta")
    assert cta and cta.text.strip() and cta.get("href")


def test_no_dangerous_href_schemes():
    for page in ("index.html", "styleguide.html"):
        for a in _soup(page).find_all("a"):
            href = a.get("href", "").strip().lower()
            assert not href.startswith(("javascript:", "data:", "vbscript:")), (page, href)
