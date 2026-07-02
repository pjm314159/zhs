# 开发日志

记录每个 Task 的 TDD 循环状态（Red / Green / Refactor）与完成情况。

---

## 题库（Question Bank）功能

外部题库查询（enncy.cn）集成，作为 LLM 答题的提示源。
方案文档：`.trae/documents/question_bank_feature.md`
API 参考：`.temp/questions_bank.md`

### Task 1 — 文档完善 → `.temp/questions_bank.md` ✅
- Red: —
- Green: 完善版写入 `.temp/questions_bank.md`（查询/信息接口、功能规格、设计决策）
- Refactor: —
- 备注：多答案以 `\n` 分隔；`#` 为污染字符（解析时清除）；URL 字段重命名为 `query_url`/`info_url`，置于 `[question_bank]` 段

### Task 2 — 配置层 `QuestionBankConfig` ✅
- Red: `tests/test_config.py::TestQuestionBankConfig`（默认值/自定义/非法 scope/TOML 加载/roundtrip）
- Green: `src/zhs/config.py` 新增 `QuestionBankConfig` + `AppConfig.question_bank` + TOML 分支
- Refactor: ruff/mypy 通过
- 同步: `config.toml.example` 新增 `[question_bank]` 段

### Task 3 — models `QuestionBankResult` / `map_question_type` ✅
- Red: `tests/question_bank/test_models.py`（`format_hint` 单/多答案/空/ai；题型映射 1/2/3/14/unknown）
- Green: `src/zhs/question_bank/models.py`
- Refactor: ruff/mypy 通过

### Task 4 — client `QuestionBankClient` ✅
- Red: `tests/question_bank/test_client.py`（`with respx.mock:` — 成功/无答案/参数/info 缓存/times=0 跳过/重试/malformed/5xx）
- Green: `src/zhs/question_bank/client.py`（`query`/`get_info`/`_get_with_retry`/`close`，独立 `httpx.Client`）
- Refactor: ruff/mypy 通过

### Task 5 — bootstrap `init_question_bank` ✅
- Red: `tests/cli/test_bootstrap.py::TestInitQuestionBank`（disabled/no-token/ai-disabled/scope-mismatch 返 None；全开返 client）
- Green: `src/zhs/cli/bootstrap.py` 新增 `init_question_bank(config, scope)`
- Refactor: ruff/mypy 通过

### Task 6 — AI exam_base 注入 ✅
- Red: `tests/ai/test_exam_base.py::TestQuestionBankInjection`（bank None/命中/无答案/异常/缓存命中跳过/provider None/查询参数）
- Green: `src/zhs/ai/exam_base.py` — `__init__` 加 `question_bank` 参数；`_build_extra` 注入 `extra["题库参考"]`；`_query_question_bank` 查询+格式化
- Refactor: ruff/mypy 通过

### Task 7 — 知到 worker 注入 ✅
- Red: `tests/zhidao/homework/test_worker.py::TestQuestionBankInjection`（6 用例）
- Green: `src/zhs/zhidao/homework/worker.py` — `__init__` 加 `question_bank` 参数；`_generate_answer_with_llm` 注入 hint
- Refactor: ruff/mypy 通过

### Task 8 — 子类转发 + 服务层接线 ✅
- Red: `tests/ai/test_homework.py` + `tests/ai/test_exam.py`（`question_bank_forwarded` / `defaults_none`）
- Green:
  - `src/zhs/ai/homework.py` + `src/zhs/ai/exam.py` — 转发 `question_bank` 到 `super().__init__`
  - `src/zhs/cli/services/homework_service.py` — zhidao/AI 作业站点接线（scope=`zhidao_homework`/`ai_homework`）
  - `src/zhs/cli/services/exam_service.py` — AI 考试站点接线（scope=`ai_exam`）
  - `src/zhs/ai/course.py` — `run_course`/`_run_homework_only` 透传 `question_bank`
- Refactor: ruff/mypy 通过

