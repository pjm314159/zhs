# ZHS 开发日志

> 记录 TDD 开发过程中每个 Phase 的进度、决策和问题。

---

## Phase 1: 基础设施

### 1. exceptions.py

| 日期 | 状态 | 测试覆盖 | 备注 |
|------|------|----------|------|
| - | [ ] 未开始 | - | 全局异常定义，无外部依赖 |

**TDD 循环记录**：

| # | 测试用例 | 红/绿 | 备注 |
|---|----------|-------|------|
| 1 | `ZhsError` 可被 `except ZhsError` 捕获 | - | |
| 2 | `ApiError` 携带 `code` 和 `message` 属性 | - | |
| 3 | `CaptchaRequired` 继承自 `ZhsError` | - | |
| 4 | `LoginFailed` 继承自 `ZhsError` | - | |
| 5 | `InvalidCookies` 继承自 `ZhsError` | - | |
| 6 | `TimeLimitExceeded` 继承自 `ZhsError` | - | |

---

### 2. crypto.py

| 日期 | 状态 | 测试覆盖 | 备注 |
|------|------|----------|------|
| - | [ ] 未开始 | - | AES/ev/签名，密钥从 CryptoConfig 获取 |

**TDD 循环记录**：

| # | 测试用例 | 红/绿 | 备注 |
|---|----------|-------|------|
| 1 | `Cipher(key, iv).encrypt("hello")` → `decrypt` 还原 | - | AES 对称性 |
| 2 | `Cipher` 加密空字符串不崩溃 | - | 边界 |
| 3 | `Cipher` 加密非 ASCII 字符（中文） | - | Unicode |
| 4 | `Cipher` 加密超长字符串 | - | 大数据 |
| 5 | `encode_ev(data)` → `decode_ev` 还原 | - | ev 对称性 |
| 6 | `encode_ev` 使用默认密钥 `zzpttjd` | - | |
| 7 | `encode_ev` 使用自定义密钥 | - | |
| 8 | `encode_ev` 空列表 | - | 边界 |
| 9 | `sign_hike(params, salt)` 与已知结果对比 | - | 需从旧代码提取已知输入输出 |
| 10 | `sign_hike` 字段顺序正确性 | - | 顺序：SALT+uuid+courseId+... |
| 11 | `sign_zhidao_ai(data, prefix)` 返回含 `sign` 参数的 URL | - | |
| 12 | `sign_zhidao_ai` 生成 `chatcmpl-` 前缀的 sessionNid | - | |
| 13 | `WatchPoint(init=0).get()` 初始值 `[0, 1]` | - | |
| 14 | `WatchPoint.add(100)` → `gen(100) = 100//5+2 = 22` | - | |
| 15 | `WatchPoint.reset()` 恢复初始状态 | - | |

---

### 3. utils/path.py

| 日期 | 状态 | 测试覆盖 | 备注 |
|------|------|----------|------|
| - | [ ] 未开始 | - | |

**TDD 循环记录**：

| # | 测试用例 | 红/绿 | 备注 |
|---|----------|-------|------|
| 1 | `get_data_dir()` 返回 `~/.zhs/` 或项目目录 | - | |
| 2 | `get_config_path()` 返回正确路径 | - | |
| 3 | `version_cmp("1.0.0", "2.0.0")` 返回 `<0` | - | |
| 4 | `version_cmp("2.0.0", "1.0.0")` 返回 `>0` | - | |
| 5 | `version_cmp("1.0.0", "1.0.0")` 返回 `0` | - | |
| 6 | `version_cmp("1.2.3", "1.2.4")` | - | 语义化版本 |

---

### 4. utils/cookie.py

| 日期 | 状态 | 测试覆盖 | 备注 |
|------|------|----------|------|
| - | [ ] 未开始 | - | |

**TDD 循环记录**：

| # | 测试用例 | 红/绿 | 备注 |
|---|----------|-------|------|
| 1 | `cookies_to_list` → `list_to_cookies` 往返还原 | - | |
| 2 | 空 cookies 序列化/反序列化 | - | 边界 |
| 3 | 多 domain cookies 保留 domain 信息 | - | |

---

