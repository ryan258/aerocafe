"""Unit checks for the security-sensitive model-output sanitizers in factory.py."""
import pytest

from factory import _json_from, _safe_svg  # importable via conftest.py

CLEAN_SVG = '<svg viewBox="0 0 10 10"><path d="M0 0h10v10H0z" fill="#fff"/></svg>'
GRADIENT_SVG = ('<svg><defs><linearGradient id="g"><stop offset="0"/></linearGradient>'
                '</defs><rect fill="url(#g)"/></svg>')


def test_safe_svg_passes_clean_logo():
    assert _safe_svg(CLEAN_SVG) == CLEAN_SVG


def test_safe_svg_allows_internal_url_ref():
    assert _safe_svg(GRADIENT_SVG)  # url(#g) is an internal fragment, not external


def test_safe_svg_allows_text_on_internal_path():
    svg = ('<svg><defs><path id="p" d="M0 0h10"/></defs>'
           '<text><textPath href="#p">hi</textPath></text></svg>')
    assert _safe_svg(svg)


def test_safe_svg_allows_filter_and_inline_style():
    svg = ('<svg><defs><filter id="s"><feGaussianBlur stdDeviation="2"/></filter>'
           '<style>.a{fill:#000;filter:url(#s)}</style></defs><rect class="a"/></svg>')
    assert _safe_svg(svg)


@pytest.mark.parametrize("bad", [
    '<svg><script>alert(1)</script></svg>',
    '<svg><foreignObject><b>hi</b></foreignObject></svg>',
    '<svg><image href="https://evil.example/x.png"/></svg>',
    '<svg><rect onload="x()"/></svg>',
    '<svg><a href="javascript:x()">l</a></svg>',
    '<svg><style>@import url(https://evil.example/f.css)</style></svg>',
    '<svg><style>@font-face{src:url("data:font/woff2;base64,AAA")}</style></svg>',
    '<svg><animate attributeName="x"/></svg>',
    '<svg><rect fill="url(https://evil.example/t.png)"/></svg>',
    '<!DOCTYPE svg [<!ENTITY x "y">]><svg></svg>',
    'no svg here',
])
def test_safe_svg_rejects_unsafe(bad):
    with pytest.raises(ValueError):
        _safe_svg(bad)


def test_json_from_handles_nested_fenced_and_trailing_prose():
    assert _json_from('{"a": {"b": 1}}') == {"a": {"b": 1}}
    assert _json_from('```json\n{"x": 2}\n```') == {"x": 2}
    assert _json_from('here: {"y": 3} hope this helps :}') == {"y": 3}
