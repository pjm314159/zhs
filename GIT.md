# Git 规范

> **提交代码前请先读本文件。** 这里是本仓库 Git / 分支 / 提交 / PR / 发布流程的唯一权威说明。
> 代码风格与 Linter 规则见 [docs/linter.md](docs/linter.md)，测试规范见 [docs/test.md](docs/test.md)，
> PR 描述必须按 [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md) 填写。

---

## 1. 分支模型

只有两条长期分支：

| 分支 | 用途 | 谁可以写入 |
|------|------|-----------|
| `dev` | 开发主线，所有功能在此集成 | 只能通过功能分支的 PR 合入 |
| `main` | 生产代码，随时可发布 | `dev` 合并 PR、发布准备 PR |

功能分支一律**从 `dev` 切出、合回 `dev`**，合并后删除：

| 前缀 | 用途 | 示例 |
|------|------|------|
| `feat/*` | 新功能 | `feat/ai-course-homework` |
| `fix/*` | Bug 修复 | `fix/session-cas-handshake` |
| `refactor/*` | 重构 | `refactor/split-cookie-restore` |
| `test/*` | 测试补充/修复 | `test/session-status-triad` |
| `docs/*` | 文档变更 | `docs/git-workflow-guide` |
| `chore/*` | 构建/工具/依赖、发布准备 | `chore/release-v0.1.5` |

```text
main ──── 稳定代码，接受 dev 合并 PR 与发布准备 PR
  ▲
  │ merge（发布准备 PR / dev → main 同步 PR）
  │
dev ──── 开发主线，功能集成
  ▲
  │ merge（PR，base 必须为 dev）
  │
feat/xxx, fix/xxx, docs/xxx ... ── 从 dev 切出，完成后合并回 dev
```

**常见错误**：把 PR 的 base 选成 `main`（应为 `dev`）；直接在 `dev` 上 commit；从 `main` 切功能分支；合并后留着旧分支。

> 远程操作（`git push`、开/合 PR、发布）属于对外变更，执行前请与仓库维护者确认。

---

## 2. Commit 消息：Conventional Commits

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### type（必填）

| type | 说明 | changelog 分组 |
|------|------|---------------|
| `feat` | 新功能 | Features |
| `fix` | Bug 修复 | Bug Fixes |
| `docs` | 文档变更 | Documentation |
| `perf` | 性能优化 | Performance |
| `refactor` | 重构（非新功能/非修复） | Refactor |
| `style` | 格式调整（不影响逻辑） | Styling |
| `test` | 测试相关 | Testing |
| `chore` | 构建/工具/依赖变更 | Miscellaneous |
| `ci` | CI 配置变更 | Miscellaneous |
| `revert` | 回退提交 | Reverted |

### scope（可选）

常用：`release`、`deps`、`config`、`crypto`、`session`、`cli`、`homework`、`video`、`ai`。

### 示例

```text
feat(homework): add AI exam answer submission
fix(session): 探活前用 CAS 换票建立 onlineservice 会话
docs: 同步超时配置与登录态判定说明
chore(deps): bump ruff to v0.15
ci: add release workflow with git-cliff
```

### 破坏性变更

提交里必须带 `!` 或 `BREAKING CHANGE:` footer，否则 `CHANGELOG.md` 不会标记：

```text
feat(api)!: change homework submit response format

feat(api): redesign config structure

BREAKING CHANGE: config.toml structure has changed, see docs for migration
```

提交粒度建议：功能 / 测试 / 文档可拆开提交，但**每个提交都要能独立跑绿**；无法拆成能独立通过的小步时合并提交。

---

## 3. Pull Request

1. 推送功能分支：`git push -u origin <branch>`。
2. 开 PR，**base 必须是 `dev`**，head 是功能分支。
3. 描述按 `.github/PULL_REQUEST_TEMPLATE.md` **逐段填写**：关联 Issue、变更描述、变更类型、主要改动、测试与验证、破坏性变更、自查清单。不要换成自由格式，也不要漏勾自查项。
4. 无关联 Issue 时说明原因，不要写无效的 `Closes #`。引用已关闭的贡献 PR 用 `#N` 普通引用即可。
5. 审阅通过后合并，删除功能分支。

