# ZHS 规格说明书

## 1. 项目概述

ZHS 是一个智慧树（zhihuishu.com）自动学习工具，支持三类课程的自动学习：

- **知到（Zhidao）共享课**：视频进度模拟、弹窗答题、章节作业
- **Hike 职教云课**：视频进度模拟、资源树遍历
- **AI 智慧课程**：视频进度模拟、作业自动作答、考试自动作答、AI 解析

核心能力：扫码登录、视频进度模拟、弹窗答题、AI 自动作业与考试、PPT 转文本、多 LLM 后端、代理支持。全部基于同步 httpx + threading 实现，无 asyncio。

## 2. 模块架构

```
src/zhs/
├── __init__.py
├── __main__.py          # CLI 入口（typer app，命令式：init/login/play/homework/exam/fetch）
├── config.py            # 配置管理（TOML，AppConfig + ConfigManager）
├── crypto.py            # AES-128-CBC / ev 编码 / Hike 签名 / WatchPoint
├── session.py           # HTTP 会话管理（同步 httpx，多种加密查询方法）
├── login.py             # 扫码登录
├── exceptions.py        # 全局异常定义
├── logger.py            # loguru 日志配置（filter 脱敏）
├── zhidao/              # 知到共享课模块
│   ├── __init__.py
│   ├── course.py        # 课程列表与上下文
│   ├── video.py         # 视频刷课
│   ├── quiz.py          # 弹窗答题
│   ├── models.py        # 数据模型
│   └── homework/        # 知到作业模块
│       ├── __init__.py
│       ├── scanner.py   # 作业扫描
│       ├── worker.py    # 作业执行
│       ├── analyzer.py  # 答案分析
│       ├── cache.py     # 答案缓存
│       └── models.py    # 作业数据模型
├── hike/                # Hike 职教云课程模块
│   ├── __init__.py
│   ├── course.py        # 课程列表与上下文
│   ├── video.py         # 视频刷课
│   └── models.py        # 数据模型
├── ai/                  # AI 智慧课程模块
│   ├── __init__.py
│   ├── course.py        # AI 课程管理（编排视频/作业/考试）
│   ├── video.py         # AI 视频播放器（AiVideoPlayer）
│   ├── homework.py      # AI 作业上下文（HomeworkCtx）
│   ├── exam.py          # AI 考试上下文（ExamCtx）
│   ├── ppt.py           # PPT 转文本（PptConverter，python-pptx）
│   └── models.py        # 数据模型
├── llm/                 # LLM 答题模块
│   ├── __init__.py
│   ├── base.py          # LLMProvider 抽象基类
│   ├── openai.py        # OpenAI 兼容接口
│   ├── zhidao.py        # 智慧树内置 AI
│   └── prompts.py       # Prompt 模板与答案解析
└── utils/               # 工具模块
    ├── __init__.py
    ├── display.py       # 终端显示（进度条、二维码、树形视图、彩色消息）
    ├── cookie.py        # Cookie 序列化/反序列化
    └── path.py          # 路径工具
```

## 3. 功能清单

### 3.1 配置管理

- **配置文件**：`~/.zhs/config.toml`（TOML 格式，支持注释）
- **配置结构**：`AppConfig` 顶层 + 多个嵌套子配置（`VideoConfig` / `HomeworkConfig` / `ExamConfig` / `DisplayConfig` / `ProxyConfig` / `QRConfig` / `AIConfig` / `CryptoConfig` / `UrlConfig`）
- **配置迁移**：`ConfigManager.migrate(json_path)` 支持从旧版 JSON 配置迁移到 TOML
- **CLI 参数覆盖**：CLI 参数优先级高于配置文件（如 `--speed` 覆盖 `video.*_speed`，`--homework-threshold` 覆盖 `homework.threshold`）
- **默认配置**：见 [config.toml.example](../config.toml.example)

### 3.2 登录系统

#### 3.2.1 扫码登录（唯一登录方式）

- 从 `qrCodeLogin/getLoginQrImg` 获取二维码图片和 `qrToken`
- 支持两种二维码显示方式：
  - 系统默认图片查看器打开（PIL）
  - 终端 Unicode 字符渲染（`--show-in-terminal`）
