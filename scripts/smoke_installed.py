#!/usr/bin/env python3
"""Smoke-test an installed SDK against official and custom Runtime paths safely.

The parent process re-executes itself with an empty credential-free HOME and a
small allowlisted environment. The official CLI is invoked only with
``--version``. The end-to-end queries use a local, no-network fixture that never
echoes or persists its fixed non-sensitive prompt. When a custom Runtime is
provided, the installed SDK executes its public ``query()`` API through that
Runtime while the Runtime supervises the fixture as its external core.
"""

import argparse
import asyncio
import importlib.metadata
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import NoReturn

SANDBOX_MARKER = "CLAUDE_SDK_PACKAGING_SMOKE_SANDBOXED"
FIXED_PROMPT = "packaging-smoke-nonsecret"
DISTRIBUTION_NAME = "ink-claude-dream-agent-sdk"


def fail(message: str) -> NoReturn:
    """Stop with an actionable smoke-test error."""
    raise SystemExit(f"installed smoke test failed: {message}")


def _official_cli(candidate: str | None) -> Path:
    """Resolve one explicit official CLI path before environment scrubbing."""
    selected = candidate or shutil.which("claude")
    if selected is None:
        fail("official Claude CLI was not found; pass --official-cli")
    path = Path(selected).expanduser().resolve()
    if not path.is_file():
        fail(f"official CLI path is not a file: {path}")
    return path


def _optional_executable(candidate: str | None, label: str) -> Path | None:
    """Resolve an optional executable path before environment scrubbing."""
    if candidate is None:
        return None
    path = Path(candidate).expanduser().resolve()
    if not path.is_file():
        fail(f"{label} path is not a file: {path}")
    if not os.access(path, os.X_OK):
        fail(f"{label} path is not executable: {path}")
    return path


def _reexec_sandboxed(
    args: argparse.Namespace,
    official_cli: Path,
    custom_runtime: Path | None,
    custom_runtime_core: Path | None,
) -> None:
    """Run the actual smoke test without inherited credentials or config."""
    with tempfile.TemporaryDirectory(prefix="claude-sdk-smoke-home-") as home:
        home_path = Path(home)
        temp_path = home_path / "tmp"
        temp_path.mkdir()
        environment = {
            "HOME": home,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.environ.get("PATH", os.defpath),
            "PYTHONIOENCODING": "utf-8",
            "TMPDIR": str(temp_path),
            SANDBOX_MARKER: "1",
        }
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--expected-version",
            args.expected_version,
            "--official-cli",
            str(official_cli),
        ]
        if custom_runtime is not None and custom_runtime_core is not None:
            command.extend(
                [
                    "--custom-runtime",
                    str(custom_runtime),
                    "--custom-runtime-core",
                    str(custom_runtime_core),
                ]
            )
        result = subprocess.run(
            command,
            cwd=home,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        if result.returncode != 0:
            fail(f"sandboxed child exited {result.returncode}")


def _write_fixture(directory: Path) -> Path:
    """Create a fixed-response CLI protocol fixture with no network behavior."""
    if sys.platform == "win32":
        fail("the executable fixture smoke test currently requires POSIX")
    fixture = directory / "claude-fixture"
    body = textwrap.dedent(
        f"""\
        #!{sys.executable}
        import json
        import sys

        if "-v" in sys.argv or "--version" in sys.argv:
            print("2.1.241 (Claude Code fixture)")
            raise SystemExit(0)

        print(json.dumps({{
            "type": "system", "subtype": "init", "session_id": "fixture-session",
            "model": "fixture", "cwd": ".", "tools": [], "mcp_servers": [],
            "permissionMode": "dontAsk", "apiKeySource": "none"
        }}), flush=True)

        for raw_line in sys.stdin:
            try:
                message = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if message.get("type") == "control_request":
                print(json.dumps({{
                    "type": "control_response",
                    "response": {{
                        "subtype": "success",
                        "request_id": message["request_id"],
                        "response": {{}}
                    }}
                }}), flush=True)
            elif message.get("type") == "user":
                print(json.dumps({{
                    "type": "assistant",
                    "session_id": "fixture-session",
                    "message": {{
                        "role": "assistant", "model": "fixture",
                        "content": [{{"type": "text", "text": "fixture-ok"}}]
                    }}
                }}), flush=True)
                print(json.dumps({{
                    "type": "result", "subtype": "success", "is_error": False,
                    "duration_ms": 1, "duration_api_ms": 0, "num_turns": 1,
                    "session_id": "fixture-session", "total_cost_usd": 0.0
                }}), flush=True)
                break
        """
    )
    fixture.write_text(body, encoding="utf-8")
    fixture.chmod(0o755)
    return fixture


async def _fixture_query(
    cli_path: Path,
    sandbox: Path,
    *,
    runtime_core: Path | None = None,
) -> tuple[int, int]:
    """Run the public query API through an explicit CLI or Runtime path."""
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        query,
    )

    environment = {"CLAUDE_CONFIG_DIR": str(sandbox / ".claude")}
    if runtime_core is not None:
        runtime_tmpdir = sandbox / ".claude-tmp"
        runtime_tmpdir.mkdir(mode=0o700, exist_ok=True)
        runtime_tmpdir.chmod(0o700)
        environment.update(
            {
                "INK_CLAUDE_CODE_EXECUTABLE": str(runtime_core),
                "INK_CLAUDE_RUNTIME_WORKSPACE_ROOT": str(sandbox),
                "CLAUDE_CODE_TMPDIR": str(runtime_tmpdir),
            }
        )

    messages = [
        message
        async for message in query(
            prompt=FIXED_PROMPT,
            options=ClaudeAgentOptions(
                cli_path=cli_path,
                cwd=sandbox,
                tools=[],
                setting_sources=[],
                permission_mode="dontAsk",
                max_turns=1,
                env=environment,
            ),
        )
    ]
    assistants = sum(isinstance(message, AssistantMessage) for message in messages)
    results = sum(isinstance(message, ResultMessage) for message in messages)
    return assistants, results


