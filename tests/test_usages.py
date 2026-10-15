"""test_usages.py – Unit and integration tests for exitcapsule/usages.py."""

from pathlib import Path

import pytest

from exitcapsule.schema import UsageLocation
from exitcapsule.usages import (
    UsageAnalysis,
    UsageList,
    analyze_usages,
    find_non_python_mentions,
    find_usages,
    get_import_names,
    main,
)


def test_get_import_names() -> None:
    """Verify PyPI distribution mapping via override table and heuristics."""
    assert "dateutil" in get_import_names("python-dateutil")
    assert "bs4" in get_import_names("beautifulsoup4")
    assert "PIL" in get_import_names("pillow")
    assert "yaml" in get_import_names("pyyaml")
    assert "sklearn" in get_import_names("scikit-learn")
    assert "requests" in get_import_names("requests")
    # Normalized name heuristics fallback
    custom_names = get_import_names("my-custom-package")
    assert any("my_custom_package" in name for name in custom_names)


def test_fixture_project(tmp_path: Path) -> None:
    """Test AST usages, aliasing, call sites, context snippets, non-py files, and limitations."""
    # Create project layout
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    venv_dir = tmp_path / ".venv" / "lib"
    venv_dir.mkdir(parents=True)

    # 1. Main python file with various import styles and usages
    main_py = src_dir / "main.py"
    main_py.write_text(
        "\n".join([
            "# File header comment",
            "import os",
            "import demo_pkg",
            "import demo_pkg as dp",
            "from demo_pkg import Client as MyClient, execute",
            "",
            "def run_pipeline():",
            "    client = MyClient(api_key='test')",
            "    client.fetch_data('param')",
            "    res = dp.quick_call()",
            "    val = demo_pkg.DEFAULT_TIMEOUT",
            "    execute(res)",
            "    return val",
        ]),
        encoding="utf-8",
    )

    # 2. Broken python file to test limitation capture
    broken_py = src_dir / "broken.py"
    broken_py.write_text("def unclosed_function(:\n    pass", encoding="utf-8")

    # 3. File in skipped venv directory (should NOT be detected)
    skipped_py = venv_dir / "skip_me.py"
    skipped_py.write_text("import demo_pkg\ndemo_pkg.bad()", encoding="utf-8")

    # 4. Non-Python manifest files
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("demo-pkg>=2.0.0\nother-lib==1.0\n", encoding="utf-8")

    docker_file = tmp_path / "Dockerfile"
    docker_file.write_text("FROM python:3.12\nRUN pip install demo-pkg\n", encoding="utf-8")

    # Perform analysis
    analysis = analyze_usages(tmp_path, "demo-pkg")

    # Verify locations in main.py
    files_found = {loc.file for loc in analysis.locations}
    assert "src/main.py" in files_found
    # Ensure .venv was skipped
    assert not any(".venv" in f for f in files_found)

    # Verify line numbers and 2 lines of context in snippet
    lines_found = {loc.line for loc in analysis.locations}
    # Imports
    assert 3 in lines_found  # import demo_pkg
    assert 4 in lines_found  # import demo_pkg as dp
    assert 5 in lines_found  # from demo_pkg import Client as MyClient, execute
    # Usages / Calls
    assert 8 in lines_found  # client = MyClient(...)
    assert 9 in lines_found  # client.fetch_data(...)
    assert 10 in lines_found # dp.quick_call()
    assert 11 in lines_found # demo_pkg.DEFAULT_TIMEOUT
    assert 12 in lines_found # execute(res)

    # Check 2 lines of context in snippet for line 8
    loc_8 = next(loc for loc in analysis.locations if loc.line == 8)
    snippet_lines = loc_8.snippet.splitlines()
    # Line 8 context should span lines 6 to 10
    assert any("def run_pipeline():" in sl for sl in snippet_lines)
    assert any("MyClient(api_key='test')" in sl for sl in snippet_lines)
    assert any("client.fetch_data('param')" in sl for sl in snippet_lines)

    # Verify used symbols
    assert "MyClient" in analysis.used_symbols or "Client" in analysis.used_symbols
    assert "execute" in analysis.used_symbols
    assert "quick_call" in analysis.used_symbols

    # Verify non-python mentions
    non_py_files = {npm.file for npm in analysis.non_python_mentions}
    assert "requirements.txt" in non_py_files
    assert "Dockerfile" in non_py_files

    # Verify limitation recorded for broken.py
    assert len(analysis.limitations) >= 1
    assert any("broken.py" in lim for lim in analysis.limitations)

    # Test find_usages signature and return type
    res = find_usages(tmp_path, "demo-pkg")
    assert isinstance(res, list)
    assert isinstance(res, UsageList)
    assert len(res) == len(analysis.locations)
    assert res.summary == analysis.summary
    assert len(res.non_python_mentions) == 2