- 支持将二维码保存到指定路径（`--image-path` 或 `qr.image_path`）
- 轮询 `qrCodeLogin/getLoginQrInfo` 检查扫码状态：
  - `-1`：未扫描
  - `0`：已扫描待确认（仅提示一次）
  - `1`：已确认，获取一次性密码完成登录
  - `2`：二维码过期，自动重新获取（递归，带 `_max_retries` 防止无限递归）
  - `3`：用户取消登录

#### 3.2.2 Cookie 持久化

- 将 cookies 序列化为 JSON 列表保存到 `~/.zhs/cookies.json`
- 启动时尝试从 `cookies.json` 恢复会话
- 恢复时验证 cookies 有效性（尝试获取课程列表）
- 设置 cookies 时自动解析 `uuid`（从 `CASLOGC` cookie 的 JSON 中提取），并设置 `exitRecod_{uuid}=2`

### 3.3 知到（Zhidao）共享课程

#### 3.3.1 课程列表获取

- API：`onlineservice-api.zhihuishu.com/gateway/t/v1/student/course/share/queryShareCourseInfo`
- 分页获取所有课程（每页 5 条）
- 使用 `home_key` 加密

#### 3.3.2 课程上下文

- 跨站登录（`gologin`，返回 HTML 不解析 JSON）
- 查询课程信息（`queryCourse`）
- 获取章节视频列表（`videoList`）
- 查询学习状态（`queryStudyInfo`）
- 缓存课程上下文（cookies、headers、视频信息）

#### 3.3.3 视频刷课

- 获取 `prelearningNote` 生成 `learningTokenId`（Base64 编码）
- 获取弹窗题目信息（`loadVideoPointerInfo`）
- 模拟视频播放主循环：
  - 按速度推进播放时间
  - 随机暂停（0.25% 概率暂停 60 秒，模拟真人）
  - 每 2 秒更新 WatchPoint
  - 遇到弹窗题目时：获取题目详情 → 自动答题 → 保存答案
  - 每 30 秒向数据库上报进度（`saveDatabaseIntervalTimeV2`）
  - 显示进度条
- 已观看视频自动跳过（`watchState == 1` 且 `end_thre <= 1.0`）
- 调用 `watchVideo` 初始化视频播放（在新线程中请求视频流）
- 调用 `threeDimensionalCourseWare` 模拟课件访问

#### 3.3.4 弹窗答题

- 从 `loadVideoPointerInfo` 获取题目时间点
- 按时间排序，跳过已播放过的题目
- 到达题目时间点时获取题目详情（`lessonPopupExam`）
- 自动选择正确答案（`answerZhidao`：选择 `result == '1'` 的选项）
- 保存答案（`saveLessonPopupExamSaveAnswer`）
- 答题延迟机制（`answer_delay=2` 递减，防止请求过快）

#### 3.3.5 知到作业（zhidao/homework/）

**作业扫描（HomeworkScanner）**：
- API：`studentexam-api.zhihuishu.com/studentExam/gateway/t/v1/student/getStudentHomework`
- 使用 `exam_key` 加密，**不发送 `dateFormate`** 字段（与知到视频 API 不同）
- 检查 `status` 字段（`"200"` 为成功）
- 分页扫描课程下所有作业
- `filter_pending` 过滤待处理作业（state=1 未提交，或 state=4 已提交但未达标且可重做）

**作业执行（HomeworkWorker）**：
- `doHomework` 获取题目详情（含 `eid` 加密 ID）
- 顺序处理题目（不并发，避免 API 限流）
- 每题保存后 sleep `homework.delay_min` ~ `delay_max` 秒
- `saveStudentAnswer` 保存单题答案
- `submit` 提交作业，获取得分
- `lookHomework` + `getStuAnswerInfo` 查看已提交作业的对错详情
- 未达标且可重做时调用 `saveCourseTran` 重置后重做（受 `homework.max_submit` 限制）

**答案分析（HomeworkAnalyzer）**：
- 解析 `getStuAnswerInfo` 返回的答题详情
- 判断每题对错，提取正确答案
- 调用 AI 解析接口（`ai_analysis_run`，SSE 流式）获取题目解析
- 更新本地答案缓存

**答案缓存（HomeworkCache）**：
- 按课程 ID + 作业 ID 分组存储
- 缓存键：`{questionId}_{version}`（version=1 时无后缀）
- 答题前查缓存，提交后根据对错更新缓存

### 3.4 职教云（Hike）课程

#### 3.4.1 课程列表获取