### 5. utils/display.py

| 日期 | 状态 | 测试覆盖 | 备注 |
|------|------|----------|------|
| - | [ ] 未开始 | - | 终端输出，测试以不抛异常为主 |

**TDD 循环记录**：

| # | 测试用例 | 红/绿 | 备注 |
|---|----------|-------|------|
| 1 | `progress_bar(50, 100)` 不抛异常 | - | |
| 2 | `progress_bar(0, 0)` 除零保护 | - | 边界 |
| 3 | `tree_print(text, depth)` 不抛异常 | - | |
| 4 | `wipe_line()` 不抛异常 | - | |

---

### 6. config.py

| 日期 | 状态 | 测试覆盖 | 备注 |
|------|------|----------|------|
| - | [ ] 未开始 | - | |

**TDD 循环记录**：

| # | 测试用例 | 红/绿 | 备注 |
|---|----------|-------|------|
| 1 | `AppConfig()` 默认值正确 | - | |
| 2 | `CryptoConfig.key_bytes("video_key")` → `b"azp53h0kft7qi78q"` | - | |
| 3 | `CryptoConfig.key_bytes("nonexistent")` → 抛异常 | - | |
| 4 | `ConfigManager.load()` 从 TOML 文件加载 | - | 需要 tmp_path fixture |
| 5 | `ConfigManager.save()` 写入 TOML 文件 | - | |
| 6 | `ConfigManager.load()` → `save()` → `load()` 往返一致 | - | |
| 7 | 旧版 JSON 配置迁移到 `AppConfig` | - | |
| 8 | TOML 缺失字段时使用默认值填充 | - | |
| 9 | `UrlConfig` 默认值正确 | - | |

---

### 7. session.py

| 日期 | 状态 | 测试覆盖 | 备注 |
|------|------|----------|------|
| - | [ ] 未开始 | - | Mock httpx |

**TDD 循环记录**：

| # | 测试用例 | 红/绿 | 备注 |
|---|----------|-------|------|
| 1 | `ZhsSession(config)` 初始化不报错 | - | |
| 2 | `session.cookies = {...}` 设置后 `session.uuid` 正确解析 | - | Mock CASLOGC cookie |
| 3 | `zhidao_query` 自动加密 data + 添加 dateFormate | - | Mock httpx 响应 |
| 4 | `zhidao_query` 返回码 -12 抛 `CaptchaRequired` | - | |
| 5 | `hike_query` 自动添加 `_` 时间戳 | - | |
| 6 | `hike_query` sig=True 时自动签名 | - | |
| 7 | `ai_exam_query` 异步版本正常工作 | - | |
| 8 | `ai_exam_query` 密钥从 config.crypto.exam_key 获取 | - | |
| 9 | API 5xx 自动重试 | - | Mock 500 → 200 |
| 10 | Cookie 设置时自动添加 `exitRecod_{uuid}=2` | - | |

---

### 8. logger.py

| 日期 | 状态 | 测试覆盖 | 备注 |
|------|------|----------|------|
| 2026-06-14 | [x] 完成 | 17 tests | 依赖 utils/path + config |

**TDD 循环记录**：

| # | 测试用例 | 红/绿 | 备注 |
|---|----------|-------|------|
| 1 | `setup_logging` 移除 loguru 默认 sink | ✅ Green | |
| 2 | `setup_logging` 注册 stderr sink，级别由 config.log_level 控制 | ✅ Green | |
| 3 | `setup_logging` 注册文件 sink，始终 DEBUG | ✅ Green | |
| 4 | 文件 sink 轮转 10MB + 保留 7 天 + zip 压缩 | ✅ Green | |
| 5 | `setup_logging` 幂等：重复调用不重复注册 | ✅ Green | |
| 6 | `get_log_dir()` 返回 `<data_dir>/logs/` 并自动创建 | ✅ Green | |
| 7 | `_SENSITIVE_PATTERNS` 脱敏 CASLOGC | ✅ Green | |
| 8 | `_SENSITIVE_PATTERNS` 脱敏 token/password/apiKey | ✅ Green | |
| 9 | `_SENSITIVE_PATTERNS` 脱敏 Authorization Bearer | ✅ Green | |
| 10 | `_SENSITIVE_PATTERNS` 不影响普通文本 | ✅ Green | |
| 11 | filter 与 loguru 集成后日志消息自动脱敏 | ✅ Green | 使用 filter 而非 patcher |
| 12 | 控制台格式包含时间戳+级别+消息 | ✅ Green | |
| 13 | 文件格式包含线程名+模块名+行号 | ✅ Green | |

