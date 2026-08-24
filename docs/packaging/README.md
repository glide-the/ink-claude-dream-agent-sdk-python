# Packaging documentation contract

Files in this folder document the downstream source mirror and local packaging
workflow. They must not redefine SDK runtime behavior or imply rights to
redistribute the Claude Code executable.

- `runtime-integration.md` is the canonical provenance, build, verification,
  runtime-path, and publication-boundary procedure.
- The repository-root `RELEASING.md` is the authoritative Chinese procedure for
  the downstream TestPyPI/PyPI Trusted Publishing environments and approvals.
- Vendor-wheel and release workflows must stay repository-identity gated so
  they cannot execute in the public downstream mirror.
- Ordinary portable CI may verify local artifacts but must have read-only
  repository permission and no artifact upload, package-index upload, tag, or
  release step. The separate manual `publish-portable.yml` workflow may transfer
  verified archives for one day and use OIDC only inside the protected
  `testpypi`/`pypi` publish jobs; it must promote the same bytes through
  TestPyPI verification before PyPI and must not create tags or releases.
- Manual promotion must check out the explicit immutable `source_ref=v<version>`
  for build, installed-wheel smoke, and package-index verification. A later
  `v<version>-publish.<n>` runner tag may repair workflow orchestration without
  moving the reviewed source tag or changing the promoted source bytes.
- The downstream distribution name may change independently of the fixed
  `claude_agent_sdk` import namespace; both names require explicit assertions.
- Version selection is source-ref authoritative: a higher package-index version
  without a matching upstream Git ref is evidence to review, not an automatic
  baseline upgrade.
- Examples must use synthetic prompts and credential-free fixtures.
- Installed-wheel smoke must cover both the default official CLI resolution and
  explicit `cli_path` selection of the standalone clean-room Runtime. The latter
  uses a loopback Anthropic SSE fixture; legacy external-core injection is only
  an optional rollback-envelope lane.
- Never paste credentials, environment dumps, transcripts, workspace content,
  downloaded vendor binaries, or generated package artifacts into these docs.
- Portable wheel/sdist archives and release workflows must reject every
  JavaScript source map (`*.map`) in addition to vendor executables.
