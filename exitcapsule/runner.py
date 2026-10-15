"""runner.py – Run the target's test suite in isolated venvs.

Exposes:
    run_tests(repo_path: Path, entry: DependencyEntry) -> Observed

Step 0: stub returning fake Observed data.
Real implementation:
  1. Create venvs/baseline_<name>/ → install original pinned version → run pytest.
  2. Create venvs/replacement_<name>/ → install proposed replacement → run pytest.
  3. Capture stdout/stderr; compute diff_summary.
  4. Return Observed with both results + commands_run list.
"""

from __future__ import annotations

from pathlib import Path

from exitcapsule.schema import DependencyEntry, Observed


def run_tests(repo_path: Path, entry: DependencyEntry) -> Observed:
    """Run tests against baseline and replacement dependency, return Observed.

    Currently a stub – returns synthetic observed data (executed=False).
    """
    pkg = entry.details.name
    replacement = entry.ai_generated.proposed_replacement or "unknown"

    baseline_cmd = (
        f"python -m venv venvs/baseline_{pkg} && "
        f"venvs/baseline_{pkg}/bin/pip install {pkg}=={entry.details.pinned_version} && "
        f"venvs/baseline_{pkg}/bin/pytest {repo_path}"
    )
    replacement_cmd = (
        f"python -m venv venvs/replacement_{pkg} && "
        f"venvs/replacement_{pkg}/bin/pip install {replacement} && "
        f"venvs/replacement_{pkg}/bin/pytest {repo_path}"
    )

    return Observed(
        baseline_test_result="not_run",
        replacement_test_result="not_run",
        diff_summary="Stub: tests not executed in Step 0.",
        commands_run=[baseline_cmd, replacement_cmd],
    )


if __name__ == "__main__":
    import sys
    from exitcapsule.schema import DependencyDetails, DependencyEntry

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    dummy = DependencyEntry(
        details=DependencyDetails(
            name="requests",
            pinned_version="2.28.0",
            latest_version="2.32.3",
            source_file="requirements.txt",
        )
    )
    print(run_tests(path, dummy).model_dump_json(indent=2))