**设计变更**：原设计使用 `logger.patcher()` 注册 patcher，但 loguru 0.7.3 的 `patch()` 返回新 Logger 实例而非修改全局 logger。改用 `filter` 参数（每个 sink 带 `_sensitive_filter`），在写入前修改 `record["message"]`，效果等价且更可靠。

---

## Phase 2: 登录

### 8. login.py

| 日期 | 状态 | 测试覆盖 | 备注 |
|------|------|----------|------|
| 2026-06-14 | [x] 完成 | 10 tests | Mock httpx + respx |

**TDD 循环记录**：

| # | 测试用例 | 红/绿 | 备注 |
|---|----------|-------|------|
| 1 | 扫码登录：获取二维码 → 轮询 → 确认 → 登录 | ✅ Green | gologin 返回 HTML 不解析 JSON |
| 2 | 扫码 status=2 过期 → 递归重试 | ✅ Green | |
| 3 | 扫码 status=3 取消 → 抛异常 | ✅ Green | |
| 4 | 扫码 status=0 仅提示一次"已扫描" | ✅ Green | on_scanned 回调 |
| 5 | Cookie 恢复登录成功 | ✅ Green | |
| 6 | Cookie 过期 → 重新登录 | ✅ Green | save_cookies + roundtrip |

---

## Phase 3: 知到课程

### 9. zhidao/models.py

| 日期 | 状态 | 测试覆盖 | 备注 |
|------|------|----------|------|
| 2026-06-14 | [x] 已完成 | 18 tests | pydantic 模型 + alias 映射 |

**TDD 循环记录**：

| # | 测试用例 | 红/绿 | 备注 |
|---|----------|-------|------|
| 1 | `ZhidaoCourse` 从 API JSON 构建（alias 映射 recruitAndCourseId） | ✅ Green | |
| 2 | `ZhidaoCourse` 可选字段 course_info/recruit_id 默认 None | ✅ Green | |
| 3 | `ZhidaoCourse` 含完整 courseInfo | ✅ Green | |
| 4 | `CourseInfo` en_name 默认空字符串 | ✅ Green | |
| 5 | `VideoSmallLesson` 仅 video_id 必填，其余默认 0/"" | ✅ Green | |
| 6 | `VideoSmallLesson` 所有字段赋值 | ✅ Green | |
| 7 | `VideoChapter` video_lessons 默认空列表 | ✅ Green | |
| 8 | `VideoChapter` 包含课时 | ✅ Green | |
| 9 | `VideoLesson` 默认值正确 | ✅ Green | |
| 10 | `VideoLesson` 包含子视频 | ✅ Green | |
| 11 | `QuestionPoint` 时间点和题目 ID | ✅ Green | |
| 12 | `QuestionOption` result='1' 为正确答案 | ✅ Green | |
| 13 | `QuestionOption` 默认值 | ✅ Green | |
| 14 | `PopupQuestion` 包含题目 ID 和选项 | ✅ Green | |
| 15 | `ZhidaoContext` 不含 cookies/headers 字段 | ✅ Green | |
| 16 | `ZhidaoContext` fucked_time 默认 0 | ✅ Green | |
| 17 | `ZhidaoContext` 包含视频字典 | ✅ Green | |
| 18 | `ZhidaoContext` chapters 为 VideoChapter 列表 | ✅ Green | |

---

### 10. zhidao/course.py

| 日期 | 状态 | 测试覆盖 | 备注 |
|------|------|----------|------|
| 2026-06-14 | [x] 已完成 | 6 tests | gologin 返回 HTML 不解析 JSON |

**TDD 循环记录**：

