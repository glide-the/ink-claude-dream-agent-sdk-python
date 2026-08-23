# Claude Agent SDK mirror packaging and runtime integration

## Outcome and boundary

This public mirror tracks the official MIT-licensed Python source at an exact
commit and adds only provenance, sync inspection, reproducible source-package
building, archive verification, installed-package smoke tests, and this
documentation. The upstream `src/` tree, public API, subprocess transport,
streaming protocol, launcher selection, and `ClaudeAgentOptions(cli_path=...)`
behavior remain unchanged. No IM DTO, state, transcript, or database logic is
introduced.

The pinned baseline is:

- Upstream: `https://github.com/anthropics/claude-agent-sdk-python.git`
- Ref: `refs/heads/main`
- Commit: `542fefb3b94be87760b2513fff889b91bb5b6672`
- Tree: `1c86f3a9144616da2a9435f0440066e23a4b580b`
- SDK version: `0.2.143`
- Official bundled-CLI pin: `2.1.241`
- Source license: MIT

`packaging/upstream.json` is the machine-readable source of truth. As checked on
2026-08-23, the mirror remote is public and advertises
`codex/sdk-packaging-flow` as its default (and only) branch. That repository
state does not authorize package or vendor-binary publication; changing the
default branch or adding release refs remains a separate reviewed action.

## Legal and publication boundary

The repository source is MIT-licensed. Official release wheels, however, bundle
the proprietary Claude Code executable. Available official legal material says
that binary must remain unmodified and run as published; this review found no
independent redistribution grant for republishing it from this mirror.

Therefore:

- Never commit or push `dist/`, wheel/sdist files, installer downloads, or a
  Claude Code executable.
- Upstream vendor-wheel and PyPI release jobs are repository-identity gated to
  `anthropics/claude-agent-sdk-python`; they must remain skipped in this public
  mirror even when a workflow is manually dispatched or a packaging PR opens.
- Keep all generated artifacts local and ignored, even when a package contains
  only MIT source.
- Do not publish mirror wheels that bundle the official CLI unless Anthropic
  gives explicit authorization covering that redistribution.
- Treat public binary/package publication as blocked pending that authorization.
- Source, provenance records, documentation, and build/verification tools are
  the only publishable outputs of this work.

The local portable build below excludes the vendor executable and validates
that exclusion by inspecting archive members. This reduces risk but does not
change the no-artifact-commit/no-artifact-push rule.

## Verify and inspect upstream sync

The reference checkout is read-only in every command:

```bash
python scripts/verify_upstream.py \
  --reference-repo /Users/dmeck/project/claude-agent-sdk-python
python scripts/check_upstream_sync.py \
  --reference-repo /Users/dmeck/project/claude-agent-sdk-python
```

`verify_upstream.py` checks the full commit and tree identifiers, commit epoch,
MIT license file digest, SDK/CLI versions, ancestry, and an empty diff between
the current `src/` tree and the pinned official commit. `check_upstream_sync.py`
reports either `sync_status=exact` or a newer linear candidate plus changed-path
count. It never fetches, merges, or writes either repository.

For a future sync, fetch the official branch into a dedicated review ref in the
mirror, review the complete old-pin-to-candidate history/tree/license/API diff,
merge the reviewed commit without rewriting upstream, and then update every
field in `upstream.json`. Re-run both commands before packaging. Never use the
reference checkout as a write target.

## Build local reproducible source artifacts

The portable flow intentionally does not call the official network installer.
It uses Python 3.12 and a complete hash-locked set of universal build wheels:

```bash
python3.12 -m venv .venv-packaging
.venv-packaging/bin/python -m pip install \
  --only-binary=:all: --require-hashes \
  -r packaging/build-requirements.lock
.venv-packaging/bin/python scripts/reproducible_build.py
```

The builder refuses a dirty tree by default. It snapshots only Git-tracked and
non-ignored untracked inputs, normalizes timestamps to the pinned commit's
`SOURCE_DATE_EPOCH`, builds wheel and sdist twice in independent temporary
directories, rejects unsafe archive paths, verifies required provenance/docs,
proves the wheel contains no `claude`/`claude.exe`, and requires byte-identical
SHA-256 digests. Verified local output and `SHA256SUMS` go under the ignored
`dist/reproducible/` directory. `--allow-dirty` is limited to pre-commit local
verification and is not a release mode.