- API：`hike.zhihuishu.com/student/course/aided/getMyCourseList`
- 使用 `uuid` 和时间戳参数

#### 3.4.2 课程上下文

- 获取资源菜单树（`queryResourceMenuTree`）
- 递归遍历树结构

#### 3.4.3 视频刷课

- 获取文件信息（`stuViewFile`）
- 调用 `watchVideo` 初始化
- 模拟播放循环：
  - 默认速度 1.25x
  - 每 30 秒上报进度（`saveStuStudyRecord`）
  - 上报时使用签名（`sign_hike`，MD5 哈希）
- 已完成文件自动跳过（`studyTime >= totalTime * end_thre`）
- `saveStuStudyRecord` 返回值覆盖 `played_time`（与服务器同步）

#### 3.4.4 文件类型处理

- `dataType == 3`：视频，调用 `play_video`
- `dataType == None` 且有 `file_id`：普通文件，调用 `play_file`
- `dataType == None` 且无 `file_id`：跳过（测验、讨论等空节点）
- 其他 `dataType`：检查 `file_id` 和 `file_name` 是否存在，存在则 `play_file`，否则跳过 + 日志
- `play_file` 内部 try/except 防护 KeyError

### 3.5 AI 智慧课程

#### 3.5.1 课程列表获取

- API：`onlineservice-api.zhihuishu.com/gateway/t/v1/student/queryStudentAICourseList`
- 使用 `home_key` 加密

#### 3.5.2 知识点获取

- API：`kg-ai-run.zhihuishu.com/run/gateway/t/stu/knowledge-study/course-basic`
- 使用 `ai_key` 加密
- 返回主题列表（`cakeThemeList`）和知识点列表（`knowledgeList`）

#### 3.5.3 资源学习

- 获取知识点资源列表（`listKnowledgeResources`）
- 资源类型处理：
  - `resourceType == 2, distributeType == 1`：文本，直接标记完成
  - `resourceType == 1, distributeType == 4`：PPT，标记完成并收集 URL
  - `resourceType == 1, distributeType == 3`：视频，调用 `AiVideoPlayer.play_video`
  - `resourceType == 2, distributeType == 2`：智慧树课程视频，调用 `AiVideoPlayer.play_video`
  - 其他：尝试标记完成
- 已完成资源自动跳过

#### 3.5.4 AI 视频刷课（AiVideoPlayer）

- 获取视频时长（`get-video-time`）
- 模拟播放循环：
  - 默认速度 1.5x，每 2 秒上报一次进度（实际推进 `speed * 2` 秒）
  - 上报 API：`studyRecord/report`
- 模拟真实视频播放请求（独立线程，反检测）

#### 3.5.5 AI 作业（HomeworkCtx）

**作业流程**：
1. 加载答案缓存（本地 JSON 文件）
2. 打开作业（`openExam`）
3. 启动心跳线程定期更新作业用时（`updateUserUsedTime`，daemon 线程，通过 `_stopped` 标志退出）
4. 获取试卷内容（`getExamSheetInfo`）
5. **顺序处理**题目（不并发，避免 API 限流）
6. 每题保存后 sleep `homework.delay_min` ~ `delay_max` 秒
7. 提交作业（`submit`）
8. 检查结果，更新答案缓存

**答题策略**：
- 优先从本地缓存获取答案
- 缓存未命中时使用 AI 生成答案
- AI 生成失败时使用兜底答案
- 支持题目类型：`1` 单选、`2` 多选、`3` 填空、`14` 判断

**答案缓存**：
- 按课程 ID 和作业 ID 分别存储
- `ai_homework_cache/{courseId}/{examTestId}.json`：当前作业答案
- `ai_homework_cache/{courseId}/data.json`：课程全部答案汇总
- 支持版本号（`questionId_version`）

**掌握度判断**：
- `masteryScore > ai_homework_threshold`（默认 90）→ 跳过该作业

#### 3.5.6 AI 考试（ExamCtx）

**与 HomeworkCtx 的区别**：
- `taskList` 使用 `ai_key` 加密（`ai_task_query`）
- `openExam` / `getAnswerSheetInformation` / `getExamQuestionInfo` / `saveBatchAnswer` / `updateUserUsedTime` / `submit` 使用 `exam_key`（`ai_exam_query` / `ai_exam_submit`）
- `openExamDetail` 使用 `ai_key`（`ai_task_query`），用于提交后判断是否可查看答案
- **批量保存** `saveBatchAnswer`（每 `exam.save_nums` 题保存一次）
- 填空题 answer 用 `/` 分隔
- submit 后若可查看答案（`isLookAnswer/isAllowShowDetail=1`）则保存正确答案到缓存

