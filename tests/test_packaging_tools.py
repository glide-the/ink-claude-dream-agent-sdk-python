"""Unit checks for downstream provenance, archive, and publication safety."""

import importlib.util
import io
import json
import re
import sys
import tarfile
import zipfile
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
verify_package_index_release = _load_script("verify_package_index_release")
build_wheel = _load_script("build_wheel")
update_version = _load_script("update_version")


def test_upstream_manifest_matches_source_and_runtime() -> None:
    pin = verify_upstream.load_pin()

    assert pin.commit == "542fefb3b94be87760b2513fff889b91bb5b6672"
    assert pin.sdk_version == "0.2.143"
    assert pin.downstream_version == "0.2.144"
    assert pin.bundled_cli_version == "2.1.241"
    verify_upstream.verify_repository(PROJECT_ROOT, pin, require_runtime_unchanged=True)


def test_reproducible_build_uses_declared_downstream_version() -> None:
    source = (PROJECT_ROOT / "scripts/reproducible_build.py").read_text(
        encoding="utf-8"
    )
    assert "pin.downstream_version" in source
    assert "pin.sdk_version," not in source


def test_archive_member_safety_rejects_traversal_and_absolute_paths() -> None:
    assert reproducible_build._safe_member(
        "ink_claude_dream_agent_sdk-0.2.143/src/claude_agent_sdk/__init__.py"
    )
    assert not reproducible_build._safe_member("../outside")
    assert not reproducible_build._safe_member("root/../../outside")
    assert not reproducible_build._safe_member("/absolute/path")


def test_archive_member_safety_rejects_every_source_map() -> None:
    assert reproducible_build._contains_source_map(["src/runtime.js.map"])
    assert reproducible_build._contains_source_map(["bundle.map"])
    assert not reproducible_build._contains_source_map(["map", "runtime.js"])


def test_wheel_and_sdist_verifiers_reject_source_maps(tmp_path: Path) -> None:
    wheel = tmp_path / "ink_claude_dream_agent_sdk-0.2.143-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("claude_agent_sdk/runtime.js.map", "{}")
    with pytest.raises(SystemExit, match=r"\*\.map"):
        reproducible_build._verify_wheel(wheel, "0.2.143")

    sdist = tmp_path / "ink_claude_dream_agent_sdk-0.2.143.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        payload = b"{}"
        member = tarfile.TarInfo(
            "ink_claude_dream_agent_sdk-0.2.143/src/runtime.js.map"
        )
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
    with pytest.raises(SystemExit, match=r"\*\.map"):
        reproducible_build._verify_sdist(sdist, "0.2.143")


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


