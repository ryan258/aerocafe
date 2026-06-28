#!/usr/bin/env python3
"""AeroCafé Brand Factory orchestrator.

Pipeline per attempt:
  BRAND.md
   -> brand spec (1 LLM call: strategy, palette, type, voice, applications, microsite)
   -> logo SVG    (1 focused LLM call, conditioned on the spec)
   -> render deliverables (style guide, microsite, logo.svg, brand.json)
   -> deterministic + Playwright tests
   -> LLM tone/style judge
   -> retry with feedback, or ship.

Model calls go through OpenRouter (OpenAI-compatible API).

Setup:  pip install -r requirements.txt && playwright install chromium
        cp .env.example .env   # then add your OPENROUTER_API_KEY
Run:    python factory.py
"""
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent
OUT = ROOT / "output"


def _slug(name: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-") or "brand"


def _load_dotenv():
    """ponytail: load .env (KEY=VALUE per line) into os.environ; no dotenv dep."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


_load_dotenv()
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")
MAX_ATTEMPTS = 3


def chat(prompt: str, retries: int = 3) -> str:
    """One OpenRouter chat completion, retrying transient 5xx/network errors.
    ponytail: plain POST, no SDK; fixed small backoff, bump retries if the provider is flakier."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("OPENROUTER_API_KEY not set")
    body = json.dumps(
        {"model": MODEL, "messages": [{"role": "user", "content": prompt}]}
    ).encode()
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    last = ""
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read())
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
            last = f"error response: {json.dumps(data)}"  # e.g. OpenRouter 502 in a 200 body
        except urllib.error.HTTPError as e:
            if e.code < 500:  # 4xx (bad key/request) won't fix by retrying
                sys.exit(f"OpenRouter HTTP {e.code}: {e.read().decode(errors='replace')}")
            last = f"HTTP {e.code}"
        except urllib.error.URLError as e:
            last = str(e)
        if i < retries - 1:
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"OpenRouter failed after {retries} tries: {last}")


def _json_from(text: str) -> dict:
    """Pull the first JSON object out of a model response (handles ```json fences)."""
    block = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if block:
        text = block.group(1)
    start = text.find("{")
    if start == -1:
        raise ValueError(f"no JSON in model output:\n{text}")
    # raw_decode reads the first complete object and ignores any trailing prose.
    return json.JSONDecoder().raw_decode(text[start:])[0]


def _safe_href(href) -> str:
    """Model-controlled href: allow only safe schemes, else neutralize to '#'."""
    href = (href or "").strip()
    if href.startswith(("#", "/", "http://", "https://", "mailto:")):
        return href
    return "#"  # blocks javascript:, data:, etc.


# Logo-safe SVG subset (plus any "fe…" filter primitive). Anything outside it — script,
# image, foreignObject, a, animate*, … — is rejected, not scrubbed, so it never reaches
# |safe. <use>/<textPath> are allowed but their href is restricted to internal #ids
# (the attr check below); <style> is allowed but its CSS text is scanned for external refs.
_SVG_OK_TAGS = {
    "svg", "g", "defs", "title", "desc", "symbol", "style", "filter", "use",
    "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "text", "tspan", "textPath", "linearGradient", "radialGradient", "stop",
    "clipPath", "mask",
}


def _safe_svg(text: str) -> str:
    """Validate model SVG against a logo-safe allowlist (it's rendered inline with |safe).
    Returns the <svg> unchanged if clean; raises ValueError otherwise so the caller retries."""
    if re.search(r"<!doctype|<!entity", text, re.IGNORECASE):
        raise ValueError("SVG contains DTD/entity declarations")  # billion-laughs guard
    m = re.search(r"<svg.*?</svg>", text, re.DOTALL | re.IGNORECASE)
    if not m:
        raise ValueError("no <svg> in model output")
    svg = m.group(0)
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as e:
        raise ValueError(f"unparseable SVG: {e}")

    local = lambda tag: tag.split("}", 1)[-1] if isinstance(tag, str) else ""
    for el in root.iter():
        tag = local(el.tag)
        if tag not in _SVG_OK_TAGS and not tag.startswith("fe"):  # fe… = filter primitives
            raise ValueError(f"disallowed SVG element: <{tag}>")
        if tag == "style":
            css = (el.text or "").lower()
            if "@import" in css or re.search(r"url\(\s*['\"]?\s*(?!#)", css) \
                    or re.search(r"(?i)(javascript|data)\s*:", css):
                raise ValueError("unsafe CSS in <style> (external @import/url or scheme)")
        for name, val in el.attrib.items():
            ln = local(name).lower()
            if ln.startswith("on"):
                raise ValueError(f"event-handler attribute: {name}")
            if re.search(r"(?i)(javascript|data)\s*:", val):
                raise ValueError(f"unsafe scheme in {name}: {val}")
            if re.search(r"(?i)url\(\s*['\"]?\s*(?!#)", val):  # url(#id) ok, url(http/data) not
                raise ValueError(f"external url() in {name}: {val}")
            if ln == "href" and not val.lstrip().startswith("#"):  # covers xlink:href too
                raise ValueError(f"external href: {val}")
    return svg.strip()