**考试流程**：
1. 获取未完成考试任务列表（`taskList`，`taskType=1`，`status=0`）
2. 对每个考试创建 `ExamCtx` 执行答题
3. 若 `--submit`，提交后通过 `openExamDetail` 判断是否可查看答案，可查看则保存缓存

### 3.6 LLM 答题模块

#### 3.6.1 OpenAI 兼容接口（OpenAIProvider）

- 使用 `openai` 库调用任意 OpenAI 兼容 API
- 支持 stream 模式
- 支持 max_retries 和 retry_delay
- Token 超长时自动截断（保留最后 `ai.max_token` tokens，默认 27900）

#### 3.6.2 智慧树内置 AI（ZhidaoAIProvider）

- API：`kg-ai-run.zhihuishu.com/run/gateway/t/stu/qa/platform/stream`
- 模型：`moonshot-v1-32k`
- 使用 `self._session._get_client().post()` 发送请求（ZhsSession 无 `post` 方法）
- 支持 stream 模式（SSE 解析）

#### 3.6.3 Prompt 模板

- **单选题**：要求从选项中选择最合适的答案，输出 JSON 格式
- **多选题**：要求选择所有正确答案，输出 JSON 格式
- **判断题**：同单选题模板
- **填空题**：要求填写空白处内容，每空一行
- 所有模板包含：课程名、主题、知识点、参考资料
- 答案格式要求：放在 ` ```answer ``` ` 代码块中

#### 3.6.4 答案解析

- 选择题/判断题：从 ` ```answer\n[{"id": ..., "content": ...}]\n``` ` 中提取选项 ID
- 填空题：从 ` ```answer\n答案1\n答案2\n``` ` 中按行提取
- 解析失败时先尝试 `json.loads`，再尝试 `ast.literal_eval`

### 3.7 PPT 转文本（PptConverter）

- 使用 `python-pptx` 本地提取 PPT 文本
- 流程：下载 PPT → 本地解析文本 → 返回内容
- `cleanup_local=True`（默认）：转换完成后自动删除本地临时文件
- PPT 内容作为参考资料提供给 AI 答题

### 3.8 加解密模块

> **注意**：所有密钥和 URL 均可通过 `config.toml` 的 `[crypto]` 和 `[urls]` 段覆盖，不硬编码在代码中。以下为默认值。

#### 3.8.1 AES 加密（Cipher）

- 算法：AES-128-CBC
- IV（默认）：`1g3qqdh4jvbskb9x`
- 密钥（默认）：
  - `home_key`：`7q9oko0vqb3la20r`（课程列表）
  - `video_key`：`azp53h0kft7qi78q`（视频相关）
  - `qa_key`：`kcGOlISPkYKRksSK`（答题相关）
  - `ai_key`：`hw2fdlwcj4cs1mx7`（AI 课程相关）
  - `exam_key`：`onbfhdyvz8x7otrp`（作业/考试相关）
- PKCS7 填充
- 加密后 Base64 编码
- 密钥长度必须为 16 字节，否则抛 `ZhsError`

#### 3.8.2 ev 编码（encode_ev）

- XOR 异或编码，密钥循环使用
- 默认密钥：`zzpttjd`
- 用于视频进度上报数据编码
- 仅编码（`encode_ev`），无解码（`decode_ev` 已删除）

#### 3.8.3 Hike 签名（sign_hike）

- MD5 哈希
- 拼接格式：`SALT + uuid + courseId + fileId + studyTotalTime + startDate + endDate + endWatchTime + startWatchTime + uuid`
- SALT（默认）：`o6xpt3b#Qy$Z`

#### 3.8.4 WatchPoint

- 视频观看轨迹点生成器
- `gen(time) = time // 5 + 2`
- 初始值 `[0, 1]`
- `add(end, start)` 按 2 秒间隔生成轨迹点
- `get()` 返回逗号分隔的字符串
- `reset(init)` 重置状态

### 3.9 终端显示

#### 3.9.1 进度条（progress_bar）

- 显示格式：`{prefix} |{bar}| {percent}% {suffix}`
- 自动适配终端宽度
- 完成后清除行

