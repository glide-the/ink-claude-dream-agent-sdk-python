# Releasing the downstream distribution

The downstream distribution name is `ink-claude-dream-agent-sdk`; the import
namespace remains `claude_agent_sdk`. Version `0.2.143` is source-compatible
with the exact upstream pin recorded in `packaging/upstream.json`.

## Current gate: publication blocked

No GitHub Actions job in this public mirror is authorized to publish packages,
tags, releases, or vendor binaries. The inherited upstream workflows are kept
for provenance and remain gated to the exact repository identity
`anthropics/claude-agent-sdk-python`. Their package URLs and vendor-wheel logic
refer to Anthropic's official `claude-agent-sdk` release, not this downstream
distribution.

The inherited `scripts/build_wheel.py` also fails before download when the
project name is not `claude-agent-sdk`. Default Hatch wheel and sdist targets
exclude `_bundled/claude` and `_bundled/claude.exe` independently of that
script-level guard.

## Required review before a future portable release

Publication remains fail closed until a separately reviewed change provides
all of the following:

1. Explicit owner authorization for the target package index and project name.
2. Trusted publishing or a project-scoped token for
   `ink-claude-dream-agent-sdk`; never reuse Anthropic release credentials.
3. A portable-only workflow that runs `scripts/reproducible_build.py`, verifies
   both archive member lists, checks the exact distribution metadata/name, and
   rejects every bundled Claude Code executable before upload.
4. Two byte-identical builds from the reviewed clean commit plus `twine check`.
5. A fresh-environment installed-wheel smoke using the official CLI path and,
   when available, the custom Runtime path through `ClaudeAgentOptions.cli_path`.
6. Confirmation that the `src/` diff from the pinned upstream commit is empty
   and that public API/state-machine/JSONL transport behavior is unchanged.
7. A human review of the current Anthropic terms and any authorization needed
   for distribution naming, trademarks, and executable redistribution.

Until those controls land, generated wheel/sdist files and checksums remain
local, ignored, and untracked. Do not upload, tag, push, or create release refs.

## Versioning and local artifact contract

The SDK version remains synchronized in `pyproject.toml` and
`src/claude_agent_sdk/_version.py`. The upstream CLI pin remains recorded in
`src/claude_agent_sdk/_cli_version.py` for compatibility/provenance, but it is
not embedded in this distribution.

For version `0.2.143`, the only accepted portable artifact names are:

```text
ink_claude_dream_agent_sdk-0.2.143-py3-none-any.whl
ink_claude_dream_agent_sdk-0.2.143.tar.gz
```

The canonical local procedure is
[`docs/packaging/runtime-integration.md`](docs/packaging/runtime-integration.md).
