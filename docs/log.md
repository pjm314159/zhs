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

---

## 知到考试（Zhidao Exam）预开发

知到课程考试功能预开发，基于已抓包确认的 `getStudentFinalExam` API 实现考试列表扫描。
方案文档：`.temp/zhidao_exam_plan.md`，API 文档：`.temp/zhidao_exam_api.md`

### Task 1 — URL 配置 ✅
- Red: —（基础设施配置）
- Green: `src/zhs/config.py` `UrlConfig` 新增 `taurusexam` 字段
- Refactor: ruff/mypy 通过

### Task 2 — 加密查询策略 ✅
- Red: —（表驱动配置）
- Green: `src/zhs/api/encrypted_query.py` `STRATEGIES` 新增 `zhidao_exam` 策略（exam_key, 无 dateFormate, status="200"）
- Refactor: ruff/mypy 通过；与 `homework` 策略仅 base_url 不同

### Task 3 — 数据模型 ✅
- Red: `tests/zhidao/exam/test_models.py`（ExamInfo.from_api 驼峰转蛇形 + ExamListResult.pending 筛选）
- Green: `src/zhs/zhidao/exam/models.py` `ExamInfo` + `ExamListResult`（含 `all`/`pending` 属性）
- Refactor: ruff/mypy 通过

### Task 4 — API 层 ✅
- Red: `tests/api/test_zhidao_exam_api.py`（respx mock getStudentFinalExam，flag=1/0，status="200" 校验，错误状态抛 ApiError）
- Green: `src/zhs/api/zhidao_exam_api.py` `ZhidaoExamApi.get_student_final_exam`
- Refactor: ruff/mypy 通过；返回 `rt` 数组（与作业的 rt 对象结构不同）

### Task 5 — Scanner ✅
- Red: `tests/zhidao/exam/test_scanner.py`（scan_exams 合并 flag=1/0，返回 ExamInfo，异常容错，flag 参数校验）
- Green: `src/zhs/zhidao/exam/scanner.py` `ExamScanner`（含 SSO 认证 + 异常容错）
- Refactor: ruff/mypy 通过

### Task 6 — Session 方法 ✅
- Red: 随 Task 5 测试验证（MagicMock spec=ZhsSession 需要方法存在）
- Green: `src/zhs/session.py` 新增 `zhidao_exam_query` + `exam_list` 委托方法，`__init__` 实例化 `ZhidaoExamApi`
- Refactor: ruff/mypy 通过

### Task 7 — 模块导出 ✅
- Green: `src/zhs/zhidao/exam/__init__.py` 导出 ExamInfo/ExamListResult/ExamScanner；`src/zhs/api/__init__.py` 导出 ZhidaoExamApi
- Refactor: ruff/mypy 通过

### Task 8 — 测试 ✅
- 16 个测试全绿：models 6 + scanner 6 + API 4
- 回归：CLI 32 + homework scanner/models 27 全绿

### Task 9 — CLI 预支持 ✅
- Green: `src/zhs/cli/services/exam_service.py` 新增 `run_zhidao_exam_by_course` + `run_zhidao_exam`（仅扫描展示，不做题）
- Green: `src/zhs/__main__.py` `exam` 命令支持 `--type zhidao -c <courseId>`，展示待处理/已完成考试列表
- Refactor: ruff/mypy 通过；做题逻辑留 TODO 待 API 抓包确认
- 修正: `-c` 参数改为接收 courseId（数字型），通过课程列表反查 recruitId

### 校验
- `pytest`（新增）: 16 passed ✅
- `ruff check src/ tests/`: All checks passed ✅
- `ruff format --check src/ tests/`: 全绿 ✅
- `mypy src/`: no issues found in 71 source files ✅
- 备注：`tests/zhidao/test_video.py` 全量运行时有预存 I/O 隔离问题，单独运行 34 passed，与本次改动无关

---

## 知到考试 — 答题前置检查（位置验证）【已回退】

> 位置验证（AnswerGuard / 二维码扫码解锁）因验证码无法自动化，已整体回退。
> 仅保留 `getSaveAnswerLockResult` 锁状态判断：state=0 可答题，state=1 提示用户手动开启考试。

