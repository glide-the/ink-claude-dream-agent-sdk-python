#!/usr/bin/env python3
"""Smoke-test an installed SDK against official and fixture CLI paths safely.

The parent process re-executes itself with an empty credential-free HOME and a
small allowlisted environment. The official CLI is invoked only with
``--version``. The end-to-end query uses a local, no-network fixture that never
echoes or persists its fixed non-sensitive prompt.
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


def _reexec_sandboxed(args: argparse.Namespace, official_cli: Path) -> None:
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


async def _fixture_query(fixture: Path, sandbox: Path) -> tuple[int, int]:
    """Run the public query API through the explicit cli_path injection."""
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        query,
    )

    messages = [
        message
        async for message in query(
            prompt=FIXED_PROMPT,
            options=ClaudeAgentOptions(
                cli_path=fixture,
                cwd=sandbox,
                tools=[],
                setting_sources=[],
                permission_mode="dontAsk",
                max_turns=1,
                env={"CLAUDE_CONFIG_DIR": str(sandbox / ".claude")},
            ),
        )
    ]
    assistants = sum(isinstance(message, AssistantMessage) for message in messages)
    results = sum(isinstance(message, ResultMessage) for message in messages)
    return assistants, results


def _run_sandboxed(expected_version: str, official_cli: Path) -> None:
    """Validate the installed distribution and both supported CLI selections."""
    if importlib.metadata.version("claude-agent-sdk") != expected_version:
        fail("installed distribution version does not match --expected-version")

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
    print(f"official_cli={official_cli}")
    print(f"official_cli_version={version_line[0]}")
    print("default_cli_resolution=official")
    print("custom_cli_fixture=ok")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--official-cli")
    args = parser.parse_args()
    official_cli = _official_cli(args.official_cli)

    if os.environ.get(SANDBOX_MARKER) != "1":
        _reexec_sandboxed(args, official_cli)
        return
    _run_sandboxed(args.expected_version, official_cli)


if __name__ == "__main__":
    main()