| # | 测试用例 | 红/绿 | 备注 |
|---|----------|-------|------|
| 1 | `get_course_list()` 返回课程列表 | ✅ Green | Mock API |
| 2 | `get_course_list()` 空列表 | ✅ Green | |
| 3 | `get_course_list()` 分页获取 | ✅ Green | totalCount > pageSize |
| 4 | `get_context()` 返回 ZhidaoContext | ✅ Green | |
| 5 | 单视频课时自动构造子视频 | ✅ Green | 有 videoId 无 videoSmallLessons |
| 6 | 已看完课程 watch_state=1 | ✅ Green | |

---

### 11. zhidao/quiz.py

| 日期 | 状态 | 测试覆盖 | 备注 |
|------|------|----------|------|
| 2026-06-14 | [x] 已完成 | 10 tests | |

**TDD 循环记录**：

| # | 测试用例 | 红/绿 | 备注 |
|---|----------|-------|------|
| 1 | `load_video_pointer_info` 返回题目列表 | ✅ Green | |
| 2 | `load_video_pointer_info` 空列表 | ✅ Green | |
| 3 | 过滤已答题目（timeSec <= played_time） | ✅ Green | |
| 4 | 所有题目都已答过 | ✅ Green | |
| 5 | `answer_question` 选择正确答案 | ✅ Green | result=='1' |
| 6 | `answer_question` 多选正确答案 | ✅ Green | |
| 7 | answer_delay=2 递减 | ✅ Green | |
| 8 | answer_delay 答题后重置 | ✅ Green | |
| 9 | `get_popup_exam` 返回题目详情 | ✅ Green | |
| 10 | `save_answer` 调用 API | ✅ Green | |

---

### 12. zhidao/video.py

| 日期 | 状态 | 测试覆盖 | 备注 |
|------|------|----------|------|
| 2026-06-14 | [x] 已完成 | 21 tests | 最复杂模块，视频播放主循环 |

**TDD 循环记录**：

| # | 测试用例 | 红/绿 | 备注 |
|---|----------|-------|------|
| 1 | 已看完视频 → 跳过 | ✅ Green | end_threshold<=1.0 |
| 2 | end_threshold > 1.0 时重看 | ✅ Green | |
| 3 | played_time 截断不超过 end_time | ✅ Green | |
| 4 | played_time 正常递增 | ✅ Green | |
| 5 | 随机暂停 → played_time 不前进 | ✅ Green | |
| 6 | 暂停倒计时递减 | ✅ Green | |
| 7 | V2 initial=True 格式 | ✅ Green | |
| 8 | initial=True 不含 courseId | ✅ Green | |
| 9 | V2 initial=False 格式 | ✅ Green | ewssw/sdsew/zwsds |
| 10 | initial=False 含 courseId | ✅ Green | |
| 11 | _watch_video 独立 httpx.Client | ✅ Green | 线程安全 |
| 12 | _watch_video daemon=True | ✅ Green | |
| 13 | answer_delay=2 递减 | ✅ Green | |
| 14 | answer_delay=0 时提交答案 | ✅ Green | |
| 15 | 答题延迟期间产生暂停 | ✅ Green | |
| 16 | 人类延迟 sleep(random+1) | ✅ Green | |
| 17 | 默认 end_threshold=0.91 | ✅ Green | |
| 18 | 弹窗题目时间超过 end_threshold | ✅ Green | |
| 19 | WatchPoint 添加和获取 | ✅ Green | |
| 20 | WatchPoint 重置 | ✅ Green | |
| 21 | play_course 遍历所有视频 | ✅ Green | |

---

## Phase 4: Hike 课程

### 13-15. hike/

| 日期 | 状态 | 测试覆盖 | 备注 |
|------|------|----------|------|
| 2026-06-14 | [x] 已完成 | 18 tests | models + course + video |

**TDD 循环记录**：

