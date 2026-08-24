# Claude Agent SDK mirror packaging and runtime integration

## 中文权威发布与 Runtime 集成合同

本镜像的 Python 发行名是 `ink-claude-dream-agent-sdk`，安装后的导入名仍为
`claude_agent_sdk`。这不是仍在使用官方 distribution：Python 的包索引发行名
和 import namespace 本来就是两个独立合同。由于两个发行包提供同一个 import
namespace，官方 `claude-agent-sdk` 与本镜像不得共存于同一环境。

本仓库只发布不含 Claude Code CLI 的 Python wheel/sdist。CLI 或精简 Runtime
必须独立安装，SDK 继续复用上游的 `ClaudeAgentOptions(cli_path=...)`、默认
`PATH` 解析和 subprocess transport，不增加 Dream DTO、第二套 Agent 状态机
或协议分叉。Dream 最终运行关系是：

```text
ink-claude-dream-agent-sdk (PyPI / Python import: claude_agent_sdk)
    -> ClaudeAgentOptions.cli_path 或 PATH
    -> 独立安装的 official/custom Claude Runtime
    -> 既有 JSONL、streaming、tool、MCP、resume 合同
```

`.github/workflows/publish-portable.yml` 是镜像唯一发布入口。构建 job 执行上游
精确来源校验、两次可复现构建、SHA-256、严格归档检查和 `twine check`，拒绝
CLI 与任何 `*.map` 后把字节保存为 GitHub artifact。联网安装依赖的 smoke 在
另一个 runner 上只使用下载副本；TestPyPI 发布 job 在两者成功后重新下载原
artifact。随后机器重新下载 TestPyPI 文件并逐一比对 SHA，成功后 PyPI 人工
审批才能提升同一个 artifact，不能选择 target 绕过 TestPyPI。`testpypi` 与
`pypi` Environment 已创建、配置 required reviewer 并只允许 `v*` tag；只有两
个发布 job 拥有 `id-token: write`。由于当前只有一个仓库 collaborator，暂时允
许该 reviewer 自审；增加第二位可信 reviewer 后必须启用 prevent-self-review。
整个流程只接受从 `v<version>` 标签触发。完整步骤以仓库根
目录 [`RELEASING.md`](../../RELEASING.md) 为准。

这一发布能力只覆盖 MIT Python SDK 归档，不覆盖 Anthropic Claude Code 二进制
或恢复源码的再分发。CLI、transcript、Workspace、插件物化数据和 MCP/OAuth
凭据均不得进入 Python 包。继承的 Anthropic 官方发布工作流继续严格锁定官方
仓库身份，不得启用、改写或借用其发布凭据。

### 2026-08-24 当前验收状态

- standalone clean-room Runtime 验收已通过 PR #4 合并到默认分支
  `main`，对应 merge commit 为
  `827f079d9fa62e1c1635f395dd0e3f1f812eb7f9`。本文档状态修正不改变
  该提交已验收的 SDK 源码、公开 API 或 subprocess transport。
- 上游公开 `main` 仍为
  `542fefb3b94be87760b2513fff889b91bb5b6672`。镜像的 28 个非缓存源码文件与
  该提交逐字节一致，SDK 版本为 `0.2.143`，公开 API 与 subprocess transport
  没有下游分叉。
- 当前本机 `PATH` 选中的官方 Claude CLI 是 `2.1.220`；本轮 standalone
  clean-room Runtime 候选报告 `2.1.241`。这两个值分别表示实际默认路径和
  Runtime 兼容版本，不得混写成同一个“当前 CLI”。
- 隔离安装验收必须同时证明：默认 SDK 路径选择实际 official CLI；显式
  `ClaudeAgentOptions(cli_path=...)` 选择 standalone clean-room Runtime，并通过
  本机 loopback Anthropic SSE fixture 完成一轮真实 SDK `query()`。fixture 不访问
  外网、不读取认证配置，也不把 Runtime、transcript 或用户数据打入 wheel。