def test_downstream_publish_workflow_is_portable_oidc_only() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/publish-portable.yml").read_text(
        encoding="utf-8"
    )

    assert (
        "github.repository == 'glide-the/ink-claude-dream-agent-sdk-python'" in workflow
    )
    assert "python scripts/reproducible_build.py" in workflow
    assert "twine==7.0.0" in workflow
    assert "runs-on: ubuntu-24.04" in workflow
    assert "python-version: '3.12.x'" in workflow
    assert "-m twine check --strict" in workflow
    assert "python scripts/smoke_installed.py" in workflow
    assert "python scripts/verify_package_index_release.py" in workflow
    assert "environment:\n      name: testpypi" in workflow
    assert "environment:\n      name: pypi" in workflow
    assert workflow.count("id-token: write") == 2
    assert workflow.count("pypa/gh-action-pypi-publish@") == 2
    assert workflow.count("skip-existing: false") == 2
    assert workflow.count("attestations: true") == 2
    assert "repository-url: https://test.pypi.org/legacy/" in workflow
    assert "source_ref:" in workflow
    assert "Immutable reviewed source tag, exactly v<version>" in workflow
    assert workflow.count("ref: ${{ inputs.source_ref }}") == 3
    assert 'test "$SOURCE_REF" = "v$RELEASE_VERSION"' in workflow
    assert 'test "$GITHUB_REF_TYPE" = "tag"' in workflow
    assert 'git rev-parse "$SOURCE_REF^{commit}"' in workflow
    assert 'test "$checked_out_commit" = "$source_commit"' in workflow
    assert 'runner_suffix=${GITHUB_REF_NAME#"$SOURCE_REF-publish."}' in workflow
    assert "sha256sum --check SHA256SUMS" in workflow
    assert "needs: publish-testpypi" in workflow
    assert "needs: verify-testpypi" in workflow
    assert "inputs.target" not in workflow
    assert "*.map" in workflow
    assert workflow.index("Final archive verification") < workflow.index(
        "Stage the final verified bytes read-only"
    )
    assert "smoke-installed:" in workflow
    assert "needs: [build-and-verify, smoke-installed]" in workflow
    assert workflow.index("Transfer the reviewed bytes to the promotion jobs") < (
        workflow.index("smoke-installed:")
    )
    assert workflow.index("smoke-installed:") < workflow.index("publish-testpypi:")
    assert workflow.index("publish-testpypi:") < workflow.index("verify-testpypi:")
    assert workflow.index("verify-testpypi:") < workflow.index("publish-pypi:")
    for forbidden in (
        "scripts/build_wheel.py",
        "scripts/download_cli.py",
        "PYPI_API_TOKEN",
        "TWINE_PASSWORD",
        "secrets:",
        "contents: write",
        "git push",
        "gh release",
    ):
        assert forbidden not in workflow


def test_publish_workflow_version_parser_accepts_module_docstring() -> None:
    version_source = (PROJECT_ROOT / "src/claude_agent_sdk/_version.py").read_text(
        encoding="utf-8"
    )
    matches = re.findall(r'^__version__ = "([^"]+)"$', version_source, re.MULTILINE)
    assert matches == ["0.2.144"]

    workflow = (PROJECT_ROOT / ".github/workflows/publish-portable.yml").read_text(
        encoding="utf-8"
    )
    assert "matches = re.findall(" in workflow
    assert "if len(matches) != 1:" in workflow
    assert "re.fullmatch(r'__version__" not in workflow


def test_package_index_promotion_inventory_rejects_source_maps(tmp_path: Path) -> None:
    (tmp_path / "runtime.js.map").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match=r"\*\.map"):
        verify_package_index_release.load_expected(tmp_path, "0.2.143")


def test_package_index_promotion_receipt_requires_exact_remote_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    version = "0.2.143"
    wheel_name = f"ink_claude_dream_agent_sdk-{version}-py3-none-any.whl"
    sdist_name = f"ink_claude_dream_agent_sdk-{version}.tar.gz"
    expected: dict[str, str] = {}
    for name, payload in ((wheel_name, b"wheel"), (sdist_name, b"sdist")):
        path = tmp_path / name
        path.write_bytes(payload)
        expected[name] = verify_package_index_release.sha256(path)
    (tmp_path / "SHA256SUMS").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(expected.items())),
        encoding="utf-8",
    )
    assert verify_package_index_release.load_expected(tmp_path, version) == expected

    payload = {
        "urls": [
            {
                "filename": name,
                "digests": {"sha256": digest},
                "url": f"https://test-files.pythonhosted.org/{name}",
            }
            for name, digest in sorted(expected.items())
        ]
    }
    monkeypatch.setattr(
        verify_package_index_release.urllib.request,
        "urlopen",
        lambda *args, **kwargs: io.BytesIO(json.dumps(payload).encode()),
    )
    monkeypatch.setattr(
        verify_package_index_release,
        "_download_digest",
        lambda url, timeout: expected[url.rsplit("/", 1)[-1]],
    )

    receipt = verify_package_index_release.verify_once(
        index_json_base="https://test.pypi.org/pypi",
        version=version,
        expected=expected,
        timeout=1,
    )
    assert receipt == expected


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
    assert "**/*.map" in wheel_excludes
    assert "**/*.map" in sdist_excludes


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
