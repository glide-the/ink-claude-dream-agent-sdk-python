# 下游 Python SDK 发布指南

本文是 `ink-claude-dream-agent-sdk` 的权威发布合同。Python 导入名继续是
`claude_agent_sdk`，与上游接口保持一致；这个发行包不能与官方
`claude-agent-sdk` 同时安装在同一个 Python 环境中。

当前源码基线由 `packaging/upstream.json` 固定为上游 SDK `0.2.143`。默认
Hatch 构建和下游发布工作流只生成 MIT Python 源码的通用 wheel/sdist，明确
排除 `_bundled/claude` 和 `_bundled/claude.exe`。Claude Code CLI 必须作为
独立 Runtime 安装，并通过上游已有的 `ClaudeAgentOptions.cli_path` 或默认
`PATH` 解析接入；不得放入本 Python 包。

当前下游发行版本为 `0.2.144`。`packaging/upstream.json` 分开记录不可变的
上游源码版本与下游发行版本；`verify_upstream.py` 只允许
`src/claude_agent_sdk/_version.py` 的单行版本赋值与上游基线不同，其余
`src/` 字节必须继续完全一致。

## 发布工作流与信任边界

下游唯一允许的包索引发布入口是
`.github/workflows/publish-portable.yml`。它由人工 `workflow_dispatch` 触发，
只在仓库 `glide-the/ink-claude-dream-agent-sdk-python` 中运行：

1. 无 OIDC 写权限的构建 job 从完整 Git 历史检出源码。
2. 要求显式 `source_ref=v<version>`，并校验该不可变源标签指向当前
   checkout commit，且输入版本、`pyproject.toml` 和带模块 docstring 的
   `_version.py` 完全一致。workflow runner 必须也从 tag 触发；常规
   发布使用同一 `v<version>`，已存在源标签上的 workflow 修复只能使用
   新的不可变 `v<version>-publish.<n>` runner 标签，不得移动源标签。
3. 安装哈希锁定的构建工具，执行 `verify_upstream.py` 和
   `reproducible_build.py`，独立构建两次并要求字节级一致。
4. 执行 SHA-256、`twine check --strict`、归档成员检查，并拒绝 Claude CLI 和
   任何 `*.map` 文件；随后将一个 wheel、一个 sdist 和 `SHA256SUMS` 上传为
   保留一天的不可变 GitHub artifact。
5. 独立 smoke job 重新下载 artifact 副本，在全新虚拟环境安装 wheel。依赖
   安装会访问 Python 包索引，但只接触 smoke runner 的副本；公开 `query()`
   使用无凭据、无模型网络访问的本地 CLI fixture。联网依赖不能修改 artifact
   服务中由构建 job 保存的原始发布字节。
6. `publish-testpypi` 必须同时等待构建和 smoke 成功，并从 artifact 服务重新
   下载原始字节，而不是复用 smoke runner 的文件。
7. TestPyPI 发布后，`verify-testpypi` 从 TestPyPI JSON API 比较精确文件名和
   SHA-256，并重新下载 wheel/sdist 做逐字节摘要验证，生成 promotion receipt。
8. 只有该机器验证成功后，`publish-pypi` 才进入 `pypi` 人工审批，并将同一个
   GitHub artifact 的字节上传 PyPI。两个发布 job 才拥有 `id-token: write`；
   不配置 API Token、`TWINE_PASSWORD` 或 Anthropic 凭据。

工作流不创建或推送 Git tag、不创建 GitHub Release、不修改版本，也不启用
`.github/workflows/publish.yml`、`build-and-publish.yml` 中 Anthropic 官方发布
身份。那些继承工作流继续以
`github.repository == 'anthropics/claude-agent-sdk-python'` 锁死，不能作为镜像
发布入口。

## 首次启用前的外部配置

仅提交工作流不会自动获得发布权限。仓库管理员必须在 GitHub 和两个包索引
完成以下配置，并由另一位审核者复核：

### GitHub Environments

当前仓库已经创建名称严格匹配的两个 Environment，并把 deployment ref 限制为
`v*` tag：

- `testpypi`：required reviewer 为当前唯一管理员 `glide-the`，只允许 `v*`
  发布标签。
- `pypi`：required reviewer 为当前唯一管理员 `glide-the`，只允许 `v*`
  发布标签。

因为仓库当前只有一个 collaborator，GitHub 暂时无法同时实现“必须人工审批”
和“禁止触发者自审”；现配置选择保留人工审批且 `prevent_self_review=false`。
增加第二位可信 reviewer 后，必须立即切换为禁止触发者自审。此限制不影响
workflow 内的精确 tag/version、TestPyPI 字节提升和 OIDC 身份校验，但属于首次
正式发布前需要复核的外部控制面事项。

