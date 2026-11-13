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
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
DATA_MYPI = ROOT / "data" / "mypi"
CONFIG = DATA_MYPI / "mypy.ini"

pytestmark = pytest.mark.skipif(not CONFIG.exists(), reason="examples not available")


def _run_mypy(*targets: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--no-incremental",
            "--config-file",
            str(CONFIG),
            *targets,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_positive_assertions_type_check_clean():
    result = _run_mypy(str(DATA_MYPI / "check_views.py"))
    assert "Success" in result.stdout, result.stdout + result.stderr


def test_expected_errors_all_fire():
    # warn_unused_ignores=true means a missing plugin error becomes an "unused ignore" failure.
    result = _run_mypy(str(DATA_MYPI / "check_errors.py"))
    assert "Success" in result.stdout, result.stdout + result.stderr


def test_generated_stubs_type_check_without_transforming_views(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from pydantic_views.stubgen import generate

    source = (
        "from pydantic import BaseModel\n"
        "from pydantic_views import View, LoadPreset, WriteOnly\n"
        "class Metadata(BaseModel):\n"
        "    name: str\n"
        "    secret: WriteOnly[str]\n"
        "class MetadataLoad(View[Metadata], preset=LoadPreset):\n"
        "    pass\n"
    )
    path = tmp_path / "stub_plugin_models.py"
    path.write_text(source)
    module = types.ModuleType("stub_plugin_models")
    module.__file__ = str(path)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    exec(compile(source, str(path), "exec"), module.__dict__)
    stub_path = generate(module)
    consumer = tmp_path / "consumer.py"
    consumer.write_text(
        "from stub_plugin_models import MetadataLoad\n"
        "view = MetadataLoad(name='example')\n"
        "MetadataLoad()  # type: ignore[call-arg]\n"
        "MetadataLoad(name=123)  # type: ignore[arg-type]\n"
        "MetadataLoad(name='example', secret='hidden')  # type: ignore[call-arg]\n"
        "view.secret  # type: ignore[attr-defined]\n"
    )

    result = _run_mypy(str(stub_path), str(consumer))
    assert result.returncode == 0, result.stdout + result.stderr


def test_plugin_field_sets_match_runtime_builder():
    sys.path.insert(0, str(DATA_MYPI))
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
