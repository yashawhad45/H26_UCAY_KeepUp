"""usages.py – Locate every usage of a dependency inside the target repo.

Exposes:
    find_usages(repo_path: Path, package_name: str) -> list[UsageLocation]

Step 0: stub returning one fake UsageLocation.
Real implementation: walk .py files, parse import statements with ast, record
file + line + snippet for every import that matches the package name (handling
common import aliases, e.g. `import requests as r`).
"""

from __future__ import annotations

from pathlib import Path

from exitcapsule.schema import UsageLocation


def find_usages(repo_path: Path, package_name: str) -> list[UsageLocation]:
    """Return all source locations where *package_name* is imported/used.

    Currently a stub – returns one synthetic location.
    """
    return [
        UsageLocation(
            file="linkwatch/core.py",
            line=5,
            snippet=f"import {package_name}",
        )
    ]


if __name__ == "__main__":
    import sys
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    pkg = sys.argv[2] if len(sys.argv) > 2 else "requests"
    for loc in find_usages(path, pkg):
        print(loc.model_dump_json(indent=2))
