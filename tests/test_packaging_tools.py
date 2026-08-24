"""Unit checks for downstream provenance, archive, and publication safety."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

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
build_wheel = _load_script("build_wheel")
update_version = _load_script("update_version")


def test_upstream_manifest_matches_source_and_runtime() -> None:
    pin = verify_upstream.load_pin()

    assert pin.commit == "542fefb3b94be87760b2513fff889b91bb5b6672"
    assert pin.sdk_version == "0.2.143"
    assert pin.bundled_cli_version == "2.1.241"
    verify_upstream.verify_repository(PROJECT_ROOT, pin, require_runtime_unchanged=True)


def test_archive_member_safety_rejects_traversal_and_absolute_paths() -> None:
    assert reproducible_build._safe_member(
        "ink_claude_dream_agent_sdk-0.2.143/src/claude_agent_sdk/__init__.py"
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
        ".github/workflows/publish.yml": 4,
        ".github/workflows/pypi-quota-check.yml": 1,
    }

    for relative_path, required_count in required_guard_counts.items():
        workflow = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert workflow.count(guard) >= required_count, relative_path


def test_portable_workflow_cannot_publish() -> None:
    workflow = (
        PROJECT_ROOT / ".github/workflows/portable-package-check.yml"
    ).read_text(encoding="utf-8")

    assert "permissions:\n  contents: read" in workflow
    assert "scripts/reproducible_build.py" in workflow
    assert "ink_claude_dream_agent_sdk-${version}-py3-none-any.whl" in workflow
    for forbidden in (
        "twine upload",
        "pypa/gh-action-pypi-publish",
        "actions/upload-artifact",
        "contents: write",
        "git push",
        "gh release",
    ):
        assert forbidden not in workflow


def test_distribution_name_and_default_build_exclude_vendor_cli() -> None:
    tomllib = pytest.importorskip("tomllib")
    config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())

    assert config["project"]["name"] == "ink-claude-dream-agent-sdk"
    assert config["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == [
        "src/claude_agent_sdk"
    ]
    expected = {
        "src/claude_agent_sdk/_bundled/claude",
        "src/claude_agent_sdk/_bundled/claude.exe",
    }
    wheel_excludes = set(
        config["tool"]["hatch"]["build"]["targets"]["wheel"]["exclude"]
    )
    sdist_excludes = {
        value.removeprefix("/")
        for value in config["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"]
    }
    assert expected <= wheel_excludes
    assert expected <= sdist_excludes


def test_vendor_builder_refuses_the_downstream_distribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(PROJECT_ROOT)
    try:
        build_wheel.require_official_distribution()
    except SystemExit as exc:
        assert "vendor wheel build refused" in str(exc)
        assert "ink-claude-dream-agent-sdk" in str(exc)
    else:
        raise AssertionError("downstream vendor build was not refused")


def test_version_updater_preserves_the_downstream_name_and_import_namespace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "ink-claude-dream-agent-sdk"\nversion = "0.2.143"\n'
    )
    import_version = tmp_path / "src/claude_agent_sdk/_version.py"
    import_version.parent.mkdir(parents=True)
    import_version.write_text('__version__ = "0.2.143"\n')
    monkeypatch.chdir(tmp_path)

    update_version.update_version("0.2.144")

    assert 'name = "ink-claude-dream-agent-sdk"' in pyproject.read_text()
    assert 'version = "0.2.144"' in pyproject.read_text()
    assert import_version.read_text() == '__version__ = "0.2.144"\n'


def test_version_updater_rejects_invalid_version_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    original = '[project]\nname = "ink-claude-dream-agent-sdk"\nversion = "0.2.143"\n'
    pyproject.write_text(original)
    import_version = tmp_path / "src/claude_agent_sdk/_version.py"
    import_version.parent.mkdir(parents=True)
    import_version.write_text('__version__ = "0.2.143"\n')
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="invalid SDK version"):
        update_version.update_version('0.2.144"; broken')

    assert pyproject.read_text() == original
    assert import_version.read_text() == '__version__ = "0.2.143"\n'