#### 3.9.2 二维码显示

- **Unicode 模式**：使用 CP437 扩展字符渲染，47×47 分辨率
- **TTY 模式**：使用 ANSI 转义序列色块渲染，47×47 分辨率
- **系统查看器**：使用 PIL 打开图片

#### 3.9.3 树形视图（tree_print）

- 课程 → 章节 → 课时 → 视频层级显示
- 前缀 `  |` 缩进
- 自动截断超长行（适配终端宽度）

#### 3.9.4 彩色消息

- `msg_info` / `msg_done` / `msg_warn` / `msg_error` / `msg_skip`
- `course_tag`：课程类型标签（zhidao/hike/ai）

### 3.10 日志模块

基于 `loguru` 的生产级日志系统。

- **双通道输出**：stderr（控制台，可选）+ 文件（持久化）
- **控制台格式**：`<level>{level:<7}</level> | <cyan>{name}</cyan> - {message}`
- **文件格式**：`{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {thread.name} | {name}:{function}:{line} | {message}`
- **文件轮转**：按天轮转（`00:00`），保留 30 天，gzip 压缩
- **日志目录**：`<data_dir>/logs/`（`data_dir` 由 `utils/path.py` 的 `get_data_dir()` 决定）
- **级别过滤**：
  - 控制台：由 `AppConfig.display.log_level` 控制（默认 INFO），`-d/--debug` 强制 DEBUG
  - 文件：始终 DEBUG 级别（完整记录）
- **敏感信息过滤**：通过 `filter` 参数（每个 sink 带 `_sensitive_filter`），在写入前修改 `record["message"]`，自动脱敏 cookie、token、password、apiKey、Authorization Bearer 等字段
- **初始化时机**：CLI 启动时由 `_setup_logger(config, debug, console_log)` 一次性配置

### 3.11 CLI 命令

ZHS CLI 采用命令式接口（typer），共 6 个子命令：

#### 3.11.1 zhs init

初始化 `~/.zhs/` 目录与默认配置。

```bash
zhs init
```

#### 3.11.2 zhs login

扫码登录智慧树。

| 参数 | 说明 |
|------|------|
| `--show-in-terminal` | 终端显示二维码 |
| `--image-path PATH` | 二维码保存路径 |
| `--proxy URL` | 代理 |
| `-d, --debug` | 调试模式 |
| `--console-log` | 日志输出到控制台 |

#### 3.11.3 zhs play

刷视频。

| 参数 | 缩写 | 说明 |
|------|------|------|
| `--course` | `-c` | 课程 ID（可多次指定） |
| `--type` | | 课程类型：zhidao/hike/ai/auto |
| `--ai-course` | | AI 课程 courseId |
| `--ai-class` | | AI 课程 classId |
| `--speed` | `-s` | 播放速度 |
| `--limit` | `-l` | 每门课程时间限制（分钟） |
| `--proxy` | | 代理 |
| `-d, --debug` | | 调试模式 |
| `--console-log` | | 日志输出到控制台 |

#### 3.11.4 zhs homework

写作业。

| 参数 | 缩写 | 说明 |
|------|------|------|
| `--course` | `-c` | 课程 ID（可多次指定） |
| `--type` | | 课程类型：zhidao/ai/auto |
| `--url` | | 作业 URL（从浏览器复制） |
| `--ai-course` | | AI 课程 courseId |
| `--ai-class` | | AI 课程 classId |
| `--no-ai` | | 不使用 AI 模型（随机生成） |
| `--homework-threshold` | | 满分阈值百分比（0-100） |
| `--max-submit` | | 最大提交次数 |
| `--proxy` / `-d` / `--console-log` | | 同上 |

#### 3.11.5 zhs exam

AI 课程考试。

| 参数 | 缩写 | 说明 |
|------|------|------|
| `--course` | `-c` | 课程 ID |
| `--type` | | 课程类型（目前仅支持 ai） |
| `--ai-course` | | AI 课程 courseId |
| `--ai-class` | | AI 课程 classId |
| `--submit` | | 答题后提交考试（默认不提交） |
| `--proxy` / `-d` / `--console-log` | | 同上 |

#### 3.11.6 zhs fetch

获取课程数据。

| 参数 | 说明 |
|------|------|
| `--type` | 数据类型：all/course/homework（默认 all） |
| `--proxy` / `-d` / `--console-log` | 同上 |

