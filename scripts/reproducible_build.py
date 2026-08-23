#!/usr/bin/env python3
"""Build and byte-compare portable Claude Agent SDK wheel/sdist artifacts.

This flow intentionally does not download or bundle Claude Code. It produces a
portable SDK wheel for runtime images that supply an official or explicitly
selected CLI. The official platform-wheel builder remains scripts/build_wheel.py.
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import NoReturn

import verify_upstream

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "dist" / "reproducible"


def fail(message: str) -> NoReturn:
    """Stop with an actionable build error."""
    raise SystemExit(f"reproducible build failed: {message}")


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    """Run one builder command without a shell."""
    print(f"$ {' '.join(command)}")
    result = subprocess.run(command, cwd=cwd, env=env, check=False)
    if result.returncode != 0:
        fail(f"command exited {result.returncode}: {' '.join(command)}")


def sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_inventory() -> list[Path]:
    """List tracked plus non-ignored untracked inputs in stable byte order."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(PROJECT_ROOT),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        fail(f"git ls-files exited {result.returncode}")
    paths = sorted(
        (Path(os.fsdecode(raw)) for raw in result.stdout.split(b"\0") if raw),
        key=os.fspath,
    )
    for path in paths:
        if path.is_absolute() or ".." in path.parts:
            fail(f"unsafe Git inventory path: {path}")
    return paths