def _run_sandboxed(
    expected_version: str,
    official_cli: Path,
    custom_runtime: Path | None,
    custom_runtime_core: Path | None,
) -> None:
    """Validate the installed distribution and both supported CLI selections."""
    distribution = importlib.metadata.distribution(DISTRIBUTION_NAME)
    if distribution.version != expected_version:
        fail("installed distribution version does not match --expected-version")
    try:
        conflicting_version = importlib.metadata.version("claude-agent-sdk")
    except importlib.metadata.PackageNotFoundError:
        pass
    else:
        fail(
            "official and downstream distributions share the claude_agent_sdk "
            f"namespace; remove claude-agent-sdk {conflicting_version}"
        )
    installed_files = distribution.files
    if installed_files is None or not any(
        str(path) == "claude_agent_sdk/__init__.py" for path in installed_files
    ):
        fail("installed distribution does not provide claude_agent_sdk/__init__.py")
    if any(
        str(path).endswith("/_bundled/claude")
        or str(path).endswith("/_bundled/claude.exe")
        for path in installed_files
    ):
        fail("installed distribution unexpectedly contains a Claude CLI executable")

    from claude_agent_sdk import ClaudeAgentOptions
    from claude_agent_sdk._internal.transport.subprocess_cli import (
        SubprocessCLITransport,
    )

    version_probe = subprocess.run(
        [str(official_cli), "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if version_probe.returncode != 0:
        fail(f"official CLI --version exited {version_probe.returncode}")
    version_line = version_probe.stdout.strip().splitlines()
    if not version_line:
        fail("official CLI --version returned no version text")

    default_transport = SubprocessCLITransport(
        prompt=FIXED_PROMPT, options=ClaudeAgentOptions()
    )
    resolved = Path(default_transport._find_cli()).resolve()
    if not resolved.samefile(official_cli):
        fail(f"default SDK CLI resolution selected {resolved}, expected {official_cli}")

    explicit_transport = SubprocessCLITransport(
        prompt=FIXED_PROMPT,
        options=ClaudeAgentOptions(cli_path=official_cli),
    )
    if Path(explicit_transport._build_command()[0]).resolve() != official_cli:
        fail("explicit official cli_path was not preserved in the launch command")

    sandbox = Path(os.environ["HOME"])
    fixture = _write_fixture(sandbox)
    assistants, results = asyncio.run(_fixture_query(fixture, sandbox))
    if (assistants, results) != (1, 1):
        fail(
            "fixture query did not yield exactly one assistant and one result "
            f"message: {(assistants, results)}"
        )

    print(f"installed_sdk_version={expected_version}")
    print(f"installed_distribution={DISTRIBUTION_NAME}")
    print(f"official_cli={official_cli}")
    print(f"official_cli_version={version_line[0]}")
    print("default_cli_resolution=official")
    print("custom_cli_fixture=ok")

    if custom_runtime is not None and custom_runtime_core is not None:
        runtime_environment = {
            **os.environ,
            "INK_CLAUDE_CODE_EXECUTABLE": str(custom_runtime_core),
        }
        runtime_probe = subprocess.run(
            [str(custom_runtime), "--version"],
            env=runtime_environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if runtime_probe.returncode != 0:
            fail(f"custom Runtime --version exited {runtime_probe.returncode}")
        runtime_version_line = runtime_probe.stdout.strip().splitlines()
        if not runtime_version_line:
            fail("custom Runtime --version returned no version text")

        assistants, results = asyncio.run(
            _fixture_query(custom_runtime, sandbox, runtime_core=fixture)
        )
        if (assistants, results) != (1, 1):
            fail(
                "custom Runtime query did not yield exactly one assistant and one "
                f"result message: {(assistants, results)}"
            )
        print(f"custom_runtime={custom_runtime}")
        print(f"custom_runtime_core={custom_runtime_core}")
        print(f"custom_runtime_core_version={runtime_version_line[0]}")
        print("custom_runtime_query_fixture=ok")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--official-cli")
    parser.add_argument("--custom-runtime")
    parser.add_argument("--custom-runtime-core")
    args = parser.parse_args()
    official_cli = _official_cli(args.official_cli)
    if bool(args.custom_runtime) != bool(args.custom_runtime_core):
        fail("--custom-runtime and --custom-runtime-core must be provided together")
    custom_runtime = _optional_executable(args.custom_runtime, "custom Runtime")
    custom_runtime_core = _optional_executable(
        args.custom_runtime_core, "custom Runtime core"
    )

    if os.environ.get(SANDBOX_MARKER) != "1":
        _reexec_sandboxed(
            args,
            official_cli,
            custom_runtime,
            custom_runtime_core,
        )
        return
    _run_sandboxed(
        args.expected_version,
        official_cli,
        custom_runtime,
        custom_runtime_core,
    )


if __name__ == "__main__":
    main()
