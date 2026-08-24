#!/usr/bin/env python3
"""Verify that a package-index release exactly matches reviewed local archives.

The promotion workflow uses this after TestPyPI upload. It compares the exact
filename set and SHA-256 values reported by the index, then downloads each
published file and hashes its bytes before PyPI approval can begin.
"""

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, NoReturn

DISTRIBUTION_NAME = "ink-claude-dream-agent-sdk"
DISTRIBUTION_STEM = "ink_claude_dream_agent_sdk"
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024


def fail(message: str) -> NoReturn:
    """Stop with an actionable promotion verification error."""
    raise SystemExit(f"package-index verification failed: {message}")


def sha256(path: Path) -> str:
    """Return the SHA-256 digest of a local file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_expected(artifacts_dir: Path, version: str) -> dict[str, str]:
    """Load and independently verify the exact two release archives."""
    artifacts_dir = artifacts_dir.resolve()
    expected_names = {
        f"{DISTRIBUTION_STEM}-{version}-py3-none-any.whl",
        f"{DISTRIBUTION_STEM}-{version}.tar.gz",
    }
    actual_names = {path.name for path in artifacts_dir.iterdir() if path.is_file()}
    if any(name.endswith(".map") for name in actual_names):
        fail("artifact inventory contains a *.map source map")
    if actual_names != expected_names | {"SHA256SUMS"}:
        fail(f"unexpected artifact inventory: {sorted(actual_names)}")

    checksums: dict[str, str] = {}
    for line in (artifacts_dir / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) != 2 or Path(parts[1]).name != parts[1]:
            fail("SHA256SUMS contains an invalid entry")
        digest, name = parts
        if len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            fail(f"SHA256SUMS contains an invalid digest for {name}")
        if name in checksums:
            fail(f"SHA256SUMS repeats {name}")
        checksums[name] = digest
    if set(checksums) != expected_names:
        fail(f"SHA256SUMS inventory mismatch: {sorted(checksums)}")
    for name, digest in checksums.items():
        if sha256(artifacts_dir / name) != digest:
            fail(f"local archive digest mismatch: {name}")
    return checksums


def _download_digest(url: str, timeout: float) -> str:
    """Download one HTTPS archive and return its SHA-256 digest."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"release file URL is not HTTPS: {url}")
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(url, timeout=timeout) as response:
        final_url = urllib.parse.urlparse(response.geturl())
        if final_url.scheme != "https" or not final_url.netloc:
            raise ValueError(
                f"release file redirected outside HTTPS: {response.geturl()}"
            )
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_ARCHIVE_BYTES:
                raise ValueError(f"release file exceeds {MAX_ARCHIVE_BYTES} bytes")
            digest.update(chunk)
    return digest.hexdigest()


def verify_once(
    *,
    index_json_base: str,
    version: str,
    expected: dict[str, str],
    timeout: float,
) -> dict[str, str]:
    """Verify one package-index JSON response and every referenced archive."""
    project = urllib.parse.quote(DISTRIBUTION_NAME, safe="")
    release = urllib.parse.quote(version, safe="")
    endpoint = f"{index_json_base.rstrip('/')}/{project}/{release}/json"
    if urllib.parse.urlparse(endpoint).scheme != "https":
        raise ValueError("package-index JSON endpoint must use HTTPS")
    with urllib.request.urlopen(endpoint, timeout=timeout) as response:
        payload: Any = json.load(response)
    urls = payload.get("urls") if isinstance(payload, dict) else None
    if not isinstance(urls, list):
        raise ValueError("package-index response has no urls list")

    remote: dict[str, dict[str, Any]] = {}
    for item in urls:
        if not isinstance(item, dict) or not isinstance(item.get("filename"), str):
            raise ValueError("package-index response contains an invalid file entry")
        name = item["filename"]
        if name.endswith(".map"):
            raise ValueError("package-index release contains a *.map source map")
        if name in remote:
            raise ValueError(f"package-index repeats filename {name}")
        remote[name] = item
    if set(remote) != set(expected):
        raise ValueError(f"package-index inventory mismatch: {sorted(remote)}")

    receipt: dict[str, str] = {}
    for name, expected_digest in sorted(expected.items()):
        item = remote[name]
        digests = item.get("digests")
        reported = digests.get("sha256") if isinstance(digests, dict) else None
        if reported != expected_digest:
            raise ValueError(f"package-index digest mismatch: {name}")
        url = item.get("url")
        if not isinstance(url, str):
            raise ValueError(f"package-index URL is missing: {name}")
        downloaded = _download_digest(url, timeout)
        if downloaded != expected_digest:
            raise ValueError(f"downloaded archive digest mismatch: {name}")
        receipt[name] = downloaded
    return receipt


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument(
        "--index-json-base",
        default="https://test.pypi.org/pypi",
        help="PEP 691-style project JSON base",
    )
    parser.add_argument("--attempts", type=int, default=12)
    parser.add_argument("--delay", type=float, default=5.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    if args.attempts < 1 or args.delay < 0 or args.timeout <= 0:
        fail("attempts, delay, and timeout values are invalid")

    expected = load_expected(args.artifacts_dir, args.version)
    last_error: Exception | None = None
    for attempt in range(1, args.attempts + 1):
        try:
            receipt = verify_once(
                index_json_base=args.index_json_base,
                version=args.version,
                expected=expected,
                timeout=args.timeout,
            )
        except Exception as error:  # Index propagation and downloads are transient.
            last_error = error
            print(f"verification_attempt={attempt} status=retry error={error}")
            if attempt < args.attempts:
                time.sleep(args.delay)
            continue
        print("promotion_receipt=" + json.dumps(receipt, sort_keys=True))
        print("testpypi_promotion_verified=true")
        return
    fail(f"TestPyPI did not match reviewed archives: {last_error}")


if __name__ == "__main__":
    main()