Environment 审批是人工发布安全门；YAML 只能声明 Environment 名称，不能替
仓库管理员建立或审计 required reviewers。2026-08-24 首次发布前，
TestPyPI 和 PyPI 的 pending Trusted Publisher 已按下述精确身份登记；
正式发布仍必须通过两个 Environment 审批和 workflow 的 OIDC 验证。

### TestPyPI Trusted Publisher

在 `https://test.pypi.org/manage/account/publishing/`（首次项目可用 pending
publisher）登记：

```text
Owner: glide-the
Repository: ink-claude-dream-agent-sdk-python
Workflow: publish-portable.yml
Environment: testpypi
Project: ink-claude-dream-agent-sdk
```

### PyPI Trusted Publisher

在 `https://pypi.org/manage/account/publishing/` 或项目 Publishing 设置登记：

```text
Owner: glide-the
Repository: ink-claude-dream-agent-sdk-python
Workflow: publish-portable.yml
Environment: pypi
Project: ink-claude-dream-agent-sdk
```

不得复用 Anthropic 官方项目的 publisher、API Token、GitHub Environment 或
Workload Identity Federation 配置。

## 发布步骤

1. 从已审查、工作区干净的提交确认：

   ```bash
   python scripts/verify_upstream.py
   python scripts/reproducible_build.py
   python -m twine check --strict dist/reproducible/*.whl \
     dist/reproducible/*.tar.gz
   ```

2. 为同一审核提交创建并推送 `v0.2.144` 源标签。从该标签手动运行
   `Promote Portable Downstream SDK`，输入 `version=0.2.144` 和
   `source_ref=v0.2.144`；工作流没有可直接选择 PyPI、跳过 TestPyPI 的
   target 参数。如果不可变源标签中的 workflow 本身存在发布前缺陷，
   在 `main` 修复并通过 CI 后创建新的 `v0.2.144-publish.1` runner 标签，
   从该 runner 标签以相同两个输入重跑。构建、smoke 和远端字节校验仍只
   checkout `source_ref`；禁止删除、移动或 force-update 原源标签。
3. 批准 `testpypi` Environment。工作流上传同一 artifact 后会自动校验
   TestPyPI 精确文件集合、元数据 SHA-256 和重新下载字节。也可以在等待 PyPI
   审批时额外人工下载验证：

   ```bash
   python -m pip download --no-deps \
     --index-url https://test.pypi.org/simple/ \
     'ink-claude-dream-agent-sdk==0.2.144'
   python -m pip install ./ink_claude_dream_agent_sdk-0.2.144-py3-none-any.whl
   python -c 'import claude_agent_sdk; print(claude_agent_sdk.__version__)'
   ```

4. 检查 `verify-testpypi` 输出的 `promotion_receipt`。只有该 job 成功后，非
   触发人才批准 `pypi` Environment；这不是一次独立重建，而是继续提升同一
   GitHub artifact。分支、错版本标签或版本文件不一致会在 TestPyPI 前失败。
5. 从 PyPI 新建环境安装精确版本，确认安装元数据名为
   `ink-claude-dream-agent-sdk`、导入名为 `claude_agent_sdk`，且安装文件中没有
   Claude CLI。随后再执行 Dream 的官方 CLI 与自定义 Runtime 两条业务验收。

包索引文件名不可覆盖，工作流也不使用 `skip-existing`。错误发布应停止后续
审批并按包索引治理流程 yank；修复必须使用新版本，不得试图覆盖原归档。

## 许可证和禁止项

- 本流程允许发布的只有经校验的 Python wheel/sdist；其源码许可证为 MIT。
- Anthropic Claude Code 可执行文件、恢复源码、用户 transcript、Workspace
  正文、插件物化数据、MCP/OAuth 凭据和环境变量不得进入归档或 GitHub
  artifact。
- JavaScript source map（任何 `*.map`）不得进入 wheel、sdist、GitHub artifact
  或包索引发布集合。
- `scripts/build_wheel.py` 是继承的官方 vendor-wheel 工具，在改名后的下游包
  会主动拒绝运行；下游发布工作流不得调用它或 `download_cli.py`。
- 公开项目前仍需仓库所有者确认项目名称、商标和当前发布条款；这不授权发布
  或修改 Claude Code 二进制。

当前合法的 `0.2.144` 便携产物名只能是：

```text
ink_claude_dream_agent_sdk-0.2.144-py3-none-any.whl
ink_claude_dream_agent_sdk-0.2.144.tar.gz
```

构建、安装 smoke、CLI path 和 Runtime 合同详见
[`docs/packaging/runtime-integration.md`](docs/packaging/runtime-integration.md)。