### 已回退的内容
- `src/zhs/zhidao/exam/guard.py`（AnswerGuard 类）— 已删除
- `tests/zhidao/exam/test_guard.py`（7 个测试）— 已删除
- `zhidao_exam_api.py` 的 4 个位置验证方法（queryIsOpenLocation / createEncodeImage / queryEncodeImageIsPass / getLoginSchoolInfo）— 已移除
- `session.py` 的 4 个委托方法 — 已移除
- `config.py` 的 `location_scan_timeout`/`location_scan_interval`/`location_max_retries` — 已移除
- `__main__.py` 的 `--school` / `--show-in-terminal` 参数 — 已移除

### 保留的内容
- `getSaveAnswerLockResult` API + session 委托（锁状态判断）
- `run_zhidao_exam` 中直接调用锁检查：state=0 → 可答题（TODO 做题），state=1 → "答案已锁死，请手动开启考试后重试"

### 校验
- `pytest`: 49 passed ✅
- `ruff check` + `format --check` + `mypy`: 全绿 ✅

---

## 知到考试 — doExam / saveStudentAnswer 做题功能

> 基于新抓包数据 `.temp/zhidao_exam_api_raw.md`（134KB）开发。
> **核心发现**：考试无心跳机制（抓包未见 updateUserUsedTime），无 submit API（用户手动提交）。
> 重写 API 文档 `.temp/zhidao_exam_api.md`，标记 doExam/saveStudentAnswer 为 ✅ 已确认。

### Task 17 — 重写 API 文档 ✅
- Red: —
- Green: `.temp/zhidao_exam_api.md` 重写：
  - doExam/saveStudentAnswer 从 ⚠️ 需抓包确认 → ✅ 已抓包确认
  - 移除心跳章节（updateUserUsedTime），明确"考试无心跳"
  - saveStudentAnswer 关键差异：`source=1` 明文字段 + `examType=1`（整数）
  - 位置验证 API 标记为"已移除（验证码无法自动化）"
  - 新增附录 D：做题策略（源感知延迟）
- Refactor: —
- 备注：抓包数据确认 saveStudentAnswer 使用 `studentexam-api` 域名（非 taurusexam-api）

### Task 18 — EncryptedQuery 支持 extra_fields 明文字段 ✅
- Red: `tests/api/test_encrypted_query.py::TestExtraFields`（3 用例：包含明文字段/默认不含/不加密）
- Green: `src/zhs/api/encrypted_query.py` `query()` 新增 `extra_fields` 参数，在 `_build_form_data` 后合并到 form_data（不进入 secretStr 加密）
- Refactor: ruff/mypy 通过
- 备注：saveStudentAnswer 的 `source=1` 是明文字段，与 secretStr 一起发送但不加密

### Task 19 — ZhidaoExamApi 新增 doExam / saveStudentAnswer / getLoginSchoolInfo ✅
- Red: `tests/api/test_zhidao_exam_api.py` 新增 10 用例（TestGetLoginSchoolInfo 3 + TestDoExam 3 + TestSaveStudentAnswer 4）
- Green: `src/zhs/api/zhidao_exam_api.py` 新增 3 方法：
  - `get_login_school_info()` → 返回 rt.schoolId（homework 策略）
  - `do_exam(recruit_id, exam_id, student_exam_id, school_id, course_id, device_id)` → 返回 rt 对象（zhidao_exam 策略）
  - `save_student_answer(answer_item, recruit_id)` → 返回 rt 对象（homework 策略 + extra_fields={"source":"1"}）
- Refactor: ruff/mypy 通过

### Task 20 — Session 委托层 ✅
- Red: —（委托方法，无独立测试）
- Green: `src/zhs/session.py` 新增 3 委托方法：
  - `exam_get_login_school_info() -> int`
  - `exam_do(recruit_id, exam_id, student_exam_id, school_id, course_id, device_id) -> dict`
  - `exam_save_answer(answer_item, recruit_id) -> dict`
- Refactor: ruff/mypy 通过

