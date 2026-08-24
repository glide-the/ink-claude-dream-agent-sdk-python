#!/usr/bin/env python3
"""Smoke-test an installed SDK against official and custom Runtime paths safely.

The parent process re-executes itself with an empty credential-free HOME and a
small allowlisted environment. The official CLI is invoked only with
``--version``. The end-to-end queries use a local, no-network fixture that never
echoes or persists its fixed non-sensitive prompt. A standalone custom Runtime
is exercised against a loopback Anthropic-compatible SSE fixture. The legacy
external-core mode remains available only for rollback-envelope verification.
"""

import argparse
import asyncio
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
        home_path = Path(home).resolve()
        temp_path = home_path / "tmp"
        temp_path.mkdir()
        environment = {
            "HOME": str(home_path),
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
        if custom_runtime is not None:
            command.extend(["--custom-runtime", str(custom_runtime)])
        if custom_runtime_core is not None:
            command.extend(["--custom-runtime-core", str(custom_runtime_core)])
        result = subprocess.run(
            command,
            cwd=home_path,
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
    provider_base_url: str | None = None,
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
    if provider_base_url is not None:
        environment.update(
            {
                "ANTHROPIC_API_KEY": "",
                "ANTHROPIC_AUTH_TOKEN": "provider-free-loopback-token",
                "ANTHROPIC_BASE_URL": provider_base_url,
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


def _sse(event: str, payload: dict[str, object]) -> bytes:
    """Encode one Anthropic-compatible SSE event."""
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n".encode()


@contextmanager
def _provider_fixture() -> Iterator[tuple[str, list[dict[str, object]]]]:
    """Serve one credential-free loopback Messages API fixture."""
    requests: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            """Suppress request logging so no request body reaches output."""

        def do_POST(self) -> None:
            """Return one fixed SSE response without echoing request content."""
            length = int(self.headers.get("content-length", "0"))
            if length <= 0 or length > 1024 * 1024:
                self.send_error(400)
                return
            try:
                payload = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self.send_error(400)
                return
            if not isinstance(payload, dict):
                self.send_error(400)
                return
            requests.append(payload)
            message_id = f"msg_packaging_{len(requests)}"
            body = b"".join(
                [
                    _sse(
                        "message_start",
                        {
                            "type": "message_start",
                            "message": {
                                "id": message_id,
                                "type": "message",
                                "role": "assistant",
                                "content": [],
                                "model": "claude-packaging-fixture",
                                "stop_reason": None,
                                "stop_sequence": None,
                                "usage": {"input_tokens": 1, "output_tokens": 0},
                            },
                        },
                    ),
                    _sse(
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": 0,
                            "content_block": {"type": "text", "text": ""},
                        },
                    ),
                    _sse(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": 0,
                            "delta": {
                                "type": "text_delta",
                                "text": "fixture-ok",
                            },
                        },
                    ),
                    _sse(
                        "content_block_stop",
                        {"type": "content_block_stop", "index": 0},
                    ),
                    _sse(
                        "message_delta",
                        {
                            "type": "message_delta",
                            "delta": {
                                "stop_reason": "end_turn",
                                "stop_sequence": None,
                            },
                            "usage": {"output_tokens": 1},
                        },
                    ),
                    _sse("message_stop", {"type": "message_stop"}),
                ]
            )
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


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

    if custom_runtime is not None:
        runtime_environment = {**os.environ}
        if custom_runtime_core is not None:
            runtime_environment["INK_CLAUDE_CODE_EXECUTABLE"] = str(custom_runtime_core)
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

        if custom_runtime_core is not None:
            assistants, results = asyncio.run(
                _fixture_query(custom_runtime, sandbox, runtime_core=fixture)
            )
            runtime_mode = "external-core-rollback"
            provider_requests = 0
        else:
            with _provider_fixture() as (provider_base_url, requests):
                assistants, results = asyncio.run(
                    _fixture_query(
                        custom_runtime,
                        sandbox,
                        provider_base_url=provider_base_url,
                    )
                )
                runtime_mode = "standalone-clean-room"
                provider_requests = len(requests)
                if provider_requests != 1:
                    fail(
                        "standalone Runtime provider fixture expected exactly one "
                        f"request, received {provider_requests}"
                    )
        if (assistants, results) != (1, 1):
            fail(
                "custom Runtime query did not yield exactly one assistant and one "
                f"result message: {(assistants, results)}"
            )
        print(f"custom_runtime={custom_runtime}")
        print(f"custom_runtime_version={runtime_version_line[0]}")
        print(f"custom_runtime_mode={runtime_mode}")
        print(f"custom_runtime_provider_requests={provider_requests}")
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
    if args.custom_runtime_core and not args.custom_runtime:
        fail("--custom-runtime-core requires --custom-runtime")
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
