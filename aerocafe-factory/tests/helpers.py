"""Shared: locate the brand output folder under test."""
import os
from pathlib import Path

BASE = Path(__file__).parents[1] / "output"


def out_dir():
    """Brand folder under test: BRAND_OUT if set (factory run), else the most recently
    generated brand. Ranked by brand.json mtime — a re-render rewrites that file, but the
    directory's own mtime can stay stale, so dir mtime would pick the wrong brand."""
    env = os.environ.get("BRAND_OUT")
    if env:
        return Path(env)
    specs = list(BASE.glob("*/brand.json")) if BASE.exists() else []
    assert specs, "no brand output — run factory.py first"
    return max(specs, key=lambda p: p.stat().st_mtime).parent
