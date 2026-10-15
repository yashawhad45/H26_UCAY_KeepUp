"""gemma_client.py – Call Gemma 4 to propose dependency replacements.

Exposes:
    propose_replacement(entry: DependencyEntry) -> AIGenerated

Env vars (loaded via python-dotenv):
    LLM_BACKEND   : "local" | "hosted"  (default: "hosted")
    GEMMA_BASE_URL: base URL for local Ollama/OpenAI-compat endpoint
    GEMMA_MODEL   : model name (default: "gemma-4-26b-a4b-it")
    GEMMA_API_KEY : API key for Google AI Studio (hosted only)

Step 0: stub returning fake AI output regardless of env vars.
Real implementation: build a structured prompt from DependencyEntry, call
google.genai.Client (hosted) or a requests-based OpenAI-compat POST (local),
parse the JSON reply into AIGenerated.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from exitcapsule.schema import AIGenerated, DependencyEntry

load_dotenv()

LLM_BACKEND: str = os.getenv("LLM_BACKEND", "hosted")
GEMMA_BASE_URL: str = os.getenv("GEMMA_BASE_URL", "")
GEMMA_MODEL: str = os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it")
GEMMA_API_KEY: str = os.getenv("GEMMA_API_KEY", "")


def propose_replacement(entry: DependencyEntry) -> AIGenerated:
    """Ask Gemma 4 to propose a safe replacement for the at-risk dependency.

    Currently a stub – returns synthetic AI output.
    Real implementation (hosted): ::

        from google import genai
        client = genai.Client(api_key=GEMMA_API_KEY)
        response = client.models.generate_content(
            model=GEMMA_MODEL,
            contents=_build_prompt(entry),
        )
        return _parse_response(response.text)

    Real implementation (local OpenAI-compat)::

        import requests, json
        payload = {"model": GEMMA_MODEL, "messages": [...], "stream": False}
        r = requests.post(f"{GEMMA_BASE_URL}/chat/completions", json=payload)
        return _parse_response(r.json()["choices"][0]["message"]["content"])
    """
    pkg = entry.details.name
    return AIGenerated(
        proposed_replacement="httpx",
        rationale=(
            f"`{pkg}` is outdated. `httpx` is a modern, async-capable HTTP "
            "client with a compatible API surface."
        ),
        migration_steps=[
            f"Replace `import {pkg}` with `import httpx`.",
            "Change `requests.get(url)` → `httpx.get(url)` (same signature).",
            "For sessions, replace `requests.Session()` → `httpx.Client()`.",
        ],
        suggested_tests=[
            "test_http_get_returns_200",
            "test_session_headers_propagated",
            "test_timeout_raises",
        ],
        confidence=0.85,
        model=GEMMA_MODEL,
        model_version=GEMMA_MODEL,
    )


if __name__ == "__main__":
    from exitcapsule.schema import DependencyDetails, DependencyEntry

    dummy = DependencyEntry(
        details=DependencyDetails(
            name="requests",
            pinned_version="2.28.0",
            latest_version="2.32.3",
            source_file="requirements.txt",
        )
    )
    print(propose_replacement(dummy).model_dump_json(indent=2))