#### 3.11.7 课程类型自动检测

- `--type` 参数优先级最高，显式指定 `zhidao`/`hike`/`ai`/`auto` 时直接路由
- 自动检测（`auto` 或未指定）：含字母 → 知到，纯数字 → Hike
- AI 课程通过 `--ai-course` + `--ai-class` 或 `-c courseId:classId --type ai` 指定

### 3.12 CAS SSO 认证

`studentexam-api` 域名不像 `studyservice-api` 有 `/login/gologin`，需要通过 CAS SSO 获取认证。

- 流程：访问 `passport/cas/login?service=xxx` → 302 带 ticket → ticket 验证设置 session cookie
- `ZhsSession.exam_sso_login()` 封装此流程
- 失败时抛 `ZhsError`（CASTGC cookie 已过期，需重新登录）
- 知到作业功能（`zhs homework`）执行前自动调用

## 4. API 端点汇总

> **注意**：所有基础 URL 均可通过 `config.toml` 的 `[urls]` 段覆盖。以下为默认域名。

### 知到视频（studyservice-api.zhihuishu.com）

| 端点 | 方法 | 用途 | 加密 |
|------|------|------|------|
| `/login/gologin` | GET | 跨站登录 | — |
| `/gateway/t/v1/learning/queryCourse` | POST | 查询课程信息 | video_key |
| `/gateway/t/v1/learning/videolist` | POST | 获取视频列表 | video_key |
| `/gateway/t/v1/learning/queryStuyInfo` | POST | 查询学习状态 | video_key |
| `/gateway/t/v1/learning/prelearningNote` | POST | 获取学习令牌 | video_key |
| `/gateway/t/v1/popupAnswer/loadVideoPointerInfo` | POST | 获取弹窗题目 | video_key |
| `/gateway/t/v1/popupAnswer/lessonPopupExam` | POST | 获取题目详情 | video_key |
| `/gateway/t/v1/popupAnswer/saveLessonPopupExamSaveAnswer` | POST | 保存弹窗答案 | video_key |
| `/gateway/t/v1/learning/saveDatabaseIntervalTimeV2` | POST | 上报视频进度 V2 | video_key |
| `/gateway/t/v1/course/threeDimensionalCourseWare` | GET | 课件访问 | — |

### 知到课程列表（onlineservice-api.zhihuishu.com）

| 端点 | 方法 | 用途 | 加密 |
|------|------|------|------|
| `/gateway/t/v1/student/course/share/queryShareCourseInfo` | POST | 获取知到课程列表 | home_key |
| `/gateway/t/v1/student/queryStudentAICourseList` | POST | 获取 AI 课程列表 | home_key |

### 知到作业（studentexam-api.zhihuishu.com）

> **注意**：使用 `exam_key` 加密，**不发送 `dateFormate`** 字段，检查 `status` 字段（`"200"` 为成功）。

| 端点 | 方法 | 用途 |
|------|------|------|
| `/studentExam/gateway/t/v1/student/getStudentHomework` | POST | 扫描作业列表 |
| `/studentExam/gateway/t/v1/student/saveCourseTran` | POST | 重做作业（重置状态） |
| `/studentExam/gateway/t/v1/student/doHomework` | POST | 开始做作业 |
| `/studentExam/gateway/t/v1/student/lookHomework` | POST | 查看已提交作业 |
| `/studentExam/gateway/t/v1/answer/saveStudentAnswer` | POST | 保存单题答案 |
| `/studentExam/gateway/t/v1/answer/submit` | POST | 提交作业 |
| `/studentExam/gateway/t/v1/answer/getStuAnswerInfo` | POST | 获取答题详情 |

### Hike（hike.zhihuishu.com）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/student/course/aided/getMyCourseList` | GET | 获取课程列表 |
| `/studyResources/stuResouce/queryResourceMenuTree` | GET | 获取资源树 |
| `/studyResources/stuResouce/stuViewFile` | GET | 获取文件信息 |
| `/stuStudy/saveStuStudyRecord` | GET | 上报学习进度（含签名） |

### AI 课程（kg-ai-run.zhihuishu.com）