### Task 9 — CLI `--no-question-bank` 旗标 ✅
- Red: `tests/cli/test_main.py` — `test_homework_no_question_bank_disables_bank` + `test_exam_no_question_bank_disables_bank`（断言 `config.question_bank.enabled is False`）
- Green: `src/zhs/__main__.py` — `homework` + `exam` 命令加 `--no-question-bank` 参数；CLI 覆盖块 `if no_question_bank: config.question_bank.enabled = False`
- Refactor: ruff check/format + mypy 全绿；`tests/cli/test_main.py` 32 用例全通过

---

## Phase 完成校验（题库功能）

- `pytest`（全量）: **1047 passed, 49 deselected** ✅
- `ruff check src/ tests/`: **All checks passed** ✅
- `ruff format --check src/ tests/`: **148 files already formatted** ✅
- `mypy src/ tests/`: **no issues found in 148 source files** ✅

---

## Bug 修复：zhidao_ai 误伤知到作业 + 题库不可用提示

### Bug 1 — `init_llm` 误判 `use_zhidao_ai` 导致知到作业无 LLM ✅
- **现象**：`ai.use_zhidao_ai=True` 时，知到作业 `init_llm` 返回 None（无 LLM，退化为随机答题）。
- **根因**：`init_llm`（仅知到作业调用）`if ai.use_zhidao_ai: return None` 短路；但 `zhidao_ai` 设计上仅在 AI 智慧课程生效（由 `LLMProviderFactory.create` 创建 `ZhidaoAIProvider`），知到课程应忽略它。
- **修复**（[bootstrap.py](file:///e:/project/python/ZHS/src/zhs/cli/bootstrap.py)）：移除 `use_zhidao_ai` 短路，知到作业仅检查 `ai.enabled` + `api_key`，有 key 则用 OpenAI。
- TDD: `test_use_zhidao_ai_ignored_returns_provider`（RED→GREEN），`test_use_zhidao_ai_no_api_key_returns_none`。

### Bug 2 — 题库不可用仅 log 不 print ✅
- **现象**：`init_question_bank` 在 token 空 / AI 未启用时只 `logger.warning`，终端不可见（非 debug 模式无 stderr handler）。
- **修复**（[bootstrap.py](file:///e:/project/python/ZHS/src/zhs/cli/bootstrap.py)）：两个分支追加 `print(msg_warn(...))`，与 `logger.warning` 并存。
- TDD: `test_no_token_returns_none` / `test_ai_disabled_returns_none` 增加 `capsys` 断言（RED→GREEN）。

### 校验
- `pytest`（全量）: **1048 passed, 49 deselected** ✅
- `ruff check` + `format --check` + `mypy`: 全绿 ✅

---

## 功能增强：题库使用统计 + 完成提示

### Task 12 — 题库统计属性 + 成功 log ✅
- **需求**：每次题库查询成功后 log 提示用户，统计成功次数/总查询次数。
- **实现**（[client.py](file:///e:/project/python/ZHS/src/zhs/question_bank/client.py)）：
  - 新增 `_success_count`、`_total_queries` 属性
  - `query()` 成功（code=1）时 `logger.info(f"题库查询成功: 剩余次数 {times}, 本次使用 1 次（累计成功 {success_count} 次")`
  - 新增 `get_usage_stats()` 返回 `(success, total)` 元组
- TDD: `TestUsageStats` 7 用例（初始值、成功增量、无答案增量、错误增量、times=0跳过、get_usage_stats、log验证）

### Task 13 — 完成时 print 统计 ✅
- **需求**：作业/考试完成时 print "题库使用: 成功 X 次 / 总查询 Y 次"。
- **实现**：
  - [worker.py](file:///e:/project/python/ZHS/src/zhs/zhidao/homework/worker.py) `run_homework` return 前：`self._reporter.print(msg_info(f"题库使用: 成功 {success} 次 / 总查询 {total} 次"))`
  - [course.py](file:///e:/project/python/ZHS/src/zhs/ai/course.py) `_run_homework_only` 结束前：`self._reporter.tree_print(msg_info(stats_msg), depth=3)`
  - 仅当 `question_bank` 存在且 `total > 0` 时显示（避免无查询时打印无意义信息）
- TDD: `test_run_homework_prints_bank_stats` 验证 capsys.out 包含统计数字

### 校验
- `pytest`（相关）: 12 passed (worker + client) ✅
- `ruff check` + `format --check` + `mypy`: 全绿 ✅

