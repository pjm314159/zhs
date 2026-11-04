# Changelog

All notable changes to this project will be documented in this file.

## [0.1.5] - 2026-11-04

### Features

- **ai**: KnowledgePoint 解析 freeExam 免考标记
- **homework**: 可配置是否跳过免考知识点
- **ai**: 流式总超时与空闲超时可配置并校验大小关系

### Bug Fixes

- **ai**: 归一化非文件类资源的 resourcesFileId 空值
- **ai**: FreeExam 空值归一为 0
- **session**: 探活前用 CAS 换票建立 onlineservice 会话

### Documentation

- **design**: 修复 Prompt 模板 Mermaid 图节点标签反引号渲染错误
- 补充免考跳过与作业配置项说明
- 更新 Cookie 恢复与登录态校验说明
- 同步 CAS 换票的会话校验流程
- 同步超时配置与登录态判定说明
- 新增 GIT.md 并清理过时与失效的文档描述
- 重组 design 章节并移除 linter 中的 Git 规范正文
- 将 GIT.md 移入 docs 并修正引用路径

### Refactor

- **cache**: 移除已弃用的 BaseQuestionCache JSON 缓存基类
- **ai**: 统一知识点遍历并修复直接模式主题缺失
- **cli**: 拆分 Cookie 恢复与会话校验

### Testing

- **cli**: 覆盖会话校验三态与本地 Cookie 恢复

### Miscellaneous

- 修正发布工作流注释中的 Git 规范引用

## [0.1.4.3] - 2026-10-14

### Bug Fixes

- **zhidao**: 原样发送弹窗题 questionIds，修复 lessonPopupExam 返回 -1
- **ci**: Pin Python version range so lxml stops building from source
- **zhidao**: 修复进度条 answering 不可达，补弹窗题调试日志
- **zhidao**: 停机原因写入日志文件，不再只打 stdout
- 补齐 Hike/CLI 的停机与失败日志

### Documentation

- Add GitHub project links to package metadata and a star request to READMEs
- Add package project links, README star request, and tidy pyproject comments
- Add project links and star request
- **zhidao**: 同步弹窗题 questionIds 的真实类型
- 记录 -12 停机日志可观测性与真机实测，教程补验证码恢复路径（Q11）

### Styling

- 删掉复述代码的注释

### Miscellaneous

- 新增 tests-gate 聚合门禁，固定 Tests & Coverage 检查名以匹配分支规则集

### Reverted

- Remove project urls and README star request

## [0.1.4.2] - 2026-09-23

### Features

- **cli**: Add zhs --version / -v backed by package metadata
- **cli**: Add zhs --version / -v and sync dev after release

### Testing

- **cli**: Strip ANSI codes when asserting --version appears in help
- **cli**: Make --version help assertion robust to ANSI colors

### Miscellaneous

- **release**: Fast-forward dev after publish and keep uv.lock version in sync

## [0.1.4.1] - 2026-09-23

### Bug Fixes

- **release**: Keep single blank line when inserting changelog section
- **release**: Accept 3- or 4-segment versions when preparing a release

### Documentation

- Highlight pip install zhs as the quickest start and document new release flow

### Miscellaneous

- **release**: Generate changelog before tagging via prepare-release workflow

## [0.1.4] - 2026-09-22

### Features

- **question_bank**: External question bank integration as LLM hint source
- **cli**: Accept only courseId for -c and resolve zhidao ids in one lookup (**BREAKING**)
- **video**: Precheck heartbeat before playback to surface captcha and time limit
- **config**: Rename use_zhidao_ai to use_builtin_ai and surface the effective AI provider (**BREAKING**)

### Bug Fixes

- Fix the zhidao progress bar and print chapter problems
- Try to add some anti-detection to prevent detection
- **config**: Remove duplicate QuestionBankConfig introduced by merge
- **homework**: Label degraded random answers and limit LLM retries to retryable status codes
- **llm**: Stop reader and close stream after early termination

### Documentation

- Add pull request and issue templates
- Update -c/--url parameter semantics

### Refactor

- SQLite 缓存重构 + CLI 命令式接口 + BeautifulSoup HTML 清洗

### Testing

- **cli**: Cover courseId-only -c and single-lookup resolution

### Miscellaneous

- **release**: Publish only latest changelog to release notes
- Bump version to 0.1.4
- **release**: Publish to PyPI first and write changelog back to dev
- **release**: Publish to PyPI before changelog sync

### Release

- V0.1.4（-c 参数语义、开播验证码预检、AI 答题失败可见性、LLM 流关闭）

## [0.1.3] - 2026-09-16

### Features

- **video**: Randomize playback speed and report interval to evade risk control

### Bug Fixes

- **video**: Repair corrupted import line in video.py

### Miscellaneous

- Bump version to 0.1.3

## [0.1.2.2] - 2026-09-02

### Bug Fixes

- Resolve mypy type errors in test files
- Correct mock URL in test and add empty course check in try_restore_cookies
- Avoid infinite redo loop by consuming attempt quota in homework worker

### Documentation

- Translate README to English and add Chinese version

### Miscellaneous

- Bump version to 0.1.2.2

## [0.1.2.1] - 2026-06-24

### Features

- Initial project setup
- **homework**: Add zhidao homework feature
- **homework**: AI homework sync refactor, python-pptx, fix all tests
- **homework**: Add AI course exam function
- **homework**: AI play/homework decouple + schedule/threshold progress control
- **release**: Add git-cliff changelog automation, bump version to 0.1.1

### Bug Fixes

- **homework**: Update config and fix print format
- Resolve ruff lint errors in test file
- Update tests for new nested config structure
- **video**: Squash merge refactor/performance - video progress regression fix + P0 cleanup
- **deps**: Fix develop dependency
- **ci**: CI compatibility - mypy cross-platform, uv.lock dev deps, dependency-groups
- Ppt workflow fix
- 统一缓存key格式、滑块验证立即停止、AI play资源进度条
- Hike API 测试字段名修正 (status → code)
- Fix the version
- Fix the version
- Fix the version

### Documentation

- Update README with pip install and custom AI recommendation

### Refactor

- **cli**: Merge from refactor/cli branch
- Restructure project layout

### Styling

- Format homework_service.py
- Format homework_service.py

### Testing

- Add more tests

### Miscellaneous

- Update .gitignore

## [0.1.2] - 2026-06-24

### Bug Fixes

- 统一缓存key格式、滑块验证立即停止、AI play资源进度条

### Documentation

- Update README with pip install and custom AI recommendation

### Styling

- Format homework_service.py

### Miscellaneous

- Bump version to 0.1.2
- Bump version to 0.1.2

## [0.1.1] - 2026-06-23

### Features

- Initial project setup
- **release**: Add git-cliff changelog automation, bump version to 0.1.1

<!-- generated by git-cliff -->