SPEC_SCHEMA = """{
  "name": "brand name",
  "tagline": "short memorable tagline",
  "mission": "one sentence — why the brand exists",
  "vision": "one sentence — the future it's building toward",
  "audience": "who this is for (specific)",
  "positioning": "one-paragraph positioning statement",
  "personality": ["3-5 brand adjectives"],
  "values": [{"name": "...", "desc": "one line"}],            // 3-5
  "palette": [                                                  // 4-6 colors
    {"name": "...", "hex": "#rrggbb", "role": "primary|background|accent|secondary|neutral", "usage": "where/when to use"}
  ],
  "typography": {
    "heading": {"family": "a real Google Font", "rationale": "why"},
    "body": {"family": "a real Google Font", "rationale": "why"},
    "scale": ["e.g. H1 48px", "H2 32px", "Body 16px"]
  },
  "voice": {
    "summary": "how the brand speaks",
    "do": ["...", "..."],
    "dont": ["...", "..."],
    "sample": "one paragraph of on-brand copy"
  },
  "logo": {"concept": "describe the mark", "usage_do": ["..."], "usage_dont": ["..."]},
  "imagery": "art direction for photography/illustration",
  "applications": ["concrete touchpoints, e.g. business card, packaging, app icon"],
  "microsite": {
    "headline": "hero H1",
    "subhead": "one supporting sentence",
    "sections": [{"title": "...", "body": "..."}],            // exactly 3
    "cta_text": "call to action",
    "cta_href": "#anchor or https URL"
  }
}"""


def generate_brand(brand: str, feedback: str | None) -> dict:
    prompt = f"""You are a senior brand strategist and designer. From the brand brief
below, design a complete, cohesive brand. Obey every guardrail in the brief.
Palette must meet WCAG 2.2 AA contrast: the primary text color must reach at least
4.5:1 against the background color, AND the accent must reach at least 4.5:1 against the
background (the accent is used for button text and links). Use exactly one accent.
Include at least one near-neutral color (a light off-white or a deep near-black, low
saturation) intended for body text — not a saturated hue like orange or red.

Return ONLY a JSON object matching this schema exactly (comments are not part of JSON):
{SPEC_SCHEMA}

BRAND BRIEF:
{brand}
"""
    if feedback:
        prompt += f"\nA previous attempt was rejected. Fix this feedback:\n{feedback}\n"
    return _json_from(chat(prompt))


def generate_logo(spec: dict) -> str:
    bg = _site_colors(spec["palette"])["bg"]
    heading_font = spec["typography"]["heading"]["family"]
    prompt = f"""Design a logo for "{spec['name']}" — {spec.get('tagline','')}.
Concept: {spec['logo'].get('concept','')}
Use only these brand colors: {[p['hex'] for p in spec['palette']]}.

Output ONE self-contained inline SVG (a wordmark or logomark). Requirements:
- viewBox set, no external fonts/images, no <script>, no animations.
- No @font-face, no data: URIs, no url(...) to anything but an internal #id.
- If the wordmark uses <text>, set font-family to the brand heading font
  "{heading_font}" (the rendered pages load it) so the logo matches the brand —
  do NOT substitute Helvetica/Arial or claim a font you don't actually set.
- The wordmark/lettering MUST be clearly legible against the brand background color
  {bg} — use light or accent fills on a dark base, never dark-on-dark. No gradient
  that leaves letter interiors low-contrast.
- Keep it SIMPLE: it must read cleanly at small/icon sizes. Avoid clutter — no stray
  embers, corner marks, or piles of gradients.
- Clean, scalable, looks designed — not a placeholder.
Return ONLY the <svg>...</svg>, nothing else."""
    return _safe_svg(chat(prompt))