### Task 21 — ExamWorker 做题器 ✅
- Red: `tests/zhidao/exam/test_worker.py`（13 用例：TestExamWorkerSaveAnswer 4 + TestRunExam 6 + TestSourceAwareSleep 3）
- Green: `src/zhs/zhidao/exam/worker.py` `ExamWorker(HomeworkWorker)`：
  - `run_exam(exam, recruit_id, school_id) -> int`：doExam → 生成答案 → saveStudentAnswer（无心跳、无提交）
  - `_fetch_exam_detail`：调用 session.exam_do，复用 HomeworkDetail 模型
  - `_save_answer`：调用 session.exam_save_answer，examType=1（整数）
  - 源感知延迟：`_SLEEP_SOURCES = frozenset({"缓存正确", "缓存排除直接", "无LLM随机"})` 仅这些来源 sleep
- 修复：
  - 语法错误（msg_warn 字符串未闭合）
  - 测试 mock 返回 rt 对象（非完整响应，与 do_exam API 层一致）
  - `HomeworkExamBase.to_chapter` 添加 `_coerce_none_to_empty` 验证器（doExam 返回 null）
  - mypy `[override]` 错误：`_save_answer` 参数 ExamInfo 窄化，添加 `# type: ignore[override]`
- Refactor: ruff/mypy 通过，13 tests passed
- 同步：`src/zhs/zhidao/exam/__init__.py` 导出 ExamWorker

### Task 22 — exam_service 集成 ExamWorker ✅
- Red: —（集成层，依赖 Task 21 测试覆盖）
- Green: `src/zhs/cli/services/exam_service.py` `run_zhidao_exam` 替换 TODO：
  - 调用 `session.exam_get_login_school_info()` 获取 schoolId
  - 初始化 ExamWorker（复用 init_llm / init_question_bank / ZhidaoHomeworkCache）
  - state=0 → `worker.run_exam(exam, recruit_id, school_id)`
  - state=1 → 提示"答案已锁死，请手动开启考试后重试"
- Refactor: ruff/mypy 通过

### Task 23 — 文档与导出更新 ✅
- `src/zhs/zhidao/exam/__init__.py`：导出 ExamWorker
- `docs/log.md`：记录 Task 17-23
- `.temp/zhidao_exam_api.md`：重写（Task 17）

### 校验
- `pytest tests/zhidao/exam/ tests/api/test_zhidao_exam_api.py`: 28 passed ✅
- `ruff check` + `format --check` + `mypy`: 全绿 ✅

---

## 知到考试 — submit 提交功能（可选 --submit）

> 用户补充了 submit 接口抓包数据（`.temp/zhidao_exam_api_raw.md` 末尾）。
> 解码确认请求体：`{"recruitId":"394787","examId":"eAqdKONe","stuExamId":"edJddjZE","achieveCount":"80"}`。
> URL: `taurusexam-api/taurusExam/gateway/t/v1/answer/submit`，策略 `zhidao_exam`，不发送 `source`。
> 默认不提交，仅当 `--submit` 时调用。

### Task 24 — ZhidaoExamApi.submit_exam + Session 委托 ✅
- Red: `tests/api/test_zhidao_exam_api.py::TestSubmitExam`（3 用例：返回 rt/策略验证/错误抛异常）
- Green: `src/zhs/api/zhidao_exam_api.py` 新增 `submit_exam(recruit_id, exam_id, stu_exam_id, achieve_count)`
  - URL: `{base}/taurusExam/gateway/t/v1/answer/submit`，zhidao_exam 策略
  - 不发送 source 字段（与 saveStudentAnswer 不同）
- `src/zhs/session.py` 新增 `exam_submit` 委托方法
- Refactor: ruff/mypy 通过

### Task 25 — ExamWorker._submit_exam + run_exam(submit=) ✅
- Red: `tests/zhidao/exam/test_worker.py::TestExamWorkerSubmit`（5 用例）
  - submit=True 调用 exam_submit / submit=False 不调用 / 0 题不提交 / 提交失败不抛 / statu≠1 抛 ZhsError
