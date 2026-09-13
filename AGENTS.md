<!-- [Input] Dream governance, pinned upstream Python source and portable downstream packaging contracts. -->
<!-- [Output] Mandatory repository instructions for agents maintaining the Python SDK mirror. -->
<!-- [Pos] Root governance; CLAUDE.md supplies complementary commands, not an alternative product architecture. -->
<!-- [Sync] 2026-09-13: adapt Dream AGENTS to upstream parity, PyPI promotion and SDK/Runtime separation. -->
<!-- [Sync] 2026-09-13: require precise programming terminology and keep retired architectures out of current designs. -->

# Python SDK AGENTS Instructions

本仓库维护便携 Python SDK 镜像，发行名为 `ink-claude-dream-agent-sdk`，导入名固定为 `claude_agent_sdk`。变更前阅读本文件、[README](README.md)、[CLAUDE 命令指南](CLAUDE.md)、[根目录合同](.folder.md)及受影响目录的合同。

## 职责与事实来源

- `src/claude_agent_sdk/`维护上游 SDK 公开 API、client/query/types、subprocess transport、消息解析及协议；不得新增 Dream 业务状态机或 Runtime 实现。
- [packaging/upstream.json](packaging/upstream.json)是源码 commit/tree/license、上游版本和下游发行版本的机器合同；[pyproject.toml](pyproject.toml)与 `_version.py`提供下游实际版本。
- [RELEASING.md](RELEASING.md)是中文权威发布合同；[packaging 合同](packaging/README.md)与 [docs/packaging 合同](docs/packaging/README.md)限定构建和文档职责；`.github/workflows/`决定实际 CI 与发布行为。
- Runtime 由 `glide-the/ink-claude-code-dream`独立构建并经 npm 安装；Dream 由 `glide-the/im-dream`管理 DTO、笔记/线程映射、权限、身份及宿主 UI；共享数据库 schema 仅属 Admin Drizzle。本仓库不创建 Dream schema、SQLite fallback 或数据库修复通道。
- 历史 CLI、404 或发布进度回执只在其标注版本/日期内成立；不把历史文档当作已发布版本或当前服务状态。冲突以机器 pin、权威发布流程与实际可验证回执定位并修正文档。

## 源码同步与最小设计

- 先用 `rg`复用已有入口和脚本。需要设计评审的实现/架构变更，方案包括“背景与问题、目标与边界、概念与规则”；小型文档修正无需新增设计稿。评审影响范围，不为已满足的目标制造实现改动。
- 保持上游目录、import namespace、公开 API、options、异步流、权限/hook、MCP 和 transport 语义；不新建包装 SDK、复制 parser/状态机或设计 Dream 专属协议。
- 依照 `verify_upstream.py`保持精确来源一致。目前仅允许 `_version.py`单行下游版本赋值与基线不同；不得批量格式化或改写上游源码、通过更新 provenance 掩盖差异。功能分叉或扩大例外需用户明确批准及完整来源/API 评审。
- 上游升级先审查完整历史、tree/license/API 和可验证 Git ref，再同步 provenance、版本及验证；包索引更高版本号不自动代表可审计源码基线。不写入或修改参考 checkout。
- 不按 development/test/production 标签改变 SDK 行为；fixture、fake transport/provider、clock 与隔离资源限于 tests、e2e-tests 或明确命名的验证脚本，通过公开 API 验证。
- 若已符合目标，只修正文档、概念命名和缺口测试；不要将消费端的数据库/cwd/PATH 问题挪到 SDK 解决。

## SDK、Runtime 与权限边界

- SDK 只提供既有 `ClaudeAgentOptions.cli_path`、PATH 解析与子进程协议；不下载、安装、捆绑或悄悄升级 Runtime，不增加 npm 安装 hook。Dream 的严格 Runtime 选择和 manifest gate 留在 Dream，独立 SDK 保持上游选择语义。
- `ClaudeSDKClient`的 CLI session/resume 参数不是 Dream note session ID。笔记 ID 只属笔记业务；Dream thread 到 Claude session 的数据库映射、当前项目 transcript 判定与新会话回退由 Dream 管理，不注入 SDK。
- 不将 `allowed_tools`误写为工具可见性或全量回调 gate；whole-tool allow 会自动批准，可能遮蔽 `can_use_tool`。按真实权限语义评估 hooks/permission mode，不为消除警告取消安全检查。
- 不增加发送后重试、重放工具、隐藏错误或自动跨 cwd/home 找旧会话。CLI initialize、query、receive、cancel 的失败边界必须保留，跨组件变更先评审消费端完整流程。
- Dream 接入时尊重服务端 env/cwd/home/tmp、Notion 原生子进程隔离和模型配置所有权；不得从 ambient env、workspace、插件或浏览器旁路注入秘密与受控配置。不要把 Dream 的绑定协议强制成所有独立 SDK 用户的业务策略。

## 版本与依赖

- 当前下游发行 `0.2.145`、上游源码 `0.2.143`、CLI compatibility `2.1.241`是不同概念；当前 Dream 使用 Runtime `0.1.9`。以后从机器合同读取，不能以同名或大小关系推断兼容。
- 升级下游版本时原子同步 `pyproject.toml`、`_version.py`、provenance 的 downstream 字段及受影响 README/发布文档与测试；仅更新事实确实变化的合同，不为同步而改动未受影响文件。上游版本不因下游发版而伪造变化。
- Dream 采用新 SDK 时另在 Dream 同步 pyproject、uv.lock、带 archive hash 的 requirements、Docker、resolver/tests、英中文 README 及相关 folder/design 文件；源码升级不等于消费端已安装。
- `uv`/PyPI 仅管 Python SDK；npm 仅管 Runtime。官方 `claude-agent-sdk`与本发行包不能共存，因为提供同一导入目录；验证唯一 distribution provider、准确版本且无 Git `direct_url.json`，不靠 import 成功判断发行身份。
- 开发/测试依赖使用已声明组或明确临时命令；不依赖 ad-hoc 包永远留在 `uv sync`后的环境中，也不擅自放宽 Python/MCP 支持范围。

