# Packaging input contract

This folder contains inputs, never generated artifacts.

- `upstream.json` is the reviewed official source/version provenance pin and
  the distinct downstream distribution version declaration.
- `build-requirements.lock` is the hash-locked Python 3.12 builder toolchain.
- Wheel, sdist, checksum, downloaded installer, and Claude Code binary files
  must not be added here or committed anywhere in this public mirror.
- The portable distribution is `ink-claude-dream-agent-sdk`; its archive stem
  is `ink_claude_dream_agent_sdk`, while its import namespace remains
  `claude_agent_sdk`.

The operational procedure and legal boundary are documented in
[`docs/packaging/runtime-integration.md`](../docs/packaging/runtime-integration.md).
Changes in this folder require rerunning upstream verification, two independent
builds, archive inspection, installed-wheel smoke tests, and `git status` checks.
