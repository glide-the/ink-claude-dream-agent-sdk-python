#!/usr/bin/env python3
"""Update the downstream distribution and import-package version pins."""

import re
import sys
from pathlib import Path

DISTRIBUTION_NAME = "ink-claude-dream-agent-sdk"
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
PROJECT_NAME_PATTERN = re.compile(r'^name = "([^"]+)"$', re.MULTILINE)
PROJECT_VERSION_PATTERN = re.compile(r'^version = "[^"]*"', re.MULTILINE)
IMPORT_VERSION_PATTERN = re.compile(r'^__version__ = "[^"]*"', re.MULTILINE)


def update_version(new_version: str) -> None:
    """Atomically prepare both version-file rewrites after validation."""
    if VERSION_PATTERN.fullmatch(new_version) is None:
        raise ValueError(f"invalid SDK version: {new_version!r}")

    pyproject_path = Path("pyproject.toml")
    version_path = Path("src/claude_agent_sdk/_version.py")
    pyproject = pyproject_path.read_text(encoding="utf-8")
    import_version = version_path.read_text(encoding="utf-8")

    name_match = PROJECT_NAME_PATTERN.search(pyproject)
    if name_match is None or name_match.group(1) != DISTRIBUTION_NAME:
        actual = name_match.group(1) if name_match is not None else "<missing>"
        raise ValueError(
            f"refusing to update distribution {actual!r}; expected {DISTRIBUTION_NAME!r}"
        )

    updated_pyproject, project_count = PROJECT_VERSION_PATTERN.subn(
        lambda _match: f'version = "{new_version}"', pyproject, count=1
    )
    updated_import, import_count = IMPORT_VERSION_PATTERN.subn(
        lambda _match: f'__version__ = "{new_version}"', import_version, count=1
    )
    if project_count != 1 or import_count != 1:
        raise ValueError("expected exactly one project and import version assignment")

    pyproject_path.write_text(updated_pyproject, encoding="utf-8")
    version_path.write_text(updated_import, encoding="utf-8")
    print(f"Updated {DISTRIBUTION_NAME} to version {new_version}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/update_version.py <version>", file=sys.stderr)
        sys.exit(1)

    try:
        update_version(sys.argv[1])
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