The unchanged upstream `scripts/build_wheel.py` remains available for official
platform-wheel engineering. Its network-fetched proprietary CLI output is not
claimed to be independently reproducible or redistributable by this mirror.

## Verify the installed SDK runtime paths

Install the locally generated portable wheel in a fresh environment using the
normal runtime dependency resolver, then run:

```bash
python scripts/smoke_installed.py \
  --expected-version 0.2.143 \
  --official-cli /absolute/path/to/default/claude \
  --custom-runtime /absolute/path/to/ink-claude-runtime.mjs \
  --custom-runtime-core /absolute/path/to/official/claude-2.1.241
```

The smoke test re-executes under a temporary empty HOME and an allowlisted
environment. It invokes the default official CLI and the custom Runtime's
selected official core only with `--version`; no prompt, credential, model
request, or transcript reaches either official binary. It verifies that the
installed SDK's existing default resolution and explicit `cli_path` launch
command select the expected executables.

The end-to-end public `query()` checks target a temporary executable fixture:
first directly, then through the actual custom Runtime. In the Runtime lane,
the envelope supervises the fixture as its external core with an exact
temporary workspace and `CLAUDE_CODE_TMPDIR`; the separately selected official
core is used only for the bounded version probe. The fixture implements only
the version probe, initialize response, one fixed assistant message, and one
fixed result. It has no network behavior, never echoes its fixed synthetic
prompt, and is deleted with the temporary HOME. This validates the installed
SDK → custom Runtime → external-core process boundary without touching IM
state or duplicating SDK protocol code.

## Out-of-repository real-business acceptance

On 2026-08-23 the unchanged SDK process contract was also exercised by the
existing local Dream application through its public Deck → Chat → Dream UI,
current Admin/Gateway services, and current real PostgreSQL data. The same
existing actor and Deck passed twice: first with the unmodified official Claude
Code `2.1.241` executable selected directly, then with the packaged clean-room
Runtime selected through the existing CLI-path injection point and supervising
that same official executable.

Each lane passed new session, first-token/SSE, multi-turn continuation, internal
stdio MCP tool/result, workspace, transcript, resume, locked-plugin loading,
Dream artifact hooks, Episode artifacts, and durable UI re-entry. This evidence
lives in the Dream release harness and content-free local receipts; no user
credential, prompt/response body, transcript, workspace material, Run ID, or
generated business artifact is copied into this public mirror.

This acceptance used Dream's current SDK `0.2.140`; it proves compatibility of
the upstream CLI-path/process boundary, not a Dream dependency upgrade to this
mirror's pinned `0.2.143`. Installed `0.2.143` wheel/sdist smoke and public
`query()` boundary tests are covered separately above.

A later lane configured a disposable external provider built with the official
MCP Python SDK `2.0.0` through Dream's public MCP API. The same existing actor
completed DCR/PKCE authorization, then the normal Chat UI confirmed and
persisted two HTTP MCP tool results across refresh and same-thread resume while
using the custom Runtime path. Public logout/remove completed and the final
server list proved cleanup. This is protocol evidence through the normal local
Dream/Admin/Gateway/PostgreSQL topology, not a shadow application or a change
to this SDK mirror.

The provider declared a resource, but Dream's current detail/inventory surface
did not report Resources/Prompts for that user-scope server. Real Resources UI
read, transient-5xx reconnect, legacy SSE add, and colon-containing user-scope
server names therefore remain unclaimed. No provider fixture, credential,
server identifier, callback, transcript, or workspace body is stored here.

## Required final audit

Before handing off source/tooling changes:

1. Run focused tests, Ruff, and mypy for all new scripts.
2. Confirm two artifact builds have identical names, sizes, and SHA-256 values.
3. Inspect wheel/sdist member lists and confirm no vendor executable is present.
4. Install the wheel outside the source tree and run the isolated smoke test.
5. Run `git status --short --ignored` and `git ls-files dist` to prove every
   artifact is ignored and untracked.
6. Inspect every vendor-wheel/release workflow and prove its official-repository
   identity guard remains effective.
7. Do not commit, tag, push, upload, change the public default branch, or add
   release refs without explicit parent review and any required Anthropic
   authorization.