- PyPI 与 TestPyPI 的 `ink-claude-dream-agent-sdk` JSON API 当前均返回 `404`，
  表示尚无公开项目或已发布版本。GitHub 的 `pypi`/`testpypi`
  Environment 和 required reviewer 已配置，但按发布合同，两个索引的
  pending Trusted Publisher 仍需在外部控制面登记并复核；该状态没有
  公开查询接口。本机也没有 Twine 用户名、Token 或 `.pypirc`。
  当前未创建或推送 `v0.2.143` 标签，未触发发布工作流，也未上传
  TestPyPI 或 PyPI。正式发布必须在 Trusted Publisher 复核完成后获得用户
  单独授权，再严格按 [`RELEASING.md`](../../RELEASING.md) 执行；源码合并
  和本地归档验证都不构成发布授权。

## Outcome and boundary

This public mirror tracks the official MIT-licensed Python source at an exact
commit and adds only provenance, sync inspection, reproducible source-package
building, archive verification, installed-package smoke tests, and this
documentation. The upstream `src/` tree, public API, subprocess transport,
streaming protocol, launcher selection, and `ClaudeAgentOptions(cli_path=...)`
behavior remain unchanged. No IM DTO, state, transcript, or database logic is
introduced.

The downstream Python distribution is `ink-claude-dream-agent-sdk`. Python
imports remain `claude_agent_sdk`; there is no namespace rename or compatibility
shim. The downstream and official distributions therefore must not be installed
together in one environment.

The pinned baseline is:

- Upstream: `https://github.com/anthropics/claude-agent-sdk-python.git`
- Ref: `refs/heads/main`
- Commit: `542fefb3b94be87760b2513fff889b91bb5b6672`
- Tree: `1c86f3a9144616da2a9435f0440066e23a4b580b`
- SDK version: `0.2.143`
- Downstream distribution: `ink-claude-dream-agent-sdk`
- Import namespace: `claude_agent_sdk`
- Official bundled-CLI pin: `2.1.241`
- Source license: MIT

Version applicability was rechecked on 2026-08-24. PyPI publishes
`claude-agent-sdk==0.2.144`, but the official Git `main` branch and latest Git
tag still identify `0.2.143` at the commit above. The `0.2.144` sdist has the
same 28-file `src` inventory; its source tree differs only in the version file
and bundled-CLI pin (`2.1.239`). It has no matching public Git source ref or
new Runtime-path/build extension point. This mirror therefore remains pinned to
the auditable Git source baseline `0.2.143` and its newer CLI pin `2.1.241`.
PyPI's highest version number must not be treated as a source-authoritative
upgrade until a matching upstream ref and complete provenance review exist.

`packaging/upstream.json` is the machine-readable source of truth. As checked on
2026-08-24, the mirror remote is public and advertises `main` as its default
branch. That repository state does not authorize package or vendor-binary
publication; adding release refs remains a separate reviewed action.

## Legal and publication boundary

The repository source is MIT-licensed. Official release wheels, however, bundle
the proprietary Claude Code executable. Available official legal material says
that binary must remain unmodified and run as published; this review found no
independent redistribution grant for republishing it from this mirror.

Therefore:

- Never commit `dist/`, wheel/sdist files, installer downloads, or a Claude
  Code executable. Reviewed portable wheel/sdist bytes may leave CI only
  through `.github/workflows/publish-portable.yml`; that workflow transfers
  them as a one-day artifact and publishes them to the selected package index.
- Upstream vendor-wheel and PyPI release jobs are repository-identity gated to
  `anthropics/claude-agent-sdk-python`; they must remain skipped in this public
  mirror even when a workflow is manually dispatched or a packaging PR opens.
- The inherited automated Claude review job is gated to that same official
  repository because it relies on Anthropic's GitHub App installation and
  workload-identity variables. Mirror pull requests use the ordinary test,
  lint, packaging, and provenance checks without impersonating that trust
  boundary.
- Inherited real-API E2E, Docker E2E, and example jobs are likewise limited to
  the official repository's WIF policy. Their skipped mirror status is not a
  business-test claim; this mirror's installed-package protocol checks and the
  separately recorded local Dream acceptance remain the applicable evidence.
- Every job in the inherited manual publish workflow is identity-gated, so a
  mirror dispatch skips before tests, vendor downloads, upload, tag, or push.
- The ordinary portable-package CI workflow has only `contents: read`, does not
  upload its ephemeral artifacts, and has no package-index, tag, release, or
  push step. The separate manual publish workflow grants `id-token: write` only
  to its protected `testpypi` and `pypi` environment jobs.
