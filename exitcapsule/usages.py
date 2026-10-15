"""usages.py – Locate every usage of a dependency inside the target repo.

Exposes:
    find_usages(repo_path: Path, package_name: str) -> list[UsageLocation]
    analyze_usages(repo_path: Path, package_name: str) -> UsageAnalysis
    get_import_names(package_name: str) -> list[str]
    find_non_python_mentions(repo_path: Path, package_name: str) -> list[NonPythonMention]

Computes:
- Distribution-to-import mapping (importlib.metadata + heuristics + overrides)
- AST-based usage discovery (import statements, aliases, calls, attribute accesses)
- 2 lines of context around every usage snippet
- Compact per-dependency summary of used functions/classes (for LLM prompt context)
- Non-Python references (requirements, CI configs, Dockerfiles, etc.)
- Limitations recording on parse or read errors
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from importlib.metadata import packages_distributions
from pathlib import Path
from typing import Any, List, Optional, Set

from pydantic import BaseModel, Field

from exitcapsule.schema import UsageLocation

# ---------------------------------------------------------------------------
# Directories and patterns to skip during repository walking
# ---------------------------------------------------------------------------
SKIP_DIRS: set[str] = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "venv",
    ".venv",
    "venvs",
    "env",
    ".env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    ".eggs",
    "build",
    "dist",
    ".idea",
    ".vscode",
}

# Well-known distribution name -> import package names override table
KNOWN_OVERRIDES: dict[str, list[str]] = {
    "beautifulsoup4": ["bs4"],
    "pillow": ["PIL"],
    "pyyaml": ["yaml"],
    "python-dateutil": ["dateutil"],
    "opencv-python": ["cv2"],
    "opencv-python-headless": ["cv2"],
    "protobuf": ["google.protobuf"],
    "scikit-learn": ["sklearn"],
    "typing-extensions": ["typing_extensions"],
    "pydantic-core": ["pydantic_core"],
    "setuptools": ["setuptools", "pkg_resources"],
    "attrs": ["attr", "attrs"],
    "apache-airflow": ["airflow"],
    "grpcio": ["grpc"],
    "psycopg2-binary": ["psycopg2"],
    "pymongo": ["pymongo", "bson"],
    "msgpack-python": ["msgpack"],
    "websocket-client": ["websocket"],
    "jinja2": ["jinja2"],
    "pygments": ["pygments"],
}

NON_PYTHON_FILENAMES: set[str] = {
    "dockerfile",
    "makefile",
    "justfile",
    "pipfile",
    "pipfile.lock",
    "containerfile",
}


# ---------------------------------------------------------------------------
# Extended Models
# ---------------------------------------------------------------------------

class NonPythonMention(BaseModel):
    """Mentions of a package in non-Python configuration/build/manifest files."""
    file: str
    line: int
    snippet: str


class UsageAnalysis(BaseModel):
    """Comprehensive analysis result for dependency usages across a repo."""
    package_name: str
    import_names: List[str]
    locations: List[UsageLocation] = Field(default_factory=list)
    summary: str = ""
    used_symbols: List[str] = Field(default_factory=list)
    non_python_mentions: List[NonPythonMention] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


class UsageList(list):
    """List subclass holding UsageLocation items while preserving analysis metadata."""
    def __init__(
        self,
        locations: list[UsageLocation],
        summary: str = "",
        used_symbols: list[str] | None = None,
        non_python_mentions: list[NonPythonMention] | None = None,
        limitations: list[str] | None = None,
    ) -> None:
        super().__init__(locations)
        self.summary = summary
        self.used_symbols = used_symbols or []
        self.non_python_mentions = non_python_mentions or []
        self.limitations = limitations or []


# ---------------------------------------------------------------------------
# Packaging & Import Resolution
# ---------------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    """Normalize a Python package name per PEP 503."""
    return re.sub(r"[-_.]+", "_", name).lower()


def get_import_names(package_name: str) -> list[str]:
    """Map a PyPI distribution name to its top-level Python import names.

    Uses `importlib.metadata.packages_distributions()` if installed in the
    current environment, falling back to an override table and normalized
    naming heuristics.
    """
    norm_pkg = _normalize_name(package_name)

    # 1. Query importlib.metadata.packages_distributions()
    try:
        dist_map = packages_distributions()
        dist_to_imports: dict[str, list[str]] = {}
        for imp_name, dists in dist_map.items():
            for dist in dists:
                norm_d = _normalize_name(dist)
                dist_to_imports.setdefault(norm_d, []).append(imp_name)

        if norm_pkg in dist_to_imports:
            return sorted(set(dist_to_imports[norm_pkg]))
    except Exception:
        pass

    # 2. Check override table
    if norm_pkg in KNOWN_OVERRIDES:
        return list(KNOWN_OVERRIDES[norm_pkg])

    hyphen_pkg = package_name.lower().replace("_", "-")
    if hyphen_pkg in KNOWN_OVERRIDES:
        return list(KNOWN_OVERRIDES[hyphen_pkg])

    # 3. Normalized-name heuristics
    candidates = {package_name, package_name.lower(), norm_pkg}
    return sorted(candidates)


# ---------------------------------------------------------------------------
# AST Node Visitor for Python Usages
# ---------------------------------------------------------------------------

def _unroll_attribute(node: ast.AST) -> tuple[str, str]:
    """Unroll an Attribute AST node into (full_chain, root_base_id).

    E.g. requests.exceptions.Timeout -> ("requests.exceptions.Timeout", "requests")
    """
    parts: list[str] = []
    curr = node
    while isinstance(curr, ast.Attribute):
        parts.append(curr.attr)
        curr = curr.value
    if isinstance(curr, ast.Name):
        parts.append(curr.id)
        parts.reverse()
        return ".".join(parts), curr.id
    return "", ""


class _DependencyUsageVisitor(ast.NodeVisitor):
    """AST visitor that tracks module imports, aliases, attributes, and call sites."""

    def __init__(
        self,
        target_imports: set[str],
        source_lines: list[str],
        rel_path: str,
    ) -> None:
        self.target_imports = target_imports
        self.target_imports_lower = {t.lower() for t in target_imports}
        self.source_lines = source_lines
        self.rel_path = rel_path

        # Scopes: local bound name -> target qualified name
        self.imported_modules: dict[str, str] = {}
        self.imported_symbols: dict[str, str] = {}
        self.local_instances: dict[str, str] = {}
        self.handled_nodes: set[int] = set()

        self.locations_by_line: dict[int, str] = {}
        self.used_symbols: set[str] = set()

    def _add_location(self, lineno: int) -> None:
        if lineno not in self.locations_by_line:
            start = max(1, lineno - 2)
            end = min(len(self.source_lines), lineno + 2)
            snippet = "\n".join(self.source_lines[start - 1 : end])
            self.locations_by_line[lineno] = snippet

    def _mark_handled(self, node: ast.AST) -> None:
        for child in ast.walk(node):
            self.handled_nodes.add(id(child))

    def _matches_target(self, root_name: str) -> bool:
        return (
            root_name in self.target_imports
            or root_name.lower() in self.target_imports_lower
        )

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if self._matches_target(root):
                local_name = alias.asname or alias.name
                self.imported_modules[local_name] = alias.name
                self._add_location(node.lineno)
                self.used_symbols.add(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            root = node.module.split(".")[0]
            if self._matches_target(root):
                self._add_location(node.lineno)
                for alias in node.names:
                    local_name = alias.asname or alias.name
                    full_name = f"{node.module}.{alias.name}"
                    self.imported_symbols[local_name] = full_name
                    # Record imported symbol name (e.g. Session, _parse_content_type_header)
                    self.used_symbols.add(alias.name)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Track assignments from constructor/factory calls (e.g. session = S() or s = requests.Session())
        if isinstance(node.value, ast.Call):
            call_func = node.value.func
            resolved: str | None = None
            if isinstance(call_func, ast.Name) and call_func.id in self.imported_symbols:
                resolved = self.imported_symbols[call_func.id]
            elif isinstance(call_func, ast.Attribute):
                chain, base = _unroll_attribute(call_func)
                if base in self.imported_modules:
                    mod = self.imported_modules[base]
                    suffix = chain.split(".", 1)[1] if "." in chain else ""
                    resolved = f"{mod}.{suffix}" if suffix else mod
            if resolved:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.local_instances[target.id] = resolved
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name):
            if func.id in self.imported_symbols:
                sym = self.imported_symbols[func.id]
                self.used_symbols.add(sym.split(".")[-1])
                self._add_location(node.lineno)
                self._mark_handled(func)
            elif func.id in self.imported_modules:
                sym = self.imported_modules[func.id]
                self.used_symbols.add(sym)
                self._add_location(node.lineno)
                self._mark_handled(func)
        elif isinstance(func, ast.Attribute):
            chain, base = _unroll_attribute(func)
            if base in self.imported_modules:
                mod = self.imported_modules[base]
                suffix = chain.split(".", 1)[1] if "." in chain else ""
                self.used_symbols.add(suffix or mod)
                self._add_location(node.lineno)
                self._mark_handled(func)
            elif base in self.imported_symbols:
                base_sym = self.imported_symbols[base]
                suffix = chain.split(".", 1)[1] if "." in chain else ""
                full_sym = f"{base_sym}.{suffix}" if suffix else base_sym
                self.used_symbols.add(suffix or full_sym.split(".")[-1])
                self._add_location(node.lineno)
                self._mark_handled(func)
            elif base in self.local_instances:
                inst_type = self.local_instances[base]
                suffix = chain.split(".", 1)[1] if "." in chain else ""
                short_inst = inst_type.split(".")[-1]
                self.used_symbols.add(f"{short_inst}.{suffix}" if suffix else short_inst)
                self._add_location(node.lineno)
                self._mark_handled(func)

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if id(node) in self.handled_nodes:
            self.generic_visit(node)
            return

        chain, base = _unroll_attribute(node)
        if base in self.imported_modules:
            mod = self.imported_modules[base]
            suffix = chain.split(".", 1)[1] if "." in chain else ""
            self.used_symbols.add(suffix or mod)
            self._add_location(node.lineno)
            self._mark_handled(node)
        elif base in self.imported_symbols:
            base_sym = self.imported_symbols[base]
            suffix = chain.split(".", 1)[1] if "." in chain else ""
            self.used_symbols.add(suffix or base_sym.split(".")[-1])
            self._add_location(node.lineno)
            self._mark_handled(node)
        elif base in self.local_instances:
            inst_type = self.local_instances[base]
            suffix = chain.split(".", 1)[1] if "." in chain else ""
            short_inst = inst_type.split(".")[-1]
            self.used_symbols.add(f"{short_inst}.{suffix}" if suffix else short_inst)
            self._add_location(node.lineno)
            self._mark_handled(node)

        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if id(node) in self.handled_nodes:
            return
        if isinstance(node.ctx, ast.Load):
            if node.id in self.imported_symbols:
                sym = self.imported_symbols[node.id]
                self.used_symbols.add(sym.split(".")[-1])
                self._add_location(node.lineno)
            elif node.id in self.imported_modules:
                self.used_symbols.add(self.imported_modules[node.id])
                self._add_location(node.lineno)


# ---------------------------------------------------------------------------
# Non-Python Scanner
# ---------------------------------------------------------------------------

def find_non_python_mentions(
    repo_path: Path,
    package_name: str,
    import_names: list[str] | None = None,
) -> list[NonPythonMention]:
    """Search requirements, CI workflows, Dockerfiles, and build manifests for mentions."""
    resolved_imports = import_names or get_import_names(package_name)
    names_to_match = {
        package_name,
        package_name.lower(),
        package_name.lower().replace("-", "_"),
        package_name.lower().replace("_", "-"),
    }
    names_to_match.update(resolved_imports)
    names_to_match.update([i.lower() for i in resolved_imports])

    sorted_names = sorted(names_to_match, key=len, reverse=True)
    regexes = [
        re.compile(rf"(?i)(?:^|[\s\"'\[,;=])({re.escape(name)})(?:$|[\s\"'\]<>=!~@,;])")
        for name in sorted_names
    ]

    mentions: list[NonPythonMention] = []

    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix == ".py":
            continue

        lower_name = path.name.lower()
        is_candidate = (
            lower_name in NON_PYTHON_FILENAMES
            or "dockerfile" in lower_name
            or "requirements" in lower_name
            or lower_name in {
                "pyproject.toml",
                "setup.cfg",
                "environment.yml",
                "environment.yaml",
                "gemfile",
            }
            or (".github" in path.parts and path.suffix in {".yml", ".yaml"})
            or (".circleci" in path.parts and path.suffix in {".yml", ".yaml"})
            or lower_name in {".gitlab-ci.yml", ".travis.yml", "azure-pipelines.yml"}
        )
        if not is_candidate:
            continue

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for idx, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            for r in regexes:
                if r.search(line):
                    mentions.append(
                        NonPythonMention(
                            file=path.relative_to(repo_path).as_posix(),
                            line=idx,
                            snippet=stripped,
                        )
                    )
                    break

    return mentions


# ---------------------------------------------------------------------------
# Core Analysis & Public API
# ---------------------------------------------------------------------------

def analyze_usages(repo_path: Path, package_name: str) -> UsageAnalysis:
    """Analyze all Python and non-Python usages of *package_name* in *repo_path*."""
    import_names = get_import_names(package_name)
    target_imports_set = set(import_names)

    locations: list[UsageLocation] = []
    used_symbols_set: set[str] = set()
    limitations: list[str] = []

    # Walk all .py files in repo_path
    for py_file in repo_path.rglob("*.py"):
        if not py_file.is_file():
            continue
        if any(part in SKIP_DIRS for part in py_file.parts):
            continue

        rel_path = py_file.relative_to(repo_path).as_posix()
        try:
            source = py_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                source = py_file.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                limitations.append(f"Failed to read {rel_path}: {exc}")
                continue
        except Exception as exc:
            limitations.append(f"Failed to read {rel_path}: {exc}")
            continue

        lines = source.splitlines()
        try:
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, ValueError) as exc:
            limitations.append(f"Syntax/parse error in {rel_path}: {exc}")
            continue

        visitor = _DependencyUsageVisitor(target_imports_set, lines, rel_path)
        visitor.visit(tree)

        for lineno, snippet in sorted(visitor.locations_by_line.items()):
            locations.append(
                UsageLocation(
                    file=rel_path,
                    line=lineno,
                    snippet=snippet,
                )
            )

        used_symbols_set.update(visitor.used_symbols)

    # Sort locations stably by file and line
    locations.sort(key=lambda loc: (loc.file, loc.line))

    # Format compact per-dependency summary
    sorted_symbols = sorted(s for s in used_symbols_set if s)
    if sorted_symbols:
        summary = f"Used {package_name} APIs ({len(sorted_symbols)}): {', '.join(sorted_symbols)}"
    else:
        summary = f"No specific functions or classes detected for {package_name}."

    # Non-Python mentions
    non_py = find_non_python_mentions(repo_path, package_name, import_names)

    return UsageAnalysis(
        package_name=package_name,
        import_names=import_names,
        locations=locations,
        summary=summary,
        used_symbols=sorted_symbols,
        non_python_mentions=non_py,
        limitations=limitations,
    )


def find_usages(repo_path: Path, package_name: str) -> list[UsageLocation]:
    """Return all source locations where *package_name* is imported or used.

    Returns a list of UsageLocation items with 2 lines of context.
    The returned list is also enriched with .summary, .used_symbols,
    .non_python_mentions, and .limitations attributes for downstream pipeline use.
    """
    analysis = analyze_usages(repo_path, package_name)
    return UsageList(
        locations=analysis.locations,
        summary=analysis.summary,
        used_symbols=analysis.used_symbols,
        non_python_mentions=analysis.non_python_mentions,
        limitations=analysis.limitations,
    )


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def _parse_cli_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="exitcapsule.usages",
        description="Find all Python and non-Python usages of a dependency in a repository.",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        metavar="PATH",
        help="Path to repository to inspect (default: .)",
    )
    parser.add_argument(
        "--package",
        type=str,
        metavar="NAME",
        help="Dependency / package name to find usages for (default: requests)",
    )
    parser.add_argument(
        "positional_repo",
        nargs="?",
        type=Path,
        metavar="REPO_PATH",
        help="Positional repository path (optional)",
    )
    parser.add_argument(
        "positional_package",
        nargs="?",
        type=str,
        metavar="PACKAGE_NAME",
        help="Positional package name (optional)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_cli_args(argv)

    repo_path = args.repo or args.positional_repo or Path(".")
    package_name = args.package or args.positional_package or "requests"

    repo_resolved = repo_path.resolve()
    if not repo_resolved.exists():
        print(f"[error] Repository path does not exist: {repo_resolved}", file=sys.stderr)
        return 1

    print(f"=== Usages Analysis for '{package_name}' in {repo_resolved} ===")
    analysis = analyze_usages(repo_resolved, package_name)

    print(f"Mapped Import Names : {analysis.import_names}")
    print(f"Locations Found     : {len(analysis.locations)}")
    print(f"Summary             : {analysis.summary}")
    print()

    if analysis.locations:
        print("--- Python Usages ---")
        for loc in analysis.locations:
            print(f"[{loc.file}:{loc.line}]")
            for line in loc.snippet.splitlines():
                print(f"  | {line}")
            print()

    if analysis.non_python_mentions:
        print("--- Non-Python Mentions ---")
        for npm in analysis.non_python_mentions:
            print(f"- {npm.file}:{npm.line} -> {npm.snippet}")
        print()

    if analysis.limitations:
        print("--- Limitations / Parse Errors ---")
        for lim in analysis.limitations:
            print(f"- {lim}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
