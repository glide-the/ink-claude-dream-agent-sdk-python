# Packaging documentation contract

Files in this folder document the downstream source mirror and local packaging
workflow. They must not redefine SDK runtime behavior or imply rights to
redistribute the Claude Code executable.

- `runtime-integration.md` is the canonical provenance, build, verification,
  runtime-path, and publication-boundary procedure.
- Examples must use synthetic prompts and credential-free fixtures.
- Never paste credentials, environment dumps, transcripts, workspace content,
  downloaded vendor binaries, or generated package artifacts into these docs.