- Green: `src/zhs/zhidao/exam/worker.py`
  - `run_exam` 新增 `submit: bool = False` 参数
  - submit=True 且 answer_count>0 时调用 `_submit_exam`
  - `_submit_exam`：调用 session.exam_submit，statu≠"1" 抛 ZhsError
  - 提交失败在 run_exam 中捕获，提示手动提交（不中断）
- Refactor: ruff/mypy 通过

### Task 26 — CLI/Service 层 --submit 传递 ✅
- `src/zhs/cli/services/exam_service.py`：`run_zhidao_exam_by_course` 和 `run_zhidao_exam` 新增 `submit: bool = False`
- `src/zhs/__main__.py`：`_run_zhidao_exam_by_course(session, config, c, submit=submit)`
- CLI 已有 `--submit` 参数（line 294），现在传递到知到考试路径
- Refactor: ruff/mypy 通过

### Task 27 — 文档更新 ✅
- `.temp/zhidao_exam_api.md`：submit 从 ⚠️ → ✅，更新附录 B/C 对比表
- `.temp/zhidao_exam_report.md`：新建知到考试功能详细报告（含输出示例）
- `docs/log.md`：记录 Task 24-27

### 校验
- `pytest tests/zhidao/exam/test_worker.py tests/api/test_zhidao_exam_api.py`: 36 passed ✅
- `ruff check` + `format --check` + `mypy`: 全绿 ✅


### Task 28 — 知到视频开播预检（提前发现验证码/时长上限）✅
- Red: \	ests/zhidao/test_video.py::TestStartPrecheck\（4 用例）
  - 预检在 _main_loop 前调用 _report_progress_v2(initial=True)，顺序 report → loop
  - 预检返回 -12 → CaptchaRequired，不进观看循环、不启动视频流线程
  - _report_progress_v2 遇 code -9 → TimeLimitExceeded（不再静默失败继续白看）
  - play_course 遇 TimeLimitExceeded 停止课程（不继续播放后续视频）
- Green: \src/zhs/zhidao/video.py\
  - 新增 \_precheck(rac_id, video_id, ctx, played_time, token_id)\：initial=True 补报格式，复刻网页端 getqueryCourse 进页补报行为，服务端风控在此响应即返回 -12/-9 判定
  - \play_video\ 在 \_start_watch_thread\ 之前调用 _precheck（时间限制本地跳过逻辑优先，避免无效请求）
  - \_report_progress_v2\ 捕获 ApiError(code=-9) 转 TimeLimitExceeded（from exc 链式）
  - \play_course\ 新增 except TimeLimitExceeded 分支：清进度条 + 提示"学习时间已达上限，停止课程" + return
- 背景：网页端逆向结论——验证码弹出完全由服务端 code -12 判定（学习时长心跳/进页补报响应），客户端无本地判定；网页端进页面即补报本地 saveDataKey 数据，未播放也能触发验证码
- Refactor: ruff check/format + mypy 通过；pytest 全量 1147 passed
- 修正（实测）：initial=True 补报不触发服务端风控（返回 code 0），-12/-9 仅在常规心跳格式（initial=False）上返回。_precheck 改为 delta=0 的常规心跳（last_submit=played_time，不虚报进度），预检格式断言同步更新。浏览器端进页即弹验证码走的是另一条入口检测链路（cheat/exceptionActionDetail 为处罚/锁定弹窗，非验证码），CLI 预检以可触发风控评估的心跳端点为准。

### Task 29 — AI 提供方选择可见性提示 ✅
- 背景：`use_builtin_ai`（默认 true）优先级高于 `api_key`。两者同时配置时，AI 智慧课程（AI 作业/AI 考试）静默走智慧树内置 AI，`api_key`/`base_url`/`model` 完全失效且无任何日志，用户易误以为在用自定义模型（知到作业/考试链路的 `init_llm` 忽略该开关、始终用 `api_key`，两条链路规则相反）
- Green: `src/zhs/cli/bootstrap.py`
  - 新增 `check_ai_provider(config)`：`ai.enabled` 且 `use_builtin_ai=true` 且 `api_key` 非空时 warning——"检测到已配置自定义 API Key 但 use_builtin_ai=true，AI 智慧课程将使用智慧树内置 AI；如需 AI 智慧课程也用自定义模型请设 use_builtin_ai=false（知到作业/考试没有内置 AI，仍会使用该 API Key）"
  - `load_config_and_session` 在 `setup_logger` 之后调用，覆盖 play/homework/exam/fetch 全部命令的公共启动路径（`zhs login` 不涉及 AI 调用，未接入）
  - 仅增加可见性，不改变优先级行为（字段名与文案随 Task 30 更新为 `use_builtin_ai`）