| # | 测试用例 | 红/绿 | 备注 |
|---|----------|-------|------|
| 1 | `HikeCourse` 从 API JSON 构建（alias 映射） | ✅ Green | model_validate |
| 2 | `ResourceNode` 递归 child_list | ✅ Green | |
| 3 | `ResourceNode` 无 file_id 的非标准节点跳过 | ✅ Green | |
| 4 | `get_course_list()` 返回课程列表 | ✅ Green | |
| 5 | `get_resource_tree()` 返回资源树 | ✅ Green | |
| 6 | 遍历：data_type=3 → play_video | ✅ Green | |
| 7 | 遍历：data_type=None + file_id → play_file | ✅ Green | |
| 8 | 遍历：data_type=None + 无 file_id → 跳过 | ✅ Green | |
| 9 | `play_file` try/except 防护 KeyError | ✅ Green | |
| 10 | `saveStuStudyRecord` 返回值覆盖 played_time | ✅ Green | |
| 11 | 默认速度 1.25 | ✅ Green | |

**修复**：pyproject.toml 重复 dependencies 键合并；hike 测试中 pydantic alias 模型改用 `model_validate`；`play_video` 测试 mock `save_stu_study_record` 从 `return_value=60` 改为 `side_effect=lambda *a, **kw: int(a[3] + 10)` 防止无限循环；添加 `patch("zhs.hike.video.time.sleep")` 防止真实 sleep。

---

## Phase 5: LLM 答题

### 16-19. llm/

| 日期 | 状态 | 测试覆盖 | 备注 |
|------|------|----------|------|
| 2026-06-14 | [x] 已完成 | 36 tests | prompts + base + openai + zhidao |

**TDD 循环记录**：

| # | 测试用例 | 红/绿 | 备注 |
|---|----------|-------|------|
| 1 | `build_choice_prompt` 包含 ```answer``` 标记 | ✅ Green | |
| 2 | `build_choice_prompt` 包含参考资料 | ✅ Green | |
| 3 | `build_choice_prompt` 包含课程上下文 | ✅ Green | |
| 4 | `build_choice_prompt` 多选题指令 | ✅ Green | |
| 5 | `build_fill_blank_prompt` 包含 ```answer``` 标记 | ✅ Green | |
| 6 | `build_fill_blank_prompt` 包含参考资料 | ✅ Green | |
| 7 | `parse_choice_answer` 正常 JSON 格式 | ✅ Green | |
| 8 | `parse_choice_answer` ast.literal_eval 兜底 | ✅ Green | |
| 9 | `parse_choice_answer` 无匹配返回空列表 | ✅ Green | |
| 10 | `parse_fill_blank_answer` 按行提取 | ✅ Green | |
| 11 | `parse_fill_blank_answer` 空输出返回空列表 | ✅ Green | |
| 12 | `LLMProvider.single_choice` 调用 completion + parse | ✅ Green | |
| 13 | `LLMProvider.multiple_choice` 调用 completion + parse | ✅ Green | |
| 14 | `LLMProvider.judgement` 调用 completion + parse | ✅ Green | |
| 15 | `LLMProvider.fill_blank` 调用 completion + parse | ✅ Green | |
| 16 | `OpenAIProvider.completion` 非流式 | ✅ Green | Mock openai |
| 17 | `OpenAIProvider.completion` 流式 | ✅ Green | |
| 18 | `OpenAIProvider.completion` API 错误处理 | ✅ Green | |
| 19 | `ZhidaoAIProvider.completion` 非流式 | ✅ Green | Mock session._get_client |
| 20 | `ZhidaoAIProvider.completion` 流式 SSE 解析 | ✅ Green | |
| 21 | `ZhidaoAIProvider` 签名参数正确 | ✅ Green | |
| 22 | `ZhidaoAIProvider` API 错误处理 | ✅ Green | |
| 23 | `ZhidaoAIProvider._parse_sse` 多行解析 | ✅ Green | |

**设计变更**：`ZhidaoAIProvider` 使用 `self._session._get_client().post()` 发送请求（ZhsSession 无 `post` 方法），测试 mock `_get_client().post` 而非 `session.post`。

---

## Phase 6: AI 课程

### 20-23. ai/

| 日期 | 状态 | 测试覆盖 | 备注 |
|------|------|----------|------|
| 2026-06-14 | [x] 已完成 | 68 tests | models + ppt + exam + course |

**TDD 循环记录**：

