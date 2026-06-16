"""
Regression tests for the pydantic-views mypy plugin (``pydantic_views.mypy``).

These drive mypy over the files in ``examples/`` and assert that:

* the positive assertions in ``check_views.py`` type-check cleanly,
* every expected error in ``check_errors.py`` still fires (``warn_unused_ignores`` turns a missing
  error into a failure), and
* the field set the plugin synthesises for each view equals the runtime builder's ``model_fields``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
CONFIG = EXAMPLES / "mypy.ini"

pytestmark = pytest.mark.skipif(not CONFIG.exists(), reason="examples not available")


def _run_mypy(*targets: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "mypy", "--no-incremental", "--config-file", str(CONFIG), *targets],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_positive_assertions_type_check_clean():
    result = _run_mypy(str(EXAMPLES / "check_views.py"))
    assert "Success" in result.stdout, result.stdout + result.stderr


def test_expected_errors_all_fire():
    # warn_unused_ignores=true means a missing plugin error becomes an "unused ignore" failure.
    result = _run_mypy(str(EXAMPLES / "check_errors.py"))
    assert "Success" in result.stdout, result.stdout + result.stderr


def test_plugin_field_sets_match_runtime_builder():
    sys.path.insert(0, str(EXAMPLES))
    try:
        import generate_stubs  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)

    result = generate_stubs.build_with_plugin()
    tree = result.graph[generate_stubs.MODULE].tree
    assert tree is not None

    runtime_views = generate_stubs.collect_runtime_views()
    plugin_views = generate_stubs.collect_plugin_views(tree)

    # Top-level views and the auto-synthesised nested views must all be present.
    assert set(plugin_views) >= set(generate_stubs.VIEW_NAMES)
    assert {"AddressLoad", "RoleLoad", "AddressCreate", "RoleCreateResult"} <= set(plugin_views)

    for name, info in plugin_views.items():
        _, plugin_fields = generate_stubs.stub_for_view(info)
        assert name in runtime_views, f"{name} not built at runtime"
        assert set(plugin_fields) == runtime_views[name], f"{name}: {set(plugin_fields)} != {runtime_views[name]}"