- Test: `tests/cli/test_bootstrap.py` 新增 `TestCheckAiProvider`（4 用例：命中提示 / 无 api_key 不提示 / use_builtin_ai=false 不提示 / ai 关闭不提示）+ `TestLoadConfigAndSession::test_calls_check_ai_provider`
- Refactor: ruff check/format + mypy 通过；pytest 全量 1152 passed

### Task 30 — 配置项更名 use_zhidao_ai → use_builtin_ai（消除语义歧义）✅
- 起因：旧名 `use_zhidao_ai` 字面像"全局使用知到 AI"，实际只影响 AI 智慧课程；知到作业/考试**没有内置 AI**、只能用自定义 `api_key`。两条链路规则相反，用户无法判断实际在用哪个模型
- 实测证据（只读验证，账号内 1 门知到课程、0 门 AI 智慧课程）
  - 知到课程 courseId=1000008156 调 `get-course-mapUid` → `code=500`（非 AI 课程拿不到内置 AI 所需参数）
  - 账号内 AI 智慧课程数 = 0 → 内置 AI 实际不可用
  - 结论：内置 AI 无法覆盖知到作业，"开关为 true 却静默改用 api_key"就是歧义根源
- Green（改名 + 文档，不保留旧名）
  - `src/zhs/config.py`：`use_builtin_ai: bool = True`，描述注明"仅 AI 智慧课程；false 则改用自定义 API Key；知到作业/考试没有内置 AI，只能用自定义 API Key"
  - `src/zhs/llm/factory.py`：`create()` 改读 `use_builtin_ai`，docstring 标注"仅 AI 智慧课程"
  - `src/zhs/cli/bootstrap.py`：`check_ai_provider` 提示语、`init_llm` docstring、题库告警文案同步改写（均明确 `api_key` 是通用自定义 LLM 配置，`use_builtin_ai=false` 时 AI 智慧课程也会使用它，避免"只服务知到作业"的误读）
  - 文档：`config.toml.example`、`README.md`、`README_zh.md`、`docs/spec.md`、`docs/design.md`、`docs/tutorial.md`、`docs/test.md`（教程改为"两条链路"对照表）
  - 测试：`tests/llm/test_factory.py`、`tests/cli/test_bootstrap.py`、`tests/cli/test_main.py`、`tests/cli/services/test_homework_service.py`、`tests/test_config.py`
- 迁移说明：旧键 `use_zhidao_ai` 已移除（不设兼容别名），旧配置中的该键会被 pydantic 忽略，请改用 `use_builtin_ai`；本机 `.zhs/config.toml` 已同步更新
- Refactor: ruff check/format + mypy 通过；pytest 全量 1152 passed

