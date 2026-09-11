# Ink Claude Dream Agent SDK for Python

Portable downstream distribution of the MIT-licensed Claude Agent SDK Python
source pinned to upstream `0.2.143`, published as downstream release `0.2.145`.
It preserves the `claude_agent_sdk` import
namespace and public API while intentionally excluding the proprietary Claude
Code executable. See the [official Claude Agent SDK documentation](https://platform.claude.com/docs/en/agent-sdk/python)
for SDK usage.

## Installation

```bash
pip install ink-claude-dream-agent-sdk
```

**Prerequisites:**

- Python 3.10+

This distribution and Anthropic's `claude-agent-sdk` distribution install the
same `claude_agent_sdk` import namespace. Do not install both in one environment;
replace the old distribution before installing this one. This portable package
does not bundle Claude Code. The unchanged SDK selection behavior can use a
system-wide installation or a specific path:

- Install Claude Code separately: `curl -fsSL https://claude.ai/install.sh | bash`
- Specify a custom path: `ClaudeAgentOptions(cli_path="/path/to/claude")`

## Quick Start

```python
import anyio
from claude_agent_sdk import query

async def main():
    async for message in query(prompt="What is 2 + 2?"):
        print(message)

anyio.run(main)
```

## Basic Usage: query()

`query()` is an async function for querying Claude Code. It returns an `AsyncIterator` of response messages. See [src/claude_agent_sdk/query.py](src/claude_agent_sdk/query.py).

```python
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock

# Simple query
async for message in query(prompt="Hello Claude"):
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                print(block.text)

# With options
options = ClaudeAgentOptions(
    system_prompt="You are a helpful assistant",
    max_turns=1
)

async for message in query(prompt="Tell me a joke", options=options):
    print(message)
```

### Using Tools

By default, Claude has access to the full [Claude Code toolset](https://code.claude.com/docs/en/settings#tools-available-to-claude) (Read, Write, Edit, Bash, and others). `allowed_tools` is a permission allowlist: listed tools are auto-approved, and unlisted tools fall through to `permission_mode` and `can_use_tool` for a decision. It does not remove tools from Claude's toolset. To block specific tools, use `disallowed_tools`. See the [permissions guide](https://platform.claude.com/docs/en/agent-sdk/permissions) for the full evaluation order.

```python
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Write", "Bash"],  # auto-approve these tools
    permission_mode='acceptEdits'  # auto-accept file edits
)

async for message in query(
    prompt="Create a hello.py file",
    options=options
):
    # Process tool use and results
    pass
```

### Working Directory

```python
from pathlib import Path

options = ClaudeAgentOptions(
    cwd="/path/to/project"  # or Path("/path/to/project")
)
```

## ClaudeSDKClient

`ClaudeSDKClient` supports bidirectional, interactive conversations with Claude
Code. See [src/claude_agent_sdk/client.py](src/claude_agent_sdk/client.py).

Unlike `query()`, `ClaudeSDKClient` additionally enables **custom tools** and **hooks**, both of which can be defined as Python functions.

### Custom Tools (as In-Process SDK MCP Servers)

A **custom tool** is a Python function that you can offer to Claude, for Claude to invoke as needed.

Custom tools are implemented in-process MCP servers that run directly within your Python application, eliminating the need for separate processes that regular MCP servers require.

For an end-to-end example, see [MCP Calculator](examples/mcp_calculator.py).

#### Creating a Simple Tool

```python
from claude_agent_sdk import tool, create_sdk_mcp_server, ClaudeAgentOptions, ClaudeSDKClient

# Define a tool using the @tool decorator
@tool("greet", "Greet a user", {"name": str})
async def greet_user(args):
    return {
        "content": [
            {"type": "text", "text": f"Hello, {args['name']}!"}
        ]
    }

# Create an SDK MCP server
server = create_sdk_mcp_server(
    name="my-tools",
    version="1.0.0",
    tools=[greet_user]
)

# Use it with Claude. allowed_tools pre-approves the tool so it runs
# without a permission prompt; it does not control tool availability.
options = ClaudeAgentOptions(
    mcp_servers={"tools": server},
    allowed_tools=["mcp__tools__greet"]
)

async with ClaudeSDKClient(options=options) as client:
    await client.query("Greet Alice")

    # Extract and print response
    async for msg in client.receive_response():
        print(msg)
```

#### Benefits Over External MCP Servers

- **No subprocess management** - Runs in the same process as your application
- **Better performance** - No IPC overhead for tool calls
- **Simpler deployment** - Single Python process instead of multiple
- **Easier debugging** - All code runs in the same process
- **Type safety** - Direct Python function calls with type hints

#### Migration from External Servers

```python
# BEFORE: External MCP server (separate process)
options = ClaudeAgentOptions(
    mcp_servers={
        "calculator": {
            "type": "stdio",
            "command": "python",
            "args": ["-m", "calculator_server"]
        }
    }
)

# AFTER: SDK MCP server (in-process)
from my_tools import add, subtract  # Your tool functions

calculator = create_sdk_mcp_server(
    name="calculator",
    tools=[add, subtract]
)

options = ClaudeAgentOptions(
    mcp_servers={"calculator": calculator}
)
```

#### Mixed Server Support

You can use both SDK and external MCP servers together:

```python
options = ClaudeAgentOptions(
    mcp_servers={
        "internal": sdk_server,      # In-process SDK server
        "external": {                # External subprocess server
            "type": "stdio",
            "command": "external-server"
        }
    }
)
```

### Hooks

A **hook** is a Python function that the Claude Code _application_ (_not_ Claude) invokes at specific points of the Claude agent loop. Hooks can provide deterministic processing and automated feedback for Claude. Read more in [Intercept and control agent behavior with hooks](https://platform.claude.com/docs/en/agent-sdk/hooks).

For more examples, see examples/hooks.py.

#### Example

```python
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher

async def check_bash_command(input_data, tool_use_id, context):
    tool_name = input_data["tool_name"]
    tool_input = input_data["tool_input"]
    if tool_name != "Bash":
        return {}
    command = tool_input.get("command", "")
    block_patterns = ["foo.sh"]
    for pattern in block_patterns:
        if pattern in command:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Command contains invalid pattern: {pattern}",
                }
            }
    return {}

options = ClaudeAgentOptions(
    allowed_tools=["Bash"],
    hooks={
        "PreToolUse": [
            HookMatcher(matcher="Bash", hooks=[check_bash_command]),
        ],
    }
)

async with ClaudeSDKClient(options=options) as client:
    # Test 1: Command with forbidden pattern (will be blocked)
    await client.query("Run the bash command: ./foo.sh --help")
    async for msg in client.receive_response():
        print(msg)

    print("\n" + "=" * 50 + "\n")

    # Test 2: Safe command that should work
    await client.query("Run the bash command: echo 'Hello from hooks example!'")
    async for msg in client.receive_response():
        print(msg)
```

## Types

See [src/claude_agent_sdk/types.py](src/claude_agent_sdk/types.py) for complete type definitions:

- `ClaudeAgentOptions` - Configuration options
- `AssistantMessage`, `UserMessage`, `SystemMessage`, `ResultMessage` - Message types
- `TextBlock`, `ToolUseBlock`, `ToolResultBlock` - Content blocks

## Error Handling

```python
from claude_agent_sdk import (
    ClaudeSDKError,      # Base error
    CLINotFoundError,    # Claude Code not installed
    CLIConnectionError,  # Connection issues
    ProcessError,        # Process failed
    ResultError,         # Run ended with an error result (subclass of ProcessError)
    CLIJSONDecodeError,  # JSON parsing issues
)

try:
    async for message in query(prompt="Hello"):
        pass
except CLINotFoundError:
    print("Please install Claude Code")
except ResultError as e:
    # The CLI reported a terminal error result (also yielded as the final
    # ResultMessage) and exited. Structured fields are on the exception.
    print(f"Run failed: {e.subtype=} {e.terminal_reason=} {e.api_error_status=}")
    print(e.result or e.errors)
except ProcessError as e:
    print(f"Process failed with exit code: {e.exit_code}")
except CLIJSONDecodeError as e:
    print(f"Failed to parse response: {e}")
```

See [src/claude_agent_sdk/\_errors.py](src/claude_agent_sdk/_errors.py) for all error types.

## Available Tools

See the [Claude Code documentation](https://code.claude.com/docs/en/settings#tools-available-to-claude) for a complete list of available tools.

## Examples

See [examples/quick_start.py](examples/quick_start.py) for a complete working example.

See [examples/streaming_mode.py](examples/streaming_mode.py) for comprehensive examples involving `ClaudeSDKClient`. You can even run interactive examples in IPython from [examples/streaming_mode_ipython.py](examples/streaming_mode_ipython.py).

## Migrating from Claude Code SDK

If you're upgrading from the Claude Code SDK (versions < 0.1.0), please see the [CHANGELOG.md](CHANGELOG.md#010) for details on breaking changes and new features, including:

- `ClaudeCodeOptions` → `ClaudeAgentOptions` rename
- Merged system prompt configuration
- Settings isolation and explicit control
- New programmatic subagents and session forking features

## Development

If you're contributing to this project, run the initial setup script to install git hooks:

```bash
./scripts/initial-setup.sh
```

This installs a pre-push hook that runs lint checks before pushing, matching the CI workflow. To skip the hook temporarily, use `git push --no-verify`.

### Building portable packages locally

Use the pinned, reproducible source-only build documented in
[`docs/packaging/runtime-integration.md`](docs/packaging/runtime-integration.md).
The resulting artifact names are:

```bash
ink_claude_dream_agent_sdk-0.2.145-py3-none-any.whl
ink_claude_dream_agent_sdk-0.2.145.tar.gz
```

Default Hatch wheel and sdist targets explicitly exclude
`src/claude_agent_sdk/_bundled/claude{,.exe}`. The inherited upstream
`scripts/build_wheel.py` vendor builder also refuses to run under this renamed
distribution, before downloading anything.

### Reproducible downstream packages

For pinned upstream provenance, read-only sync inspection, a portable SDK-only
wheel/sdist, repeat-build verification, and isolated official/custom CLI path
smoke tests, see
[`docs/packaging/runtime-integration.md`](docs/packaging/runtime-integration.md).
The downstream procedure does not authorize redistribution of the proprietary
Claude Code binary. Local artifacts remain ignored and untracked; reviewed SDK
archives leave CI only through the protected promotion workflow below.

### Release policy

The downstream portable-SDK promotion workflow is configured to publish one
reviewed wheel/sdist byte set to TestPyPI, verify the published bytes, and only
then enter the protected PyPI approval environment. Repository administrators
must still configure both Trusted Publishers and required reviewers before the
workflow is usable. The inherited vendor-wheel and official PyPI workflows stay
repository-identity gated to `anthropics/claude-agent-sdk-python`; they skip in
this mirror. See [`RELEASING.md`](RELEASING.md) for the Chinese authoritative
release procedure. Neither release path permits a Claude CLI or `*.map` file in
the downstream Python archives.

## License and terms

Use of this SDK is governed by Anthropic's [Commercial Terms of Service](https://www.anthropic.com/legal/commercial-terms), including when you use it to power products and services that you make available to your own customers and end users, except to the extent a specific component or dependency is covered by a different license as indicated in that component's LICENSE file.
