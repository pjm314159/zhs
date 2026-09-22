<!--
感谢贡献！提交 PR 前请先阅读 docs/linter.md（代码规范与 Linter 配置），并确保 CI 全绿。
-->

## 关联 Issue

<!-- 使用 Closes / Fixes 关联，例如：Closes #123 -->

Closes #

## 变更描述

<!-- 说明改动背景、目的与实现思路 -->

## 变更类型

<!-- 与 Conventional Commits 的 type 对应（docs/linter.md §9.1），可多选 -->

- [ ] `feat` 新功能
- [ ] `fix` Bug 修复
- [ ] `docs` 文档变更
- [ ] `perf` 性能优化
- [ ] `refactor` 重构（非新功能 / 非修复）
- [ ] `style` 格式调整（不影响逻辑）
- [ ] `test` 测试相关
- [ ] `chore` 构建 / 工具 / 依赖变更
- [ ] `ci` CI 配置变更
- [ ] `revert` 回退提交

## 主要改动

<!-- 逐条列出关键改动，必要时标注文件路径或模块 -->

-

## 测试与验证

<!-- 说明如何验证本次改动；CLI / 行为变更请附上命令输出、日志或截图 -->

```bash
uv run ruff check src/ tests/           # Lint 检查
uv run ruff format --check src/ tests/  # 格式检查
uv run mypy src/ tests/                 # 类型检查
uv run pytest                           # 测试（默认跳过 integration）
```

## 破坏性变更

- [ ] 无
- [ ] 有（请在下方说明影响范围与迁移方式）

<!--
有破坏性变更时，commit 需使用 `feat(scope)!: ...` 或添加 `BREAKING CHANGE:` footer，
否则不会在 CHANGELOG 中标记。
-->

## 自查清单

- [ ] 已阅读并遵循 `docs/linter.md`
- [ ] Ruff lint 通过（0 errors），且已执行 `--fix` / `format` 处理格式问题
- [ ] Ruff format 检查通过（0 changes needed）
- [ ] mypy strict 检查通过（0 errors）
- [ ] pytest 全部通过（如有跳过 `integration` 标记的场景，已说明原因）
- [ ] 未引入 `asyncio` / `async def` / `await`（项目已全面同步化，统一用 `time.sleep` + `threading`）
- [ ] 公开函数具备完整类型注解；异常使用 `raise ... from e` 保留异常链
- [ ] 日志使用 `loguru`，且未输出 cookie / token / password / apiKey 等敏感信息
- [ ] 未在业务模块中调用 `logger.add()` / `logger.remove()`（日志配置统一在 CLI 入口）
- [ ] 涉及行为变更时已同步更新 `README.md` / `README_zh.md` / `docs/`
- [ ] commit 消息遵循 Conventional Commits（会自动进入 CHANGELOG）