### Task 31 — LLM 失败可见性 + 4xx 不重试（知到作业）✅
- 现象（实测日志 20:56）：DeepSeek 返回 `402 Insufficient Balance` → 每题 3 次重试全败 → `_generate_answer_with_llm` 静默 `_random_answer`，但 `_generate_answer_with_source` 仍标注来源 `LLM`/`缓存排除AI`、日志写"LLM 返回答案" → 用户以为在用 AI，实际提交的是随机答案（同期题库配额也为 0，正确率完全等于随机）
- Green
  - `src/zhs/zhidao/homework/worker.py`
    - 新增实例状态 `_llm_degraded`（None / `failed` / `exhausted`）：`_generate_answer_with_llm` 每次调用先复位，LLM 抛错与重试耗尽分别置位
    - `_generate_answer_with_source` 按真实来源标注 `LLM失败随机` / `LLM重试耗尽随机`（不再把随机答案记成 LLM），日志按级别区分（error/warning）
    - `do_homework` 首次遇到 `LLM失败随机` 时在控制台提示一次"后续题目将降级为随机答案（正确率会明显下降），请检查 api_key/余额/网络"
    - `_style_source`：两个新来源标签分别用红/黄着色，控制台一眼可辨
  - `src/zhs/llm/openai.py`
    - 新增显式集合 `NON_RETRYABLE_STATUS = {400, 401, 402, 403, 404, 405, 409, 413, 422}`：命中即不重试、直接抛 `ZhsError`（每题省下约 2.3s 无效等待）；集合外的错误（408 超时、429 限流、5xx、网络异常、未列入的 4xx）仍按原策略重试，不做 4xx 一刀切
- Test: `tests/zhidao/homework/test_worker.py::TestLlmFailureVisibility`（3 用例：失败标注 / 成功仍标 LLM / 控制台只提示一次）+ `tests/llm/test_openai.py::TestOpenAIRetryPolicy`（4 用例：402 不重试 / 429 仍重试 / 未列入集合的 4xx（418）仍重试 / 无状态码错误仍重试）
- Refactor: ruff check/format + mypy 通过；pytest 全量 1158 passed

### Task 32 — 提前终止后关闭流（消除 chunk_queue 丢弃与连接泄漏）✅
- 现象（实测 `.zhs/logs/zhs_2026-09-22.log`）：单日 `chunk_queue 满，丢弃 chunk` **128 次**；按 reader 线程分组，相邻丢包间隔**恒为 5.00~5.02s**（= `put(timeout=5.0)` 超时）→ 证明是「主线程提前终止后无人消费」，而非 chunk 到达过密
- 影响：每条被抛弃的流在无消费者时每 5s 丢一个 chunk，128 次 ≈ **10.7 分钟**白读（白烧 token/流量/连接）；若丢弃发生在找到标记之前则会丢答案内容
- Green: `src/zhs/llm/openai.py`
  - 新增 `stop_event`（`threading.Event`）+ `_close_stream()`：主线程离开的三条路径（找到标记 `return` / 流式超时 / 流内异常）统一由 `try/finally` 触发 `stop_event.set()` 与 `stream.close()`
  - `_reader`：每次迭代前检查停止标记；空 delta 不再入队；`put(timeout=5.0)` → `put_nowait`（丢弃改为计数）；丢弃在 reader 退出时汇总为**一条** warning
- Test: `tests/llm/test_openai.py::TestStreamEarlyTermination`（6 用例：提前终止后 reader 停止且关流 / 提前终止无丢包告警 / 标记末尾闭合返回完整文本 / 超时同样停流关流 / `close()` 抛异常不影响返回值 / **思考阶段只有空 delta 时不误杀**）
- 修正（实现过程中踩到并修复的回归）：初版把"空 delta 不入队"当优化，但思考型模型（`deepseek-v4-flash` 等）在思考阶段只发 `reasoning_content`、`delta.content` 为空，这些空 delta 原本承担"刷新 30s 空闲超时"的 keepalive 作用；丢弃后 23:34:37 / 23:35:55 两次真实运行出现 `OpenAI 流式响应超时（30.0s 无数据），已收集 0 个 chunk`，重试后才成功（单题多花约 20 秒并白烧一次思考 token）。现明确：**空 delta 照常入队作为活跃信号**（不参与 `cache` 拼接），空闲阈值抽为 `STREAM_IDLE_TIMEOUT = 30.0`，语义为"这么久连一个 delta 都没收到"才算死连接；reader 退出时打印 `流式统计: 正文 chunk=N, 空 delta(含 thinking)=M` 便于确认 reasoning 阶段长度
- 受益范围：`OpenAIProvider` 同时服务「知到作业/考试」与「AI 智慧课程 + `use_builtin_ai=false`」两条链路
- 未做（实测评估为可忽略）：消费端全文正则 O(n²) —— 每 chunk 仅 1.5~3.6 µs（≈28~66 万 chunk/s），比 chunk 到达速率快 3 个数量级，与本次丢包**无因果关系**（依据见 `.temp/llm_stream_queue_fix.md` §3.3 / §9.4）
- 修复文档：`.temp/llm_stream_queue_fix.md`（含根因、方案对比、测试计划、验收标准、证据附录）
- Refactor: ruff check/format + mypy 通过；pytest 全量 1165 passed

