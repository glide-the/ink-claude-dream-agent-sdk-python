#!/usr/bin/env python3
"""Verify the downstream tree against its exact Claude Agent SDK provenance.

The check is read-only. It verifies that the recorded upstream commit is in
the current history, that runtime source still matches that commit, and that
the SDK/CLI version pins agree across the manifest and source files. An
optional local reference repository can be checked without modifying it.
"""

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "packaging" / "upstream.json"
HEX_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
SEMVER_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
UPSTREAM_DISTRIBUTION_NAME = "claude-agent-sdk"
DOWNSTREAM_DISTRIBUTION_NAME = "ink-claude-dream-agent-sdk"


@dataclass(frozen=True)
class UpstreamPin:
    """Validated fields from packaging/upstream.json."""

    schema_version: int
    repository: str
    ref: str
    commit: str
    tree: str
    source_date_epoch: int
    sdk_version: str
    bundled_cli_version: str
    license: str


def fail(message: str) -> NoReturn:
    """Stop with one actionable provenance error."""
    raise SystemExit(f"upstream verification failed: {message}")


def _required(data: dict[str, Any], name: str, expected: type[Any]) -> Any:
    value = data.get(name)
    if not isinstance(value, expected):
        fail(f"manifest field {name!r} must be {expected.__name__}")
    return value


def load_pin(path: Path = DEFAULT_MANIFEST) -> UpstreamPin:
    """Read and validate an upstream provenance manifest."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read {path}: {exc}")
    if not isinstance(raw, dict):
        fail(f"{path} must contain one JSON object")

    schema_version = _required(raw, "schema_version", int)
    repository = _required(raw, "repository", str)
    ref = _required(raw, "ref", str)
    commit = _required(raw, "commit", str)
    tree = _required(raw, "tree", str)
    source_date_epoch = _required(raw, "source_date_epoch", int)
    sdk_version = _required(raw, "sdk_version", str)
    cli_version = _required(raw, "bundled_cli_version", str)
    license_name = _required(raw, "license", str)

    if schema_version != 1:
        fail(f"unsupported manifest schema {schema_version!r}")
    if not repository.startswith("https://github.com/") or not repository.endswith(
        ".git"
    ):
        fail("repository must be an explicit GitHub HTTPS .git URL")
    if not ref.startswith("refs/heads/"):
        fail("ref must be a full refs/heads/* name")
    if HEX_SHA_RE.fullmatch(commit) is None:
        fail("commit must be a full lowercase SHA-1")
    if HEX_SHA_RE.fullmatch(tree) is None:
        fail("tree must be a full lowercase SHA-1")
    if source_date_epoch <= 0:
        fail("source_date_epoch must be positive")
    if SEMVER_RE.fullmatch(sdk_version) is None:
        fail("sdk_version must be a concrete semantic version")
    if SEMVER_RE.fullmatch(cli_version) is None:
        fail("bundled_cli_version must be a concrete semantic version")
    if license_name != "MIT":
        fail("license must remain MIT for this upstream baseline")

    return UpstreamPin(
        schema_version=schema_version,
        repository=repository,
        ref=ref,
        commit=commit,
        tree=tree,
        source_date_epoch=source_date_epoch,
        sdk_version=sdk_version,
        bundled_cli_version=cli_version,
        license=license_name,
    )


def git(
    repository: Path, *arguments: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run Git without a shell and capture only non-sensitive repository data."""
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        fail(f"git {' '.join(arguments)} exited {result.returncode}: {detail}")
    return result


def _extract_assignment(text: str, name: str, source: str) -> str:
    pattern = re.compile(rf'^{re.escape(name)} = "([^"]+)"$', re.MULTILINE)
    match = pattern.search(text)
    if match is None:
        fail(f"cannot find {name} in {source}")
    return match.group(1)


def _read_commit_file(repository: Path, commit: str, path: str) -> str:
    return git(repository, "show", f"{commit}:{path}").stdout


