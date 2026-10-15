# KeepUp

Dependency Exit Capsule generator for the H26 hackathon (Track 1: Gemma 4 Dependency Resilience).

---

## Overview

KeepUp analyses a target Python repository, identifies dependencies that are
at risk of becoming unavailable or unmaintained, asks Gemma 4 to propose
safe replacements, verifies the proposals by running the target's own test
suite against both the original and the replacement dependency, and finally
emits a **Dependency Exit Capsule** (`capsule.json` + `capsule.md`).

---

## Model / Version / Access method / License terms

| Field          | Value |
|----------------|-------|
| Model          | Gemma 4 (`gemma-4-26b-a4b-it`) |
| Access method  | Google AI Studio API (`google-genai` SDK) |
| License        | Apache 2.0 |

Configuration is loaded from environment variables (see `.env.example`).
Copy `.env.example` → `.env` and fill in your `GEMMA_API_KEY`.

---

## How to run

```bash
# 1. Create and activate a virtual environment
python -m venv venvs/main
# Windows:  venvs\main\Scripts\activate
# Unix:     source venvs/main/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and configure env vars
cp .env.example .env
# edit .env – add your GEMMA_API_KEY

# 4. Run against the bundled target repo
python -m exitcapsule.cli --repo ./target/LinkWatch

# Outputs: capsule.json and capsule.md in the current directory
```

---

## Architecture

```
exitcapsule/
├── schema.py        – Pydantic models (Capsule, DependencyEntry, …)
├── scanner.py       – Detect at-risk dependencies from repo + PyPI metadata
├── usages.py        – Locate every usage of each dependency in the source tree
├── gemma_client.py  – Call Gemma 4 for replacement proposals
├── runner.py        – Run tests in isolated venvs; diff results
├── capsule.py       – Render capsule.json + capsule.md
└── cli.py           – `python -m exitcapsule.cli` entry point
```

Data flows: `cli` → `scanner` → `usages` → `gemma_client` → `runner` → `capsule`.

---

## Limitations

- **No security scoring**: vulnerability analysis is out of scope for this track.
- **venv isolation**: the runner creates fresh venvs per dependency pair; slow
  on first run because pip must download packages each time.
- **Gemma rate limits**: the hosted AI Studio endpoint may throttle requests;
  failures are recorded as limitations in the capsule rather than crashing.
- **Dynamic imports**: packages imported only at runtime (e.g. via
  `importlib`) will not be detected by the static scanner.
- **Private packages**: packages not on PyPI cannot be checked for latest
  version or risk indicators.