def test_edge_cases(tmp_path: Path) -> None:
    """Test edge cases like nested imports, multiple imports per line, and unused packages."""
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()

    # Nested imports and multiple imports per line
    sample_file = pkg_dir / "edge.py"
    sample_file.write_text(
        "\n".join([
            "import alpha, beta, gamma",
            "from alpha.sub.deep import deeply_nested",
            "val = deeply_nested()",
        ]),
        encoding="utf-8",
    )

    analysis_alpha = analyze_usages(tmp_path, "alpha")
    assert len(analysis_alpha.locations) == 3
    assert "deeply_nested" in analysis_alpha.used_symbols

    # Test unused package
    analysis_unused = analyze_usages(tmp_path, "nonexistent-pkg")
    assert len(analysis_unused.locations) == 0
    assert "No specific functions or classes detected" in analysis_unused.summary


def test_cli_entry_point(capsys: pytest.CaptureFixture[str]) -> None:
    """Test the CLI entry point main() execution with --help and arguments."""
    repo = Path("target/LinkWatch").resolve()
    if not repo.exists():
        pytest.skip("target/LinkWatch not found")

    exit_code = main(["--repo", str(repo), "--package", "requests"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Usages Analysis for 'requests'" in captured.out
    assert "linkwatch/checker.py" in captured.out
    assert "requirements.txt" in captured.out


def test_linkwatch_requests() -> None:
    """Integration test: analyze 'requests' against the real ./target/LinkWatch repo."""
    repo = Path("target/LinkWatch").resolve()
    if not repo.exists():
        pytest.skip("target/LinkWatch not found at relative path")

    analysis = analyze_usages(repo, "requests")

    # Should find usages across checker.py, encoding.py, and http_patch.py
    files_found = {loc.file for loc in analysis.locations}
    assert "linkwatch/checker.py" in files_found
    assert "linkwatch/encoding.py" in files_found
    assert "linkwatch/http_patch.py" in files_found
    assert len(analysis.locations) >= 10

    # Verify used symbols summary
    assert "Session" in analysis.used_symbols
    assert "get" in analysis.used_symbols or "Session.get" in analysis.used_symbols
    assert any("Timeout" in s for s in analysis.used_symbols)
    assert any("ConnectionError" in s for s in analysis.used_symbols)

    # Verify non-Python files
    non_py = {npm.file for npm in analysis.non_python_mentions}
    assert "requirements.txt" in non_py
    assert "pyproject.toml" in non_py

    # Verify find_usages
    locations = find_usages(repo, "requests")
    assert all(isinstance(loc, UsageLocation) for loc in locations)


def test_linkwatch_dateutil() -> None:
    """Integration test: analyze 'python-dateutil' in ./target/LinkWatch."""
    repo = Path("target/LinkWatch").resolve()
    if not repo.exists():
        pytest.skip("target/LinkWatch not found")

    analysis = analyze_usages(repo, "python-dateutil")
    assert analysis.import_names == ["dateutil"]

    files_found = {loc.file for loc in analysis.locations}
    assert "linkwatch/dates.py" in files_found
    assert any("parse" in s for s in analysis.used_symbols)

    non_py = {npm.file for npm in analysis.non_python_mentions}
    assert "requirements.txt" in non_py