def verify_repository(
    repository: Path,
    pin: UpstreamPin,
    *,
    require_runtime_unchanged: bool,
) -> None:
    """Verify provenance and version consistency in one Git repository."""
    repository = repository.resolve()
    if git(repository, "cat-file", "-t", pin.commit).stdout.strip() != "commit":
        fail(f"{pin.commit} is not a commit in {repository}")

    actual_tree = git(
        repository, "show", "-s", "--format=%T", pin.commit
    ).stdout.strip()
    if actual_tree != pin.tree:
        fail(f"tree mismatch for {pin.commit}: {actual_tree} != {pin.tree}")
    actual_epoch = int(
        git(repository, "show", "-s", "--format=%ct", pin.commit).stdout.strip()
    )
    if actual_epoch != pin.source_date_epoch:
        fail(
            f"commit epoch mismatch for {pin.commit}: "
            f"{actual_epoch} != {pin.source_date_epoch}"
        )

    sdk_at_pin = _extract_assignment(
        _read_commit_file(repository, pin.commit, "src/claude_agent_sdk/_version.py"),
        "__version__",
        f"{pin.commit}:_version.py",
    )
    cli_at_pin = _extract_assignment(
        _read_commit_file(
            repository, pin.commit, "src/claude_agent_sdk/_cli_version.py"
        ),
        "__cli_version__",
        f"{pin.commit}:_cli_version.py",
    )
    pyproject_at_pin = _extract_assignment(
        _read_commit_file(repository, pin.commit, "pyproject.toml"),
        "version",
        f"{pin.commit}:pyproject.toml",
    )
    distribution_at_pin = _extract_assignment(
        _read_commit_file(repository, pin.commit, "pyproject.toml"),
        "name",
        f"{pin.commit}:pyproject.toml",
    )
    if sdk_at_pin != pin.sdk_version or pyproject_at_pin != pin.sdk_version:
        fail("SDK version in the pinned commit does not match upstream.json")
    if cli_at_pin != pin.bundled_cli_version:
        fail("CLI version in the pinned commit does not match upstream.json")
    if distribution_at_pin != UPSTREAM_DISTRIBUTION_NAME:
        fail(
            "distribution name in the pinned commit is not "
            f"{UPSTREAM_DISTRIBUTION_NAME}"
        )

    if require_runtime_unchanged:
        ancestor = git(
            repository,
            "merge-base",
            "--is-ancestor",
            pin.commit,
            "HEAD",
            check=False,
        )
        if ancestor.returncode != 0:
            fail(f"pinned upstream commit {pin.commit} is not an ancestor of HEAD")
        runtime_diff = git(
            repository, "diff", "--quiet", pin.commit, "--", "src", check=False
        )
        if runtime_diff.returncode != 0:
            fail("src/ differs from the pinned upstream commit")
        untracked_runtime = git(
            repository,
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            "src",
        ).stdout.splitlines()
        if untracked_runtime:
            fail(f"src/ contains untracked files: {untracked_runtime}")

        current_sdk = _extract_assignment(
            (repository / "src/claude_agent_sdk/_version.py").read_text(
                encoding="utf-8"
            ),
            "__version__",
            "working tree _version.py",
        )
        current_cli = _extract_assignment(
            (repository / "src/claude_agent_sdk/_cli_version.py").read_text(
                encoding="utf-8"
            ),
            "__cli_version__",
            "working tree _cli_version.py",
        )
        current_pyproject = _extract_assignment(
            (repository / "pyproject.toml").read_text(encoding="utf-8"),
            "version",
            "working tree pyproject.toml",
        )
        current_distribution = _extract_assignment(
            (repository / "pyproject.toml").read_text(encoding="utf-8"),
            "name",
            "working tree pyproject.toml",
        )
        if {current_sdk, current_pyproject} != {pin.sdk_version}:
            fail("working tree SDK versions do not match upstream.json")
        if current_cli != pin.bundled_cli_version:
            fail("working tree CLI version does not match upstream.json")
        if current_distribution != DOWNSTREAM_DISTRIBUTION_NAME:
            fail(
                f"working tree distribution name is not {DOWNSTREAM_DISTRIBUTION_NAME}"
            )

        license_digest = hashlib.sha256(
            (repository / "LICENSE").read_bytes()
        ).hexdigest()
        print(f"license={pin.license} sha256={license_digest}")


def check_remote_default(pin: UpstreamPin) -> None:
    """Check the advertised upstream default branch without fetching objects."""
    result = subprocess.run(
        ["git", "ls-remote", "--symref", pin.repository, "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail(f"git ls-remote exited {result.returncode}: {result.stderr.strip()}")
    advertised = f"ref: {pin.ref}\tHEAD"
    if advertised not in result.stdout.splitlines():
        fail(f"upstream does not advertise {pin.ref} as HEAD")
    print(f"remote_default={pin.ref}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=DEFAULT_MANIFEST, help="provenance JSON"
    )
    parser.add_argument(
        "--reference-repo",
        type=Path,
        help="optional read-only local upstream checkout to verify",
    )
    parser.add_argument(
        "--check-remote-default",
        action="store_true",
        help="query the upstream URL and verify its advertised HEAD",
    )
    args = parser.parse_args()

    pin = load_pin(args.manifest)
    verify_repository(PROJECT_ROOT, pin, require_runtime_unchanged=True)
    print(f"upstream_commit={pin.commit}")
    print(f"upstream_tree={pin.tree}")
    print(f"sdk_version={pin.sdk_version}")
    print(f"bundled_cli_version={pin.bundled_cli_version}")

    if args.reference_repo is not None:
        verify_repository(args.reference_repo, pin, require_runtime_unchanged=False)
        reference_head = git(args.reference_repo, "rev-parse", "HEAD").stdout.strip()
        if reference_head != pin.commit:
            fail(f"reference HEAD {reference_head} != pinned commit {pin.commit}")
        print(f"reference_repo={args.reference_repo.resolve()}")
    if args.check_remote_default:
        check_remote_default(pin)


if __name__ == "__main__":
    main()
