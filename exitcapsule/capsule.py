"""capsule.py – Render the Dependency Exit Capsule to capsule.json + capsule.md.

Exposes:
    render(capsule: Capsule, out_dir: Path) -> None

AI-generated content and observed/executed evidence are kept in visibly
separate sections so reviewers can immediately see what was machine-generated
versus what was actually measured.
"""

from __future__ import annotations

import json
from pathlib import Path

from exitcapsule.schema import Capsule, DependencyEntry


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def _write_json(capsule: Capsule, out_dir: Path) -> Path:
    path = out_dir / "capsule.json"
    path.write_text(
        capsule.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------

_SEPARATOR = "---"


def _md_dependency(entry: DependencyEntry) -> str:
    d = entry.details
    lines: list[str] = []

    # Header
    lines.append(f"## 📦 `{d.name}`")
    lines.append("")

    # Details table
    lines.append("### Details")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| Pinned version | `{d.pinned_version or 'unset'}` |")
    lines.append(f"| Latest version | `{d.latest_version or 'unknown'}` |")
    lines.append(f"| Source file    | `{d.source_file}` |")
    lines.append("")

    # Risk indicators
    if entry.risk_indicators:
        lines.append("### ⚠️ Risk Indicators")
        lines.append("")
        for ri in entry.risk_indicators:
            lines.append(f"- **{ri.type}** ({ri.source}): {ri.evidence}")
        lines.append("")

    # Usage locations
    if entry.usage_locations:
        lines.append("### 🔍 Usage Locations")
        lines.append("")
        for ul in entry.usage_locations:
            lines.append(f"- `{ul.file}` line {ul.line}: `{ul.snippet}`")
        lines.append("")

    # ── AI-GENERATED (clearly labelled, never mixed with observed) ──────────
    lines.append("### 🤖 AI-Generated (unverified)")
    lines.append("")
    lines.append(
        "> ⚠️ The content in this section was produced by a language model "
        f"(`{entry.ai_generated.model}`) and has **not** been independently "
        "verified. Treat it as a starting point, not a guarantee."
    )
    lines.append("")
    ai = entry.ai_generated
    lines.append(f"**Proposed replacement:** `{ai.proposed_replacement or 'none'}`  ")
    lines.append(f"**Confidence:** {ai.confidence if ai.confidence is not None else 'N/A'}  ")
    lines.append(f"**Model:** {ai.model} / {ai.model_version}")
    lines.append("")
    if ai.rationale:
        lines.append(f"**Rationale:** {ai.rationale}")
        lines.append("")
    if ai.migration_steps:
        lines.append("**Migration steps:**")
        lines.append("")
        for step in ai.migration_steps:
            lines.append(f"1. {step}")
        lines.append("")
    if ai.suggested_tests:
        lines.append("**Suggested tests:**")
        lines.append("")
        for t in ai.suggested_tests:
            lines.append(f"- `{t}`")
        lines.append("")

    # ── OBSERVED / EXECUTED (clearly labelled, never mixed with AI output) ──
    lines.append("### 🧪 Observed (executed)")
    lines.append("")
    obs = entry.observed
    executed_badge = "✅ Yes" if entry.executed else "❌ No (stub / not run)"
    lines.append(f"**Tests executed:** {executed_badge}")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|---|---|")
    lines.append(f"| Baseline result     | `{obs.baseline_test_result or 'N/A'}` |")
    lines.append(f"| Replacement result  | `{obs.replacement_test_result or 'N/A'}` |")
    lines.append(f"| Diff summary        | {obs.diff_summary or 'N/A'} |")
    lines.append("")
    if obs.commands_run:
        lines.append("**Commands that would be run:**")
        lines.append("")
        lines.append("```bash")
        for cmd in obs.commands_run:
            lines.append(cmd)
        lines.append("```")
        lines.append("")

    # Compatibility gaps & open concerns
    if entry.compatibility_gaps:
        lines.append("### Compatibility Gaps")
        lines.append("")
        for g in entry.compatibility_gaps:
            lines.append(f"- {g}")
        lines.append("")

    if entry.open_concerns:
        lines.append("### Open Concerns")
        lines.append("")
        for c in entry.open_concerns:
            lines.append(f"- {c}")
        lines.append("")

    lines.append(_SEPARATOR)
    lines.append("")
    return "\n".join(lines)


def _write_markdown(capsule: Capsule, out_dir: Path) -> Path:
    path = out_dir / "capsule.md"
    lines: list[str] = []

    lines.append("# Dependency Exit Capsule")
    lines.append("")
    lines.append(f"**Generated at:** {capsule.generated_at.isoformat()}  ")
    lines.append(f"**Target repo:** `{capsule.target_repo}`  ")
    lines.append(f"**Dependencies analysed:** {len(capsule.dependencies)}")
    lines.append("")
    lines.append(_SEPARATOR)
    lines.append("")

    for entry in capsule.dependencies:
        lines.append(_md_dependency(entry))

    # Global limitations
    lines.append("## ⚙️ Limitations")
    lines.append("")
    if capsule.global_limitations:
        for lim in capsule.global_limitations:
            lines.append(f"- {lim}")
    else:
        lines.append("_None recorded._")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render(capsule: Capsule, out_dir: Path) -> None:
    """Write capsule.json and capsule.md to *out_dir*."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = _write_json(capsule, out_dir)
    md_path = _write_markdown(capsule, out_dir)
    print(f"  [capsule] Wrote {json_path}")
    print(f"  [capsule] Wrote {md_path}")


if __name__ == "__main__":
    # Quick smoke-test: render a one-entry capsule to ./
    from exitcapsule.schema import (
        AIGenerated,
        Capsule,
        DependencyDetails,
        DependencyEntry,
        Observed,
        RiskIndicator,
        UsageLocation,
    )

    dummy_capsule = Capsule(
        target_repo="./target/LinkWatch",
        dependencies=[
            DependencyEntry(
                details=DependencyDetails(
                    name="requests",
                    pinned_version="2.28.0",
                    latest_version="2.32.3",
                    source_file="requirements.txt",
                ),
                risk_indicators=[
                    RiskIndicator(
                        type="outdated_version",
                        evidence="2.28.0 → 2.32.3",
                        source="PyPI",
                    )
                ],
                usage_locations=[
                    UsageLocation(file="linkwatch/core.py", line=5, snippet="import requests")
                ],
                ai_generated=AIGenerated(
                    proposed_replacement="httpx",
                    rationale="httpx is a modern async-capable replacement.",
                    migration_steps=["Change import requests → import httpx"],
                    suggested_tests=["test_http_get_returns_200"],
                    confidence=0.85,
                ),
                observed=Observed(
                    baseline_test_result="not_run",
                    replacement_test_result="not_run",
                    diff_summary="Stub: not executed.",
                    commands_run=["pytest target/LinkWatch"],
                ),
                executed=False,
            )
        ],
        global_limitations=["Step 0 stub: no real scanning or test execution."],
    )
    render(dummy_capsule, Path("."))
