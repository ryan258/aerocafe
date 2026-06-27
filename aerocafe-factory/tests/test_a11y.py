"""WCAG 2.2 AA color-contrast checks on the colors that actually ship.

Templates resolve the palette to three CSS vars via factory._site_colors and use them as:
  primary text on bg (body, headings) and bg text on primary (style-guide cover) — 1.4.3
  bg text on accent (CTA button) and accent text on bg (links/headings) — 1.4.3
Both pairings must clear 4.5:1 for normal text. Structural 2.2 criteria (lang, semantic
headings, real <a> CTA, viewport, 24px+ targets) are handled by the static templates.
"""
import json

from factory import _site_colors, contrast_ratio  # importable via conftest.py
from helpers import out_dir


def _brand():
    return json.loads((out_dir() / "brand.json").read_text())


def test_contrast_ratio_math():
    assert round(contrast_ratio("#000000", "#ffffff"), 1) == 21.0
    assert contrast_ratio("#123456", "#123456") == 1.0


def test_body_text_contrast_aa():
    c = _site_colors(_brand()["palette"])
    r = contrast_ratio(c["primary"], c["bg"])
    assert r >= 4.5, f"primary text {c['primary']} on bg {c['bg']} is {r:.2f}:1 (< 4.5 AA)"


def test_accent_contrast_aa():
    # accent is used both as button-label-on-accent and as accent-on-bg link/heading text.
    c = _site_colors(_brand()["palette"])
    r = contrast_ratio(c["accent"], c["bg"])
    assert r >= 4.5, f"accent {c['accent']} on bg {c['bg']} is {r:.2f}:1 (< 4.5 AA)"
