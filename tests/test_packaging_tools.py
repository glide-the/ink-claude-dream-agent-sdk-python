"""Unit checks for downstream provenance, archive, and publication safety."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str) -> ModuleType:
    path = PROJECT_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


verify_upstream = _load_script("verify_upstream")
reproducible_build = _load_script("reproducible_build")


def test_upstream_manifest_matches_source_and_runtime() -> None:
    pin = verify_upstream.load_pin()

    assert pin.commit == "542fefb3b94be87760b2513fff889b91bb5b6672"
    assert pin.sdk_version == "0.2.143"
    assert pin.bundled_cli_version == "2.1.241"
    verify_upstream.verify_repository(PROJECT_ROOT, pin, require_runtime_unchanged=True)


def test_archive_member_safety_rejects_traversal_and_absolute_paths() -> None:
    assert reproducible_build._safe_member(
        "claude_agent_sdk-0.2.143/src/claude_agent_sdk/__init__.py"
    )
    assert not reproducible_build._safe_member("../outside")
    assert not reproducible_build._safe_member("root/../../outside")
    assert not reproducible_build._safe_member("/absolute/path")


def test_vendor_build_and_release_workflows_are_official_repo_only() -> None:
    guard = "github.repository == 'anthropics/claude-agent-sdk-python'"
    required_guard_counts = {
        ".github/workflows/auto-release.yml": 2,
        ".github/workflows/build-and-publish.yml": 2,
        ".github/workflows/build-wheel-check.yml": 1,
        ".github/workflows/publish.yml": 1,
    }

    for relative_path, required_count in required_guard_counts.items():
        workflow = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert workflow.count(guard) >= required_count, relative_path