| 端点 | 方法 | 用途 | 加密 |
|------|------|------|------|
| `/run/gateway/t/stu/knowledge-study/course-basic` | POST | 获取知识点 | ai_key |
| `/run/gateway/t/stu/studyRecord/completed` | POST | 标记资源完成 | ai_key |
| `/run/gateway/t/stu/studyRecord/report` | POST | 上报视频进度 | ai_key |
| `/run/gateway/t/stu/resources/list-knowledge-resource` | POST | 获取资源列表 | ai_key |
| `/run/gateway/t/stu/resources-lab/get-video-time` | POST | 获取视频时长 | ai_key |
| `/run/gateway/t/stu/qa/platform/stream` | POST | 智慧树 AI 对话（SSE） | ai_key |

### AI 考试任务（kg-run-student.zhihuishu.com）

> **注意**：使用 `ai_key` 加密，发送 `dateFormate` 字段，检查 `code` 字段（`200` 为成功）。

| 端点 | 方法 | 用途 |
|------|------|------|
| `/student/gateway/t/task/taskList` | POST | 获取考试任务列表 |

### AI 考试（studentexamtest.zhihuishu.com）

> **注意**：使用 `exam_key` 加密，发送 `dateFormate` 字段，检查 `code` 字段（`0` 为成功）。

| 端点 | 方法 | 用途 |
|------|------|------|
| `/gateway/t/v1/exam/user/openExam` | POST | 打开考试 |
| `/gateway/t/v1/exam/user/updateUserUsedTime` | POST | 更新考试用时（心跳） |
| `/gateway/t/v1/exam/user/getExamSheetInfo` | GET | 获取试卷内容 |
| `/gateway/t/v1/question/getExamQuestionInfo` | GET | 获取题目内容 |
| `/gateway/t/v1/answer/saveBatchAnswer` | POST | 批量保存答案 |
| `/gateway/t/v1/exam/user/submit` | POST | 提交考试 |
| `/gateway/t/v1/exam/user/openExamDetail` | POST | 查看考试详情（判断是否可查看答案） |

### AI 解析（ai-course-assistant-api.zhihuishu.com）

> **注意**：明文 JSON POST，SSE 流式响应，不加密。

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/v1/user/info` | GET | 获取用户 ID |
| `/api/v1/question/analysis/thread/run` | POST | AI 解析（SSE 流式） |

### 登录（passport.zhihuishu.com）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/login` | GET | 登录页面 |
| `/qrCodeLogin/getLoginQrImg` | GET | 获取二维码 |
| `/qrCodeLogin/getLoginQrInfo` | GET | 查询扫码状态 |
| `/cas/login?service=xxx` | GET | CAS SSO 认证 |

### 其他

| 端点 | 方法 | 用途 |
|------|------|------|
| `newbase.zhihuishu.com/video/initVideo` | GET | 初始化视频播放 |

## 5. 关键数据结构

### WatchPoint

- 每 2 秒记录一个观察点
- 生成公式：`time // 5 + 2`
- 输出格式：逗号分隔的整数序列

### ev 编码数据（知到视频进度上报 V2）

```
[recruitId, lessonId, smallLessonId, videoId, chapterId, '0', playTimes, totalStudyTime, HMS, uuid+'zhs']
```

### Hike 签名数据

```
SALT + uuid + courseId + fileId + studyTotalTime + startDate + endDate + endWatchTime + startWatchTime + uuid
```

### 答案缓存格式

```json
{
  "questionId_version": {
    "version": 1,
    "question": "题目内容",
    "answer": "选项ID#@#选项ID",
    "answer_content": "选项文本\n选项文本",
    "questionDict": { ... }
  }
}
```

## 6. 异常处理

| 异常 | 触发条件 |
|------|----------|
| `ZhsError` | ZHS 基础异常 |
| `ApiError` | API 返回错误（携带 `code` 和 `message`） |
| `CaptchaRequired` | 服务端要求验证码（API 返回 code -12） |
| `SliderVerificationRequired` | 作业答题需要滑块验证 |
| `LoginFailed` | 登录失败 |
| `TimeLimitExceeded` | 刷课时间超过设定限制 |

异常链规范：`raise ZhsError(...) from e`，禁止裸 `raise ZhsError`。

## 7. 技术栈

