#!/usr/bin/env python3
"""AeroCafé Brand Factory orchestrator.

Pipeline: BRAND.md -> LLM generates site content (JSON) -> Jinja2 render
-> deterministic + Playwright tests -> LLM tone/style judge -> retry or ship.

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
import urllib.error
import urllib.request
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent
OUTPUT = ROOT / "output" / "index.html"


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

# Brand palette guardrails the renderer enforces (BRAND.md is the source of truth
# for the model; these keep the deterministic output on-spec regardless).
PALETTE = {"espresso": "#2b1d14", "cream": "#f4ece2", "accent": "#d98e3b"}


def chat(prompt: str) -> str:
    """One OpenRouter chat completion. ponytail: plain POST, no SDK."""
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
    try:
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"OpenRouter HTTP {e.code}: {e.read().decode(errors='replace')}")
    if "choices" not in data:
        raise RuntimeError(f"OpenRouter error response: {json.dumps(data)}")
    return data["choices"][0]["message"]["content"]


def _json_from(text: str) -> dict:
    """Pull the first JSON object out of a model response (handles ```json fences)."""
    # 1. Try to find a markdown json code block
    block_match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if block_match:
        try:
            return json.loads(block_match.group(1))
        except json.JSONDecodeError:
            pass

    # 2. Fall back to finding the outermost braces
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON in model output:\n{text}")

    return json.loads(text[start : end + 1])


def generate(brand: str, feedback: str | None) -> dict:
    prompt = f"""You are a brand copywriter. Using the brand brief below, produce
the content for a single-page microsite. Obey every guardrail in the brief.

Return ONLY a JSON object with these keys:
  title      - browser tab title (<= 60 chars)
  headline   - the H1
  subhead    - one supporting sentence
  sections   - array of exactly 3 objects, each {{"title": ..., "body": ...}}
  cta_text   - call-to-action label
  cta_href   - a plausible href (e.g. "#locations")

BRAND BRIEF:
{brand}
"""
    if feedback:
        prompt += f"\nA previous attempt was rejected. Fix this feedback:\n{feedback}\n"
    return _json_from(chat(prompt))


def _safe_href(href) -> str:
    """Model-controlled href: allow only safe schemes, else neutralize to '#'."""
    href = (href or "").strip()
    if href.startswith(("#", "/", "http://", "https://", "mailto:")):
        return href
    return "#"  # blocks javascript:, data:, etc.


def render(content: dict) -> str:
    content = {**content, "cta_href": _safe_href(content.get("cta_href"))}
    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)
    html = env.get_template("layout.html").render(**content, **PALETTE)
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(html)
    return html


def run_tests() -> tuple[bool, str]:
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(ROOT / "tests")],
        capture_output=True, text=True,
    )
    return r.returncode == 0, r.stdout + r.stderr


def judge(brand: str, html: str) -> tuple[bool, str]:
    prompt = f"""You are a strict Tone & Style Judge. Compare the rendered HTML
against the brand brief. Reply ONLY with JSON: {{"pass": true|false, "feedback": "..."}}.
Fail it if the copy violates any guardrail (banned words, wrong voice, missing
required elements). Feedback must be specific and actionable.

BRAND BRIEF:
{brand}

RENDERED HTML:
{html}
"""
    v = _json_from(chat(prompt))
    # only a real boolean true passes; "false"/"no"/missing all fail
    return v.get("pass") is True, v.get("feedback", "")


def main():
    brand = (ROOT / "BRAND.md").read_text()
    feedback = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"\n=== Attempt {attempt}/{MAX_ATTEMPTS} ===")
        try:
            content = generate(brand, feedback)
            html = render(content)
        except Exception as e:  # bad JSON, transient API glitch, render error
            print(f"generation failed: {e}")
            feedback = f"Previous attempt errored, fix it:\n{e}"
            continue
        print(f"rendered -> {OUTPUT}")

        ok, log = run_tests()
        print(log.strip())
        if not ok:
            feedback = f"Automated tests failed:\n{log}"
            continue

        passed, fb = judge(brand, html)
        print(f"judge: {'PASS' if passed else 'FAIL'} — {fb}")
        if passed:
            print(f"\n✅ Verified asset ready: {OUTPUT}")
            return 0
        feedback = fb

    print("\n❌ Could not produce a verified asset within attempt budget.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
