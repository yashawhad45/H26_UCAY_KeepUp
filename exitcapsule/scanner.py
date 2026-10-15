"""scanner.py – Detect at-risk dependencies from the target repo + PyPI metadata.

Exposes:
    scan(repo_path: Path) -> list[DependencyEntry]

Step 0: stub returning one fake DependencyEntry so the pipeline runs end-to-end.
"""

from __future__ import annotations

from pathlib import Path

from exitcapsule.schema import (
    DependencyDetails,
    DependencyEntry,
    RiskIndicator,
)


def scan(repo_path: Path) -> list[DependencyEntry]:
    """Return a list of at-risk DependencyEntry objects for *repo_path*.

    Currently a stub – returns one synthetic entry.
    Real implementation: parse requirements*.txt / pyproject.toml / setup.cfg,
    query PyPI JSON API for latest version + release history, flag packages
    that are unpinned, outdated, deprecated, or low-activity.
    """
    stub_entry = DependencyEntry(
        details=DependencyDetails(
            name="requests",
            pinned_version="2.28.0",
            latest_version="2.32.3",
            source_file="requirements.txt",
        ),
        risk_indicators=[
            RiskIndicator(
                type="outdated_version",
                evidence="Pinned to 2.28.0; latest release is 2.32.3.",
                source="PyPI",
            )
        ],
    )
    return [stub_entry]


if __name__ == "__main__":
    import sys
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    for entry in scan(path):
        print(entry.model_dump_json(indent=2))