| 类别 | 选型 | 说明 |
|------|------|------|
| Python | >=3.13 | 支持 match 语句、类型参数语法等新特性 |
| HTTP 客户端 | httpx | **同步 API**，兼容 requests 风格 |
| 数据模型 | pydantic v2 | 类型安全、自动验证、JSON 序列化、alias 映射 |
| CLI | typer | 类型注解自动生成参数，命令式接口 |
| 日志 | loguru | 双通道输出、filter 脱敏、按天轮转 |
| 加密 | pycryptodome | AES-128-CBC 加密 |
| 配置 | TOML | Python 3.11+ 标准库 tomllib + tomli-w |
| LLM | openai | OpenAI 兼容 API 调用 |
| Token 计数 | tiktoken | Prompt 长度截断 |
| PPT 解析 | python-pptx | 本地 PPT 文本提取 |
| 图片处理 | Pillow + qrcode | 二维码生成与渲染 |
| 测试 | pytest + respx + freezegun | TDD 开发，HTTP Mock，时间 Mock |
| Linter | ruff | 集成 flake8 + isort + pyupgrade + bugbear + simplify |
| 类型检查 | mypy | strict 模式 + pydantic 插件 |
| 格式化 | ruff format | 替代 black，统一工具链 |

### 执行模型

- **全部同步**：所有代码均为同步实现，使用 `httpx.Client` + `time.sleep()`
- **线程使用**：仅 `_watch_video`（视频流请求，daemon）和 `_heartbeat`（考试/作业心跳，daemon）使用 threading
- **禁止 asyncio**：项目不使用 `asyncio`，无 `async def` / `await` / `httpx.AsyncClient`

### 项目配置 (pyproject.toml)

```toml
[project]
name = "zhs"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "httpx>=0.28",
    "pydantic>=2.10",
    "typer>=0.15",
    "loguru>=0.7",
    "pycryptodome>=3.21",
    "openai>=2.41.1",
    "tiktoken>=0.9",
    "Pillow>=11.0",
    "qrcode>=8.2",
    "tomli-w>=1.2.0",
    "python-pptx>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=6.0",
    "respx>=0.22",
    "freezegun>=1.5",
    "ruff>=0.8",
    "mypy>=1.13",
]

[project.scripts]
zhs = "zhs.__main__:app"

[tool.ruff]
line-length = 120
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]
"tests/**/*.py" = ["B011"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-m 'not integration'"
markers = [
    "unit: 单元测试",
    "integration: 集成测试（需真实 API）",
    "e2e: 端到端测试",
]

[tool.mypy]
python_version = "3.13"
strict = true
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false
```

## 8. 设计约束

1. **密钥不硬编码**：所有密钥从 `CryptoConfig` 获取，构造时显式传入
2. **URL 不硬编码**：所有 URL 从 `UrlConfig` 获取
3. **异常链**：`raise ZhsError(...) from e`，禁止裸 `raise ZhsError`
4. **线程安全**：`_watch_video` 使用独立 `httpx.Client`，daemon=True，全捕获 Exception
5. **同步延迟**：所有代码均为同步，使用 `time.sleep()`，禁止 `asyncio.sleep()`
6. **顺序处理**：`HomeworkCtx` 顺序处理题目（不并发），每题 sleep 3-5s，避免 API 限流
7. **心跳线程**：`HomeworkCtx._heartbeat` / `ExamCtx._heartbeat` 使用 `threading.Thread(daemon=True)`，通过 `_stopped` 标志退出
8. **本地文件清理**：`PptConverter` 默认 `cleanup_local=True`
9. **课程类型**：CLI `--type` 支持 `zhidao/hike/ai/auto` 显式覆盖自动检测
10. **Hike 资源树**：无 `file_id` 的非标准节点跳过 + 日志，`play_file` 内 try/except 防护 KeyError
11. **测试 Mock**：`mock_session` fixture 用 `with respx.mock: yield`，禁止 `@respx.mock` 装饰器
12. **AI 作业命名**：AI 课程的"考试"统一称为"作业"（homework），代码中使用 `HomeworkCtx`，文件名 `ai/homework.py`
13. **CLI 命令式**：使用 `zhs play/homework/exam/fetch` 命令式接口，禁止旧的 `zhs -c ID` 风格
14. **作业 API 加密**：知到作业 API（`studentexam-api`）使用 `exam_key` 加密，**不发送 `dateFormate`** 字段
15. **AI 考试 API 加密**：AI 考试 API（`studentexamtest`）使用 `exam_key` 加密，**发送 `dateFormate`** 字段，检查 `code` 字段
16. **禁止 asyncio**：项目不使用 `asyncio`，所有代码同步实现
