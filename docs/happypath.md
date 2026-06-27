# AeroCafe Happy Path

This is the end-to-end demo path for the AeroCafe Brand Factory. It shows the
factory turning a static brand brief into a verified microsite, with deterministic
checks, browser rendering checks, and an LLM tone judge before the asset ships.

## Demo Goal

Generate a calm, premium airport coffee microsite from `BRAND.md`, prove it
renders cleanly, and leave the finished HTML at:

```text
aerocafe-factory/output/index.html
```

`output/` is intentionally ignored. It is the live build target, not a checked-in
source file.

## Setup

Run from the factory directory:

```bash
cd aerocafe-factory
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Edit `.env` and set:

```text
OPENROUTER_API_KEY=sk-or-...
```

`OPENROUTER_MODEL` is optional and defaults to `google/gemini-2.5-flash`.

## Run The Factory

```bash
python factory.py
```

Expected success signal:

```text
=== Attempt 1/3 ===
rendered -> .../aerocafe-factory/output/index.html
...
judge: PASS - ...
Verified asset ready: .../aerocafe-factory/output/index.html
```

If an attempt fails, the factory feeds the failure back into the next generation
attempt. It stops after three attempts.

## Verify The Asset

After `factory.py` succeeds, run the full gate:

```bash
python -m pytest -q tests
```

Expected result:

```text
10 passed
```

The gate covers:

- HTML structure: title, one `h1`, exactly three sections, and a linked CTA.
- Brand guardrails: locked amber accent and no gradients.
- Link safety: generated CTA URLs cannot use dangerous schemes such as
  `javascript:`, `data:`, or `vbscript:`.
- Browser rendering: Playwright opens the generated page, checks for console
  errors, confirms the headline is visible, and verifies mobile content does not
  overflow horizontally.

## Demo Script

1. Show `BRAND.md` as the source of truth: fast airport coffee, calm premium
   voice, espresso/cream/amber palette, and no stock-copy cliches.
2. Run `python factory.py` and point out the three-stage loop:
   generation, deterministic/browser verification, tone judging.
3. Open `output/index.html` and narrate the result as a traveler-facing page:
   one focused headline, short calm copy, three scannable sections, and one CTA.
4. Run `python -m pytest -q tests` to show the page is not just generated, but
   verified.
5. Mention that `output/index.html` is ignored so demos always prove the factory
   can reproduce the asset from source.

## Failure Cases Worth Showing

These are useful for testing and for explaining why the gates exist:

- Remove Playwright or skip `playwright install chromium`: the browser gate fails
  instead of silently skipping rendering checks.
- Change the template to use a gradient: `test_palette_locked` fails.
- Force a generated CTA href like `javascript:alert(1)`: `render()` neutralizes
  it to `#`, and the linter guards against dangerous schemes.
- Return `"pass": "false"` from the judge: it does not pass, because only a real
  boolean `true` is accepted.

## Reset For Another Demo

```bash
rm -rf output
python factory.py
python -m pytest -q tests
```

The regenerated `output/index.html` should still satisfy the same deterministic
and browser checks.
