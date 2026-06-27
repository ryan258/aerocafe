# **SYSTEM SPECIFICATION: AeroCafé Brand Factory**

**Target Agent:** Terminal Coding Assistant (Claude Code / Cline / Aider)

**Execution Context:** Clean directory, Python 3.11+ environment

## **BLUF (Bottom Line Up Front)**

This specification directs the automatic assembly of an agentic **Creative Brand Factory**. The system ingests high-level design constraints (BRAND.md), generates an interactive microsite, launches it inside a sandboxed Playwright browser to test for rendering errors, uses Gemini 2.5 Flash as a qualitative "Tone & Style Judge", and outputs a fully verified, deployable index.html.

## **1\. Directory Structure**

Your task is to instantiate the following structure:

aerocafe-factory/
├── BRAND.md                 \# Static brand context & guardrails
├── requirements.txt         \# Package dependencies
├── factory.py               \# Main Orchestrator script
├── templates/
│   └── layout.html          \# Jinja2 template for the microsite
├── tests/
│   ├── test\_linter.py       \# Deterministic HTML/CSS sanity checks
│   └── test\_visual.py       \# Headless Playwright rendering tests
└── output/
    └── index.html           \# Final verified production-ready asset

## **2\. Dependencies (requirements.txt)**

Install these dependencies first:

- playwright\>=1.40.0
- jinja2\>=3.1.0
- beautifulsoup4\>=4.12.0
- pytest\>=7.4.0

Model calls go through **OpenRouter** (OpenAI-compatible HTTP API) via stdlib
`urllib` — no provider SDK. Set `OPENROUTER_API_KEY` (and optionally
`OPENROUTER_MODEL`, default `google/gemini-2.5-flash`) in a `.env` file.
After install, run `playwright install chromium` for the visual tests.