def _copy_snapshot(destination: Path, epoch: int) -> None:
    """Copy only declared Git inputs and normalize their times."""
    for relative in _git_inventory():
        source = PROJECT_ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            target.symlink_to(source.readlink())
            os.utime(target, (epoch, epoch), follow_symlinks=False)
            continue
        if not source.is_file():
            fail(f"inventory entry is not a file: {relative}")
        shutil.copyfile(source, target)
        target.chmod(source.stat().st_mode & 0o7777)
        os.utime(target, (epoch, epoch))

    directories = sorted(
        (path for path in destination.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        os.utime(directory, (epoch, epoch))
    os.utime(destination, (epoch, epoch))


def _safe_member(name: str) -> bool:
    """Return whether an archive member stays within its archive root."""
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts


def _verify_wheel(path: Path, version: str) -> None:
    """Check the portable wheel shape and absence of a bundled executable."""
    if not path.name.endswith("-py3-none-any.whl"):
        fail(f"portable wheel has unexpected platform tag: {path.name}")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if any(not _safe_member(name) for name in names):
            fail(f"wheel contains an unsafe path: {path.name}")
        if "claude_agent_sdk/__init__.py" not in names:
            fail("wheel does not contain claude_agent_sdk/__init__.py")
        if any(
            name.endswith("/_bundled/claude") or name.endswith("/_bundled/claude.exe")
            for name in names
        ):
            fail("portable wheel unexpectedly contains a Claude CLI executable")
        metadata_names = [
            name for name in names if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_names) != 1:
            fail("wheel must contain exactly one METADATA file")
        metadata = archive.read(metadata_names[0]).decode("utf-8")
        if f"\nVersion: {version}\n" not in f"\n{metadata}":
            fail(f"wheel METADATA version is not {version}")


def _verify_sdist(path: Path) -> None:
    """Check source provenance and tooling are present in the sdist."""
    with tarfile.open(path, "r:gz") as archive:
        names = archive.getnames()
        if any(not _safe_member(name) for name in names):
            fail(f"sdist contains an unsafe path: {path.name}")
        required_suffixes = {
            "/docs/packaging/README.md",
            "/docs/packaging/runtime-integration.md",
            "/packaging/upstream.json",
            "/packaging/build-requirements.lock",
            "/packaging/README.md",
            "/scripts/check_upstream_sync.py",
            "/scripts/reproducible_build.py",
            "/scripts/smoke_installed.py",
            "/scripts/verify_upstream.py",
        }
        missing = {
            suffix
            for suffix in required_suffixes
            if not any(name.endswith(suffix) for name in names)
        }
        if missing:
            fail(f"sdist is missing required files: {sorted(missing)}")


def _build_once(
    python: Path, epoch: int, version: str, work_root: Path, sequence: int
) -> dict[str, Path]:
    """Build one normalized source snapshot and validate its artifacts."""
    snapshot = work_root / f"source-{sequence}"
    output = work_root / f"artifacts-{sequence}"
    snapshot.mkdir()
    output.mkdir()
    _copy_snapshot(snapshot, epoch)

    env = {
        **os.environ,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONHASHSEED": "0",
        "SOURCE_DATE_EPOCH": str(epoch),
        "TZ": "UTC",
    }
    run(
        [
            str(python),
            "-m",
            "build",
            "--no-isolation",
            "--sdist",
            "--wheel",
            "--outdir",
            str(output),
            str(snapshot),
        ],
        cwd=snapshot,
        env=env,
    )
    artifacts = {path.name: path for path in sorted(output.iterdir()) if path.is_file()}
    wheels = [path for path in artifacts.values() if path.suffix == ".whl"]
    sdists = [path for path in artifacts.values() if path.name.endswith(".tar.gz")]
    if len(wheels) != 1 or len(sdists) != 1 or len(artifacts) != 2:
        fail(f"expected one wheel and one sdist, found {sorted(artifacts)}")
    _verify_wheel(wheels[0], version)
    _verify_sdist(sdists[0])
    return artifacts


def _publish(artifacts: dict[str, Path], output: Path) -> None:
    """Copy verified artifacts without replacing different existing files."""
    output.mkdir(parents=True, exist_ok=True)
    checksum_lines: list[str] = []
    for name, source in sorted(artifacts.items()):
        digest = sha256(source)
        target = output / name
        if target.exists():
            if not target.is_file() or sha256(target) != digest:
                fail(f"refusing to replace different existing artifact: {target}")
        else:
            shutil.copyfile(source, target)
        checksum_lines.append(f"{digest}  {name}\n")
        print(f"artifact={target} bytes={target.stat().st_size} sha256={digest}")

    checksum_text = "".join(checksum_lines)
    checksum_path = output / "SHA256SUMS"
    if checksum_path.exists():
        if checksum_path.read_text(encoding="utf-8") != checksum_text:
            fail(f"refusing to replace different checksum file: {checksum_path}")
    else:
        checksum_path.write_text(checksum_text, encoding="utf-8")
    print(f"checksums={checksum_path}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python with the hash-locked build toolchain installed",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT, help="verified output"
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="include uncommitted, non-ignored inputs (local verification only)",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=2,
        help="independent builds to compare (minimum 2)",
    )
    args = parser.parse_args()

    if args.repetitions < 2:
        fail("--repetitions must be at least 2")
    if not args.python.is_file():
        fail(f"builder Python does not exist: {args.python}")
    if not args.allow_dirty:
        status = subprocess.run(
            [
                "git",
                "-C",
                str(PROJECT_ROOT),
                "status",
                "--porcelain",
                "--untracked-files=all",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if status.returncode != 0:
            fail(f"git status exited {status.returncode}")
        if status.stdout:
            fail("working tree is dirty; commit/review inputs or pass --allow-dirty")

    bundled = PROJECT_ROOT / "src" / "claude_agent_sdk" / "_bundled"
    executables = [
        path for path in bundled.glob("claude*") if path.name != ".gitignore"
    ]
    if executables:
        fail(f"portable build input contains bundled CLI files: {executables}")

    pin = verify_upstream.load_pin()
    verify_upstream.verify_repository(PROJECT_ROOT, pin, require_runtime_unchanged=True)
    print(f"source_date_epoch={pin.source_date_epoch}")

    with tempfile.TemporaryDirectory(prefix="claude-sdk-repro-") as temp:
        work_root = Path(temp)
        builds = [
            _build_once(
                args.python.absolute(),
                pin.source_date_epoch,
                pin.sdk_version,
                work_root,
                sequence,
            )
            for sequence in range(1, args.repetitions + 1)
        ]
        expected = {name: sha256(path) for name, path in builds[0].items()}
        for sequence, artifacts in enumerate(builds[1:], start=2):
            actual = {name: sha256(path) for name, path in artifacts.items()}
            if actual != expected:
                fail(f"build {sequence} digest mismatch: {actual} != {expected}")
        print(f"reproducible_builds={args.repetitions}")
        _publish(builds[0], args.output_dir.resolve())


if __name__ == "__main__":
    main()