| # | 测试用例 | 红/绿 | 备注 |
|---|----------|-------|------|
| 1 | `KnowledgePoint` 从 API JSON 构建 | ✅ Green | |
| 2 | `Theme` 包含知识点列表 | ✅ Green | |
| 3 | `AiCourseInfo` 包含主题列表 | ✅ Green | |
| 4 | `ResourceDetail` 资源类型和分发类型 | ✅ Green | |
| 5 | `Resource` 学习状态 | ✅ Green | |
| 6 | `ExamInfo` 考试信息 | ✅ Green | |
| 7 | `QuestionSheet` / `QuestionContent` 模型 | ✅ Green | |
| 8 | `OptionVo` 选项模型 | ✅ Green | |
| 9 | `AnswerCache` 缓存模型 | ✅ Green | |
| 10 | `PptConverter` 完整转换流程 | ✅ Green | Mock MoonShot |
| 11 | `_cleanup_local` 删除临时文件 | ✅ Green | |
| 12 | `cleanup_local=False` 不调用清理 | ✅ Green | |
| 13 | `_extract` JSON 解析优先 | ✅ Green | |
| 14 | `_extract` 纯文本兜底 | ✅ Green | |
| 15 | `_manage_cache` LRU 清理 | ✅ Green | |
| 16 | `ExamCtx` Semaphore(3) 限制并发 | ✅ Green | |
| 17 | `_process_question` 每题 sleep 0.3-0.8s | ✅ Green | |
| 18 | 两级缓存：先查 all_answer_cache 再查 answer_cache | ✅ Green | |
| 19 | `_save_answer` 用 `#@#` 分隔选项 ID | ✅ Green | |
| 20 | `_submit_exam` 含 courseType=8 | ✅ Green | |
| 21 | 选项少于 2 个且非填空 → 选第一个 | ✅ Green | |
| 22 | API 失败 3 次重试 | ✅ Green | |
| 23 | 缓存键格式（version=1 无后缀，>1 有后缀） | ✅ Green | |
| 24 | `get_knowledge_points` 返回知识点列表 | ✅ Green | |
| 25 | 资源类型路由：(2,1) 文本 → complete_resource | ✅ Green | |
| 26 | 资源类型路由：(1,4) PPT → complete + 收集 URL | ✅ Green | |
| 27 | 资源类型路由：(1,3) 视频 → play_video | ✅ Green | |
| 28 | 资源类型路由：(2,2) 课程视频 → play_video | ✅ Green | |
| 29 | 已完成 PPT 仍收集 URL | ✅ Green | |
| 30 | mastery_score > 90 → 退出考试 | ✅ Green | |
| 31 | mastery_score < 30 且 tried > 4 → 放弃 | ✅ Green | |
| 32 | no_exam=True 跳过考试 | ✅ Green | |

**设计变更**：`PptConverter._cleanup_local` 属性名与方法名冲突，属性重命名为 `_should_cleanup_local`。`ZhidaoAIProvider` 使用 `self._session._get_client().post()` 发送请求。`ExamCtx._open_exam` 失败时抛出 `ZhsError` 而非原始异常。

---

## Phase 7: CLI

### 24. __main__.py

| 日期 | 状态 | 测试覆盖 | 备注 |
|------|------|----------|------|
| 2026-06-14 | [x] 已完成 | 8 tests | typer CLI 入口 |

**TDD 循环记录**：

| # | 测试用例 | 红/绿 | 备注 |
|---|----------|-------|------|
| 1 | `zhs --help` 不报错 | ✅ Green | |
| 2 | 含字母课程 ID → 路由到知到 | ✅ Green | detect_course_type |
| 3 | 纯数字课程 ID → 路由到 Hike | ✅ Green | |
| 4 | `--type hike` 显式指定 | ✅ Green | |
| 5 | CLI 参数覆盖 config 值 | ✅ Green | --speed 覆盖 |
| 6 | `detect_course_type` 辅助函数 | ✅ Green | 单元测试 |

**设计变更**：CLI 使用 typer 框架替代旧版 argparse。课程类型检测逻辑：`--type` 显式指定优先，含字母→知到，纯数字→Hike。B008 规则使用 `# noqa: B008` 抑制。

---

## 重构: AI Homework 异步转同步