PR 自查清单对应的本地门禁：

```bash
uv sync --dev
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/ tests/
uv run pytest
```

`pyproject.toml` 的 `addopts` 默认 `-m 'not integration'`；集成测试需要真实 API 与扫码登录，单独跑：

```bash
uv run pytest -m integration tests/integration/
```

CI 实际执行 `.github/workflows/ci.yml`：Python 3.13 / 3.14 矩阵、四项检查、`tests-gate` 门禁和 wheel 安装冒烟（`user-install`）。

---

## 4. Tag 与发布

| 规则 | 说明 |
|------|------|
| 格式 | `v<major>.<minor>.<patch>` 或四段 `v<major>.<minor>.<patch>.<hotfix>`（如 `v0.1.4`、`v0.1.2.2`） |
| 位置 | 在 `main` 上打 tag |
| 触发 | 推送 tag 自动触发 `release.yml` |
| 版本号 | 与 `pyproject.toml` 的 `version` 一致 |

### 发布流程（CHANGELOG 在打 tag 前生成）

```text
1. 在 dev 上开发、测试（功能分支 → dev）
2. Actions → Prepare Release → Run workflow，输入版本号（如 0.1.5）
   自动：bump pyproject.toml version（含 uv.lock 中本包自身版本）+ git-cliff 生成 CHANGELOG.md 新段落
   自动：推送 chore/release-vX.Y.Z 分支并开 PR 到 main（标题 release: vX.Y.Z）
3. 审阅并合并发布 PR（CHANGELOG 内容在此审阅）
4. 在 main 上打 tag 并推送：
   git checkout main && git pull && git tag v0.1.5 && git push origin v0.1.5
5. CI（release.yml）：check → release notes → build → GitHub Release → PyPI
   → 末尾尝试把 main 快进同步回 dev（best effort）
```

**为什么在打 tag 前生成**：`main` 受规则集保护（`pull_request` 规则 + 无 bypass actor），机器人只能把提交推到 `dev`；改为发布前生成后，不再需要「发布后补写 CHANGELOG」的收尾 PR。

**注意**：发布提交（版本号 + CHANGELOG 段落）只落在 `main`，因此 `release.yml` 末尾会把 `main` 快进同步回 `dev`；该步骤允许失败（`dev` 有新提交时会拒绝非快进），失败时需人工补一次同步 PR。

**依赖设置**：Prepare Release 需要仓库允许 Actions 创建 PR —— Settings → Actions → General → Workflow permissions → 勾选 *Allow GitHub Actions to create and approve pull requests*（未开启时分支仍会推送，工作流会打印手动开 PR 的 compare 链接）。

### Changelog 自动化

[git-cliff](https://git-cliff.org) 配置在 `cliff.toml`；`prepare-release.yml` 在发布前生成 `CHANGELOG.md`，`release.yml` 在推送 tag 时生成 Release notes。**不要手工编辑 `CHANGELOG.md`。** 标签尚不存在时必须带 `--unreleased`。

```bash
# 预览下一个版本段落（标签还不存在）
uvx --from git-cliff git-cliff --config cliff.toml --unreleased --tag v0.1.5 --strip header
# 预览/写入完整 CHANGELOG（针对已存在的标签）
uvx --from git-cliff git-cliff --config cliff.toml --tag v0.1.4 -o CHANGELOG.md
```

---

## 5. 一眼看懂的检查表

- [ ] 功能分支从最新 `dev` 切出，命名符合 `<type>/<short-description>`
- [ ] commit 消息遵循 Conventional Commits，每个提交可独立跑绿
- [ ] `uv run ruff check` / `ruff format --check` / `mypy` / `pytest` 全过
- [ ] PR base 是 `dev`，描述按 PR 模板逐段填写，自查项已勾
- [ ] 行为变更已同步 `README.md` / `README_zh.md` / `docs/`
- [ ] 远程操作（push / 开 PR / 合并 / 发布）已与维护者确认
