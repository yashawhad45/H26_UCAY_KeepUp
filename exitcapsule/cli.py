"""cli.py – `python -m exitcapsule.cli` entry point.

Usage:
    python -m exitcapsule.cli --repo ./target/LinkWatch [--out .]

Pipeline (Step 0 – stubs):
    1. scanner.scan()        → list[DependencyEntry]   (risk detection)
    2. usages.find_usages()  → list[UsageLocation]     (code locations)
    3. gemma_client.propose_replacement() → AIGenerated (AI proposals)
    4. runner.run_tests()    → Observed                 (test execution)
    5. capsule.render()      → capsule.json + capsule.md
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from exitcapsule import __version__
from exitcapsule.schema import Capsule


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="exitcapsule",
        description="Generate a Dependency Exit Capsule for a Python repo.",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        required=True,
        metavar="PATH",
        help="Path to the target repository (e.g. ./target/LinkWatch).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("."),
        metavar="DIR",
        help="Output directory for capsule.json and capsule.md (default: .).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"exitcapsule {__version__}",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_path: Path = args.repo.resolve()
    out_dir: Path = args.out.resolve()

    if not repo_path.exists():
        print(f"[error] Repo path does not exist: {repo_path}", file=sys.stderr)
        return 1

    print(f"[exitcapsule {__version__}] Analysing: {repo_path}")
    print(f"[exitcapsule] Output dir : {out_dir}")
    print()

    # ── Step 1: Scan for at-risk dependencies ────────────────────────────────
    from exitcapsule import scanner
    print("[1/4] Scanning dependencies...")
    entries = scanner.scan(repo_path)
    print(f"      Found {len(entries)} at-risk package(s).")
    print()

    limitations: list[str] = [
        "Step 0 stub: scanner returns synthetic data, not real repo analysis.",
        "Step 0 stub: usages returns synthetic locations.",
        "Step 0 stub: Gemma client returns synthetic AI output (no real LLM call).",
        "Step 0 stub: runner does not execute tests.",
    ]

    # ── Step 2–4: Enrich each entry ──────────────────────────────────────────
    from exitcapsule import gemma_client, runner, usages

    for entry in entries:
        pkg = entry.details.name
        print(f"[2/4] Finding usages of '{pkg}'...")
        entry.usage_locations = usages.find_usages(repo_path, pkg)
        print(f"      {len(entry.usage_locations)} location(s).")

        print(f"[3/4] Asking Gemma 4 for replacement proposal for '{pkg}'...")
        entry.ai_generated = gemma_client.propose_replacement(entry)
        print(f"      Proposed: {entry.ai_generated.proposed_replacement!r} "
              f"(confidence {entry.ai_generated.confidence})")

        print(f"[4/4] Running tests for '{pkg}'...")
        entry.observed = runner.run_tests(repo_path, entry)
        entry.executed = False  # stub: not actually executed
        print(f"      Baseline: {entry.observed.baseline_test_result}  "
              f"Replacement: {entry.observed.replacement_test_result}")
        print()

    # ── Step 5: Render capsule ────────────────────────────────────────────────
    from exitcapsule import capsule as capsule_mod

    cap = Capsule(
        target_repo=str(repo_path),
        dependencies=entries,
        global_limitations=limitations,
    )

    print("[5/5] Rendering capsule...")
    capsule_mod.render(cap, out_dir)
    print()
    print("[DONE] Review capsule.md for the human-readable report.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