### 背景

知到作业 API 有时间速率限制，异步并发会触发限流。将 `ai/homework.py` 从 asyncio 改为同步实现，使用 threading + time.sleep 替代。

### 变更清单

| 文件 | 变更 |
|------|------|
| `src/zhs/ai/homework.py` | 删除 asyncio，改用 threading + time.sleep；并发改顺序 |
| `src/zhs/session.py` | 删除 `_async_client`/`_get_async_client`/`async_api_query`/`aclose`；`ai_exam_query` 改同步 |
| `src/zhs/ai/course.py` | 移除 `asyncio.run` 调用 |
| `tests/ai/test_homework.py` | 异步测试转同步，删除 AsyncMock/pytest.mark.asyncio |
| `tests/test_session.py` | TestAiExamQuery 转同步 |
| `tests/integration/test_ai_integration.py` | 转同步 |
| `pyproject.toml` | 移除 `pytest-asyncio` 依赖与 `asyncio_mode` 配置 |

### TDD 循环记录

| # | 阶段 | 测试用例 | 红/绿 | 备注 |
|---|------|----------|-------|------|
| 1 | RED | `test_no_semaphore` 验证无 asyncio.Semaphore | ✅ Red | 删除旧并发测试 |
| 2 | RED | `test_heartbeat_thread_attribute` 验证 threading.Thread 属性 | ✅ Red | |
| 3 | RED | `test_heartbeat_uses_thread` 验证使用 threading.Thread | ✅ Red | |
| 4 | RED | `test_heartbeat_thread_daemon` 验证 daemon=True | ✅ Red | |
| 5 | RED | `TestAiExamQuery::test_sync_query_works` 同步调用 | ✅ Red | |
| 6 | GREEN | `ai/homework.py` 重写为同步 | ✅ Green | threading.Thread 心跳，for 循环顺序处理 |
| 7 | GREEN | `session.py` 删除异步接口，`ai_exam_query` 改同步 | ✅ Green | 使用 `self.api_query()` |
| 8 | GREEN | `ai/course.py` 移除 `asyncio.run` | ✅ Green | 直接调用 `homework_ctx.start()` |
| 9 | GREEN | `pyproject.toml` 移除 pytest-asyncio | ✅ Green | |
| 10 | REFACTOR | `ruff check src/ tests/` | ✅ Pass | All checks passed |
| 11 | REFACTOR | `ruff format src/ tests/` | ✅ Pass | 3 files reformatted |
| 12 | REFACTOR | `mypy src/ tests/` | ✅ Pass | Success: no issues found in 89 source files |
| 13 | REFACTOR | 相关测试 63 个全绿 | ✅ Pass | tests/ai + tests/test_session + integration |

**设计变更**：
- `HomeworkCtx._semaphore` (asyncio.Semaphore) 删除，改为顺序处理（for 循环）
- `HomeworkCtx._heartbeat_task` (asyncio.Task) → `_heartbeat_thread` (threading.Thread, daemon=True)
- `HomeworkCtx.start()` 从 `async def` 改为 `def`
- `await asyncio.gather(*tasks)` → `for sheet in sheets: self._process_question(sheet)`
- `await asyncio.sleep()` → `time.sleep()`
- `ZhsSession` 删除 `_async_client`/`_get_async_client`/`async_api_query`/`aclose`
- `ZhsSession.ai_exam_query` 从 `async def` 改为 `def`，使用 `self.api_query()` 替代 `await self.async_api_query()`
- `ai/course.py` 中 `asyncio.run(homework_ctx.start(...))` → `homework_ctx.start(...)`
- 移除 `pytest-asyncio` 依赖与 `asyncio_mode = "auto"` 配置

**验证结果**：
- `ruff check src/ tests/` → All checks passed
- `ruff format --check src/ tests/` → 89 files already formatted
- `mypy src/ tests/` → Success: no issues found in 89 source files
- 相关测试 63 个全部通过（tests/ai/test_homework.py + tests/test_session.py + tests/ai/test_course.py + tests/integration/test_ai_integration.py）
- grep 验证：src/zhs/ 无 asyncio/async def/await/AsyncClient 残留