### Task 33 — 发布流程改造（CHANGELOG 打 tag 前生成）+ README 安装前置说明 ✅
- 背景：旧 `release.yml` 在发布后把 CHANGELOG 回写 `dev`（`main` 受 `main-basic` 规则集保护：`pull_request` 规则 + `bypass_actors=[]` + `current_user_can_bypass=never`，机器人直推 main 被拒 GH013），于是每次发布后 `dev` 必然领先 `main` 一个提交，必须人工补一次 `dev → main` 同步 PR（v0.1.4 后即如此）
- Green（方案 B：CHANGELOG 在打 tag 前生成，发布后零收尾）
  - 新增 `.github/workflows/prepare-release.yml`（`workflow_dispatch` 输入 `version`）：校验 `X.Y.Z` 格式与标签是否已占用 → `sed` bump `pyproject.toml` version → git-cliff 生成新版本段落 → 插入 `CHANGELOG.md` 头部之后 → 推送 `chore/release-vX.Y.Z` 并开 PR 到 `main`（标题 `release: vX.Y.Z`，正文含 release notes 与打 tag 命令）
  - `release.yml`：删除「发布后回写 CHANGELOG 到 dev」步骤，只保留 check / build / GitHub Release / PyPI；发布结束即 `main == dev`
  - `docs/linter.md` §9.3 发布流程重写为「Prepare Release → 合并发布 PR → 在 main 打 tag 并推送」；§9.4 补充关键坑：**标签尚不存在时必须带 `--unreleased`，否则 git-cliff 只渲染已存在的标签**，本地预览统一改用 `uvx --from git-cliff git-cliff`
- 实测踩坑（本地校验发现并修复）：git-cliff 在标签不存在时的三种行为——仅 `--tag vX` 输出的是上一版段落（0.1.4）；`--unreleased --tag vX` 只输出新版本段落（不含历史）；`--prepend` 会把 `# Changelog` 文件头重复一遍。最终采用「`--unreleased --tag vX --strip header` 生成段落 + 插入文件头之后」，且拼接用 `head.rstrip()` / `tail.lstrip("\n")`（初版用 `text[:i] + "\n\n" + section` 会多出**一个空行**，由校验脚本断言发现）
- 已知依赖：Prepare Release 依赖仓库设置 *Allow GitHub Actions to create and approve pull requests*（当前为关闭）；未开启时分支仍会推送，工作流打印手动开 PR 的 compare 链接，不会静默失败
- Green（README 安装说明，中英同步）：`README.md` / `README_zh.md` 的「前置要求 / Prerequisites」改为——Python 3.13+ → **最快开始：`pip install zhs`，最推荐用户使用** → uv 包管理器（标注"开发推荐"）→ 预打包 whl；删去原先重复的独立 `pip install zhs` 条目
- Test: 无 Python 代码改动；新增的 CHANGELOG 插入逻辑用临时脚本对**真实 `CHANGELOG.md` 副本**做断言校验（文件头唯一 / 新版本段落在 0.1.4 之前 / 历史顺序不变 / 无多余空行 / `<!-- generated by git-cliff -->` 只出现一次）
- 修正（版本号方案）：项目历史 tag 含**四段版本**（`v0.1.2.1`、`v0.1.2.2`），初版校验 `^[0-9]+\.[0-9]+\.[0-9]+$` 会把它们挡下；放宽为 `^[0-9]+(\.[0-9]+){2,3}$`（3 段或 4 段），错误提示与 `docs/linter.md` §9.3 的 tag 格式规则同步补充四段写法
- Refactor: ruff check/format + mypy（158 files）通过；pytest 全量 1165 passed；分支 `chore/prepare-release-flow`