def _relative_luminance(hexcolor: str) -> float:
    r, g, b = (int(hexcolor[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast_ratio(c1: str, c2: str) -> float:
    """WCAG relative-contrast ratio: 1:1 (identical) .. 21:1 (black on white)."""
    l1, l2 = _relative_luminance(c1), _relative_luminance(c2)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)


def _chroma(hexcolor: str) -> int:
    r, g, b = (int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))
    return max(r, g, b) - min(r, g, b)  # 0 = neutral (gray/white/black), high = saturated hue


def _site_colors(palette: list[dict]) -> dict:
    by_role = {p.get("role"): p["hex"] for p in palette}
    bg = by_role.get("background", palette[-1]["hex"])
    cands = [p["hex"] for p in palette if p.get("role") != "accent"] or [palette[0]["hex"]]
    # Body text: prefer the most NEUTRAL color that still clears AA on bg, so a dark brand
    # with few neutrals doesn't get garish hued body text (e.g. orange on charcoal). Fall
    # back to the most readable color if none clear AA (the a11y gate then flags it).
    readable = [h for h in cands if contrast_ratio(h, bg) >= 4.5]
    text = (min(readable, key=lambda h: (_chroma(h), -contrast_ratio(h, bg)))
            if readable else max(cands, key=lambda h: contrast_ratio(h, bg)))
    # Cover band: darker of text/bg as background, lighter as foreground, so the style-guide
    # hero respects a dark-first brand instead of inverting to a light band.
    dark, light = sorted((text, bg), key=_relative_luminance)
    return {
        "primary": text,
        "bg": bg,
        "accent": by_role.get("accent", by_role.get("secondary", palette[0]["hex"])),
        "cover_bg": dark,
        "cover_fg": light,
    }


def _font_link(typ: dict) -> str:
    fam = lambda n: n.strip().replace(" ", "+")
    h, b = fam(typ["heading"]["family"]), fam(typ["body"]["family"])
    return (
        f"https://fonts.googleapis.com/css2?family={h}:wght@400;700"
        f"&family={b}:wght@400;600&display=swap"
    )


def render(spec: dict) -> tuple[Path, str, str]:
    """Render all deliverables into output/<slug>/. Returns (dir, style-guide, microsite)."""
    d = OUT / _slug(spec["name"])
    d.mkdir(parents=True, exist_ok=True)
    (d / "brand.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False))
    (d / "logo.svg").write_text(spec["logo"]["svg"])

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)
    colors = _site_colors(spec["palette"])
    ctx = dict(
        colors=colors,
        font_link=_font_link(spec["typography"]),
        heading_font=spec["typography"]["heading"]["family"],
        body_font=spec["typography"]["body"]["family"],
    )

    guide = env.get_template("styleguide.html").render(b=spec, **ctx)
    (d / "styleguide.html").write_text(guide)

    ms = {**spec["microsite"], "cta_href": _safe_href(spec["microsite"].get("cta_href"))}
    site = env.get_template("layout.html").render(title=spec["name"], **ms, **ctx)
    (d / "index.html").write_text(site)
    return d, guide, site


def run_tests(brand_dir: Path) -> tuple[bool, str]:
    # tests target this brand's folder via BRAND_OUT
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(ROOT / "tests")],
        capture_output=True, text=True,
        env={**os.environ, "BRAND_OUT": str(brand_dir)},
    )
    return r.returncode == 0, r.stdout + r.stderr


def judge(brand: str, guide_html: str, site_html: str) -> tuple[bool, str]:
    prompt = f"""You are a strict brand design director. Judge BOTH deliverables — the
style guide and the microsite — against the brief. Reply ONLY with JSON:
{{"pass": true|false, "feedback": "..."}}.
Fail it for: guardrail violations, incoherent or generic strategy, a weak/placeholder
or amateur logo, off-brand voice or copy, banned phrases, a weak/broken call-to-action,
or missing style-guide sections. Judge both; a problem in either fails the suite.
Feedback must be specific and actionable.
Do NOT evaluate color contrast or WCAG ratios: page/text contrast is already verified by a
deterministic automated test that passed before you were called. Do not estimate ratios or
fail on contrast — trust that test and focus on strategy, voice, copy, guardrails, and logo craft.

BRAND BRIEF:
{brand}

STYLE GUIDE HTML:
{guide_html}

MICROSITE HTML:
{site_html}
"""
    v = _json_from(chat(prompt))
    return v.get("pass") is True, v.get("feedback", "")


def main():
    brief = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "BRAND.md"
    brand = brief.read_text()
    print(f"brief: {brief}")
    feedback = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"\n=== Attempt {attempt}/{MAX_ATTEMPTS} ===")
        try:
            spec = generate_brand(brand, feedback)
            spec["logo"]["svg"] = generate_logo(spec)
            brand_dir, guide, site = render(spec)
        except Exception as e:  # bad JSON, transient API glitch, render error
            print(f"generation failed: {e}")
            feedback = f"Previous attempt errored, fix it:\n{e}"
            continue
        print(f"rendered -> {brand_dir}/ (styleguide.html, index.html, logo.svg, brand.json)")

        ok, log = run_tests(brand_dir)
        print(log.strip())
        if not ok:
            feedback = f"Automated tests failed:\n{log}"
            continue

        try:
            passed, fb = judge(brand, guide, site)
        except Exception as e:  # judge API/parse glitch — brand already passed tests, retry it
            print(f"judge errored, retrying: {e}")
            feedback = None
            continue
        print(f"judge: {'PASS' if passed else 'FAIL'} — {fb}")
        if passed:
            print(f"\n✅ Verified brand suite ready in {brand_dir}/")
            return 0
        feedback = fb

    print("\n❌ Could not produce a verified brand within attempt budget.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