- Keep locally generated artifacts ignored and untracked. Package-index upload
  is allowed only for the reviewed portable SDK archives through the protected
  downstream workflow after Trusted Publisher and reviewer configuration.
- Do not publish mirror wheels that bundle the official CLI unless Anthropic
  gives explicit authorization covering that redistribution.
- Treat Claude Code binary publication as blocked pending explicit
  redistribution authorization. That binary restriction does not turn the
  separately verified MIT Python source archives into vendor-binary wheels.

The local portable build below excludes the vendor executable and validates
that exclusion by inspecting archive members. Generated archives remain
untracked; release publication uses only the protected workflow described in
the Chinese contract and `RELEASING.md`.

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

The unit-test and MCP-floor CI lanes use a full Git checkout because the
provenance test reads the exact pinned ancestor and its tree. A depth-1 pull
request checkout is insufficient and must not be used for those lanes.

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

For `0.2.143`, the builder accepts only these normalized artifact names and
checks the wheel's `Name`/`Version` metadata plus the sdist root:

```text
ink_claude_dream_agent_sdk-0.2.143-py3-none-any.whl
ink_claude_dream_agent_sdk-0.2.143.tar.gz
```

Default Hatch wheel and sdist targets explicitly exclude
`src/claude_agent_sdk/_bundled/claude` and `claude.exe`. The inherited upstream
`scripts/build_wheel.py` remains as provenance/tooling, but in this renamed
distribution it exits before downloading or building a vendor wheel. The
official-repository workflows retain an independent exact repository-identity
guard.

## 验证安装后的 SDK Runtime 双路径

在仓库外的新虚拟环境安装本地 portable wheel，确认官方 distribution
`claude-agent-sdk` 没有共存，然后运行：

```bash
python scripts/smoke_installed.py \
  --expected-version 0.2.143 \
  --official-cli /absolute/path/to/default/claude \
  --custom-runtime /absolute/path/to/standalone-clean-room-claude
```

smoke 工具会在规范化后的临时空 `HOME` 和环境变量白名单中重新执行。它检查已
安装 metadata 只存在 `ink-claude-dream-agent-sdk==0.2.143`，安装文件提供
`claude_agent_sdk` 且不含 vendor CLI；随后验证默认解析与显式 `cli_path` 分别指向
预期 executable。官方 CLI 只执行 `--version`，不会收到 prompt。

SDK 先通过本地固定 JSONL fixture 完成一轮 `query()`，再把同一个公开
`query()` 入口指向 standalone Runtime。第二轮由进程内 loopback HTTP fixture
返回固定 Anthropic SSE，证明 SDK → Runtime → provider 协议可用；不再把 fake
Claude core 注入 Runtime，也不复制 SDK 或 Dream 状态机。旧 envelope 回滚验收仍
可额外传入 `--custom-runtime-core`，但它不是 standalone Runtime 的发布门。

## 历史业务证据（不替代本次 standalone 验收）

On 2026-08-23 the unchanged SDK process contract was exercised by the
existing local Dream application through its public Deck → Chat → Dream UI,
current Admin/Gateway services, and current real PostgreSQL data. The same
existing actor and Deck passed twice: first with the unmodified official Claude
Code `2.1.241` executable selected directly, then with the historical envelope
Runtime selected through the existing CLI-path injection point and supervising
that same official executable. This historical result does not qualify the new
standalone clean-room Runtime or replace a new Dream business acceptance.

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
3. Confirm wheel `Name`/`Version`, exact wheel/sdist filenames and sdist root,
   then inspect both member lists and confirm no vendor executable is present.
4. Install the wheel outside the source tree and run the isolated smoke test.
5. Run `git status --short --ignored` and `git ls-files dist` to prove every
   artifact is ignored and untracked.
6. Inspect every vendor-wheel/release workflow and prove its official-repository
   identity guard remains effective; prove ordinary portable CI is read-only.
   Separately verify the downstream publish workflow has OIDC only in protected
   publish jobs and never invokes the vendor builder.
7. Do not commit generated archives. Do not create a production tag or approve
   package upload until source review, TestPyPI validation, GitHub Environment
   reviewer policy, Trusted Publisher identity, and applicable naming/license
   review are complete.