## 打包与发布

- 只发布 MIT Python wheel/sdist，不包含 Runtime、`_bundled/claude`、`claude.exe`、任何 `.map`、凭据、transcript 或 Workspace。保留源码版权；本合同不授权重新分发 Claude Code。
- 使用 hash-locked Python 3.12 构建工具，精确上游验证、两次独立可复现构建、成员检查、SHA-256 和 `twine check --strict`。生成物留在 Git-ignored 输出目录，不提交到 Git 或 packaging 输入目录。
- 唯一下游索引发布入口为 `.github/workflows/publish-portable.yml`：显式不可变 `source_ref=v<version>`，同一组字节通过 TestPyPI 上传/远端摘要验证后，才经受保护 PyPI Environment/OIDC 提升。普通 CI 只读、不发布；不启用继承的 Anthropic 官方仓库发布身份或跳过审批。
- 发布 runner 修复使用新的不可变 `v<version>-publish.<n>`标签作为 workflow 运行 ref，源码输入仍固定原 `source_ref=v<version>`，产物身份不变；保留原 source tag，不 force-update、不改旧版本、不覆盖现有索引文件、不以 `skip-existing`掩盖来源不一致。
- 已发布精确版本先比对文件名、大小、摘要和元数据，复用合格制品，不重复上传/重建。文档-only 不自动授权新版本、源标签、workflow dispatch 或 package upload。
- 不用 argv、日志、文档、commit、artifact 暴露 registry/API/OAuth 凭据；CI/OIDC 与既有保护门禁是授权入口。

## 文档同步

### 通用产品设计原则与用语（强制）

- 不得增加“可信”“不可信”“物化”等含糊概念标签或抽象符号；它们不能定义程序行为，只会增加理解成本。已有设计按实际语境改为身份认证、授权校验、schema 校验、参数传递、数据转换、文件生成、持久化等专业用语，明确模块、输入输出、条件和失败处理。
- 相关项目的功能变更必须同步受影响设计稿，采用“背景与问题、目标与边界、概念与规则”，规则对应真实业务约束；覆盖正常流程、状态转换、失败反馈、影响范围和验收，不把技术常量当产品限制，不增加无决策价值的说明、确认或架构。
- 配置型设计写明 default、desired、effective、revision 及转换条件。正文、表格和时序图保持一致；保留实际代码/协议标识符和官方名称，不为文档清理改变 SDK API。
- 废弃方案从当前设计稿与索引删除；历史追溯使用 Git 或已有执行回执，不在当前设计中保留废弃架构说明。

- 任何功能、架构、安装、命令、版本、路径或安全合同变化，同轮更新 README、RELEASING/受影响设计、已有文件头和目录合同；packaging 目录使用现有 README 合同，不制造重复权威文件。
- 根 `.folder.md`维护入口清单；适用目录已有 `.folder.md`时同步。上游源码头也属 parity，说明放在下游脚本/文档，不为同步要求污染 `src`原始字节。
- README 是使用指南，历史验收按日期/版本标注；新增文档明确 owner/current/historical，不把 fixture、用户确认、未触发或 skipped CI 写成自动化真实业务通过。
- 不凭空新增本仓库不存在的中文 README 镜像；若维护多语言文件，保持版本、命令、结构与事实一致。

## 影响评估与验证

- 测试前列出公开 API、transport/options、协议/permissions/resume/MCP、包成员、支持版本和 Dream 消费端的受影响面；按完整受影响流程安排测试，不能只参考当前报错。
- 文档-only 核对 Markdown 链接、文件/脚本/版本事实与 `git diff --check`，不无故重建制品或调用真实模型。
- 代码/脚本变更按范围运行 `python -m ruff check src/ tests/ scripts/`、`python -m ruff format --check src/ tests/ scripts/`、`python -m mypy src/ scripts/`及 `python -m pytest tests/`或相关测试。禁止对整个上游树自动 `--fix`或格式化以掩盖不相关问题。
- 来源/打包变更增加 `python scripts/verify_upstream.py`、`python scripts/reproducible_build.py`和安装后的 `scripts/smoke_installed.py`适用 lanes；provenance 测试保留完整 Git 历史。需要工具或 CLI fixture 时按现有指南显式配置，不静默下载 vendor binary 或真实联网模型。
- Provider-free 协议/包验证与真实业务验收分开。用户要求真实业务时按 Dream AGENTS 走正常本机 Dream/Admin/Gateway/PostgreSQL、指定现有账户/实体及公开业务入口，留下正常 Admin 可查的业务和结算回执；隔离数据库、影子账户或 fake provider 不冒充真实链路。
- 浏览器优先现有 Chrome；runner/secret/依赖缺失如实记录为前置失败，不改变生产行为或放宽权限。最终列命令、exit code、pass/skip/fail、未执行项及 Git/PR/制品状态。

## 工作区与进程

- 不覆盖用户或其他 Agent 的未提交改动、不全局格式化、不 reset/force-push/强行合并；跨仓库修复留在各 owner 项目，扩大任务前取得授权。
- 不提交凭据、用户正文、环境完整值、CLI 下载、wheel/sdist 或临时回执中的敏感内容。
- 清理仅限本轮明确创建且验证身份的资源；不停止正常 Dream/Admin/MCP/PostgreSQL 或用户已有 SDK 进程。主分支切换尊重 linked worktree 占用。
