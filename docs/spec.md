# ZHS 规格说明书

## 1. 项目概述

ZHS 是一个智慧树（zhihuishu.com）自动刷课工具，支持普通共享课程（知到/Zhidao）、职教云课程（Hike）以及 AI智慧课程三种课程类型的自动学习。核心功能包括：自动登录、视频进度模拟、弹窗答题、AI 课程考试自动作答。

## 2. 模块架构

```
zhs/
├── __init__.py
├── __main__.py          # CLI 入口
├── config.py            # 配置管理
├── crypto.py            # 加解密（AES、ev 编码、签名）
├── session.py           # HTTP 会话管理
├── login.py             # 登录（扫码）
├── zhidao/              # 知到共享课程模块
│   ├── __init__.py
│   ├── course.py        # 课程列表与上下文
│   ├── video.py         # 视频刷课
│   └── quiz.py          # 弹窗答题
├── hike/                # 职教云课程模块
│   ├── __init__.py
│   ├── course.py        # 课程列表与上下文
│   └── video.py         # 视频刷课
├── ai/                  # AI 课程模块
│   ├── __init__.py
│   ├── course.py        # AI 课程学习
│   ├── exam.py          # AI 考试上下文
│   └── ppt.py           # PPT 转文本
├── llm/                 # LLM 答题模块
│   ├── __init__.py
│   ├── base.py          # 基类
│   ├── openai.py        # OpenAI 兼容接口
│   └── zhidao.py        # 智慧树内置 AI
├── utils/               # 工具模块
│   ├── __init__.py
│   ├── display.py       # 终端显示（进度条、二维码、树形视图）
│   ├── cookie.py        # Cookie 序列化/反序列化
│   └── path.py          # 路径工具
└── logger.py            # 日志模块
```

## 3. 功能清单

### 3.1 配置管理

- **配置文件**：`config.json`，存储代理、日志级别、AI 配置等
- **配置版本迁移**：自动检测 `config_version`，将旧版配置升级到新版
- **默认配置**：
  ```json
  {
    "qrlogin": true,
    "save_cookies": true,
    "proxies": {},
    "logLevel": "INFO",
    "tree_view": true,
    "progressbar_view": true,
    "qr_extra": { "show_in_terminal": null, "ensure_unicode": false },
    "image_path": "",
    "config_version": "1.4.0",
    "ai": {
      "enabled": true,
      "use_zhidao_ai": true,
      "openai": { "api_base": "", "api_key": "", "model_name": "" },
      "ppt_processing": {
        "provide_to_ai": false,
        "moonShot": { "base_url": "", "api_key": "", "delete_after_convert": true }
      },
      "use_stream": true
    }
  }
  ```
- **CLI 参数覆盖**：支持通过命令行参数覆盖配置文件中的值

### 3.2 登录系统

#### 3.2.1 扫码登录
- 从 `qrCodeLogin/getLoginQrImg` 获取二维码图片和 `qrToken`
- 支持三种二维码显示方式：
  - 系统默认图片查看器打开
  - 终端 Unicode 字符渲染
  - 终端 TTY 色块渲染
- 支持将二维码保存到指定路径（`image_path`）
- 轮询 `qrCodeLogin/getLoginQrInfo` 检查扫码状态：
  - `-1`：未扫描
  - `0`：已扫描待确认
  - `1`：已确认，获取一次性密码完成登录
  - `2`：二维码过期，自动重新获取
  - `3`：用户取消登录

#### 3.2.2 Cookie 持久化
- 将 cookies 序列化为 JSON 列表保存到 `cookies.json`
- 启动时尝试从 `cookies.json` 恢复会话
- 恢复时验证 cookies 有效性（尝试获取课程列表）

### 3.3 知到（Zhidao）共享课程

#### 3.3.1 课程列表获取
- API：`onlineservice-api.zhihuishu.com/gateway/t/v1/student/course/share/queryShareCourseInfo`
- 分页获取所有课程（每页 5 条）
- 使用 `HOME_KEY` 加密

#### 3.3.2 课程上下文
- 跨站登录（`gologin`）
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
  - 可选缓存上报（`saveCacheIntervalTime`，当前禁用）
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

### 3.4 职教云（Hike）课程

#### 3.4.1 课程列表获取
- API：`hikeservice.zhihuishu.com/student/course/aided/getMyCourseList`
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
  - 上报时使用签名（`sign` 函数，MD5 哈希）
- 已完成文件自动跳过（`studyTime >= totalTime * end_thre`）

#### 3.4.4 文件类型处理
- `dataType == 3`：视频，调用 `fuckHikeVideo`
- `dataType == None`：测验（不支持）
- 其他类型：调用 `fuckFile`（仅标记已查看）

### 3.5 AI 课程

#### 3.5.1 课程列表获取
- API：`onlineservice-api.zhihuishu.com/gateway/t/v1/student/queryStudentAICourseList`

#### 3.5.2 知识点获取
- API：`kg-ai-run.zhihuishu.com/run/gateway/t/stu/knowledge-study/course-basic`
- 返回主题列表（`cakeThemeList`）和知识点列表（`knowledgeList`）

#### 3.5.3 资源学习
- 获取知识点资源列表（`listKnowledgeResources`）
- 资源类型处理：
  - `resourceType == 2, distributeType == 1`：文本，直接标记完成
  - `resourceType == 1, distributeType == 4`：PPT，标记完成并收集 URL
  - `resourceType == 1, distributeType == 3`：视频，调用 `fuckAiVideo`
  - `resourceType == 2, distributeType == 2`：智慧树课程视频，调用 `fuckAiVideo`
  - 其他：尝试标记完成
- 已完成资源自动跳过

#### 3.5.4 AI 视频刷课
- 获取视频时长（`get-video-time`）
- 模拟播放循环：
  - 默认速度 1.5x，每 2 秒上报一次进度
  - 上报 API：`studyRecord/report`
- 显示进度条

#### 3.5.5 AI 考试系统（ExamCtx）

**考试流程**：
1. 加载答案缓存（本地 JSON 文件）
2. 打开考试（`openExam`）
3. 启动心跳线程定期更新考试用时（`updateExamCostTime`，每 10 秒）
4. 获取试卷内容（`getExamSheetInfo`）
5. 逐题获取题目内容并作答
6. 提交考试（`submitExam`）
7. 检查结果，更新答案缓存

**答题策略**：
- 优先从本地缓存获取答案
- 缓存未命中时使用 AI 生成答案
- AI 生成失败时使用随机/兜底答案
- 支持题目类型：
  - `1`：单选题
  - `2`：多选题
  - `3`：填空题
  - `14`：判断题

**答案缓存**：
- 按课程 ID 和考试 ID 分别存储
- `aiexamAnswer/{courseId}/{examTestId}.json`：当前考试答案
- `aiexamAnswer/{courseId}/data.json`：课程全部答案汇总
- 支持版本号（`questionId_version`）
- 答题后自动写入磁盘
- 提交后根据正确答案更新缓存

**考试重试**：
- 掌握分数 > 90 时停止
- 掌握分数 < 30 且已尝试 > 4 次时放弃
- 否则继续重试

### 3.6 LLM 答题模块

#### 3.6.1 OpenAI 兼容接口
- 使用 `openai` 库调用任意 OpenAI 兼容 API
- 支持 stream 模式
- 支持 max_retries 和 retry_delay
- Token 超长时自动截断（保留最后 27900 tokens）

#### 3.6.2 智慧树内置 AI
- API：`ai-knowledge-map-platform.zhihuishu.com/knowledgemap/gateway/t/qa/platform/stream`
- 模型：`moonshot-v1-32k`
- 需要签名（MD5，前缀 `8ZflKEagfL`）
- 生成随机 `sessionNid`
- 支持 stream 模式

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

### 3.7 PPT 转文本（PptToTxt）

- 使用 MoonShot API 的文件提取功能
- 流程：下载 PPT → 上传到 MoonShot → 提取文本 → 返回内容
- 文件大小限制（默认 100MB）
- 缓存管理：
  - 本地文件缓存（`AiDownloadCache/`）
  - 远程文件缓存（避免重复上传）
  - 最大缓存文件数（默认 500）
  - 最大缓存大小（默认 8GB）
  - 可选立即删除远程文件
- PPT 内容作为参考资料提供给 AI 答题

### 3.8 加解密模块

> **注意**：所有密钥和 URL 均可通过 `config.toml` 的 `[crypto]` 和 `[urls]` 段覆盖，不再硬编码在代码中。以下为默认值。

#### 3.8.1 AES 加密（Cipher）
- 算法：AES-128-CBC
- IV（默认）：`1g3qqdh4jvbskb9x`
- 密钥（默认）：
  - `HOME_KEY`：`7q9oko0vqb3la20r`（课程列表）
  - `VIDEO_KEY`：`azp53h0kft7qi78q`（视频相关）
  - `QA_KEY`：`kcGOlISPkYKRksSK`（答题相关）
  - `AI_KEY`：`hw2fdlwcj4cs1mx7`（AI 课程相关）
  - `EXAM_KEY`：`onbfhdyvz8x7otrp`（考试相关）
- PKCS7 填充
- 加密后 Base64 编码

#### 3.8.2 ev 编码（getEv/revEv）
- XOR 异或编码，密钥循环使用
- 默认密钥：`zzpttjd`
- 备选密钥：`zhihuishu`
- 用于视频进度上报数据编码

#### 3.8.3 Hike 签名（sign）
- MD5 哈希
- 拼接格式：`SALT + uuid + courseId + fileId + studyTotalTime + startDate + endDate + endWatchTime + startWatchTime + uuid`
- SALT（默认）：`o6xpt3b#Qy$Z`

#### 3.8.4 智慧树 AI 签名
- MD5 哈希，前缀（默认）`8ZflKEagfL`
- 输入为 JSON 字符串（`messageList`、`modelCode`、`sessionNid`、`stream`）

### 3.9 终端显示

#### 3.9.1 进度条（progressBar）
- 显示格式：`{prefix} |{bar}| {percent}% {suffix}`
- 自动适配终端宽度
- 完成后清除行

#### 3.9.2 二维码显示
- **Unicode 模式**：使用 CP437 扩展字符渲染，47×47 分辨率
- **TTY 模式**：使用 ANSI 转义序列色块渲染，47×47 分辨率
- **系统查看器**：使用 PIL 打开图片

#### 3.9.3 树形视图
- 课程 → 章节 → 课时 → 视频层级显示
- 前缀 `  |` 缩进
- 自动截断超长行（适配终端宽度）

### 3.10 日志模块

基于 `loguru` 的生产级日志系统，替代旧版自定义 `MonoLogger`。

- **双通道输出**：stderr（控制台）+ 文件（持久化）
- **控制台格式**：彩色、紧凑，适合实时查看
  - `{time:HH:mm:ss} | {level:<7} | {message}`
- **文件格式**：完整时间戳 + 线程信息，适合事后排查
  - `{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {thread.name} | {name}:{function}:{line} | {message}`
- **文件轮转**：单文件 10 MB，保留最近 7 天，自动压缩归档
- **日志目录**：`<data_dir>/logs/`（`data_dir` 由 `utils/path.py` 的 `get_data_dir()` 决定）
- **级别过滤**：
  - 控制台：由 `AppConfig.log_level` 控制（默认 INFO）
  - 文件：始终 DEBUG 级别（完整记录）
- **模块标识**：通过 `logger.bind(module="zhidao")` 等标记来源模块
- **敏感信息过滤**：自动脱敏 cookie、token 等字段
- **初始化时机**：CLI 启动时由 `setup_logging(config)` 一次性配置，之后全局 `from loguru import logger` 即可使用

### 3.11 CLI 参数

| 参数 | 缩写 | 说明 |
|------|------|------|
| `--course` | `-c` | 课程 ID（支持多个） |
| `--videos` | `-v` | 视频 ID（支持多个） |
| `--speed` | `-s` | 播放速度 |
| `--threshold` | `-t` | 完成阈值（0-1，默认 0.91） |
| `--limit` | `-l` | 时间限制（分钟，0 为无限制） |
| `--qrlogin` | `-q` | 扫码登录（唯一登录方式） |
| `--debug` | `-d` | 调试模式 |
| `--fetch` | `-f` | 获取课程列表保存到文件 |
| `--show_in_terminal` | | 终端显示二维码 |
| `--proxy` | | 代理配置（http/https/socks5/all） |
| `--tree_view` | | 树形视图开关 |
| `--progressbar_view` | | 进度条开关 |
| `--image_path` | | 二维码图片保存路径 |
| `--aicourse` | `-ai` | AI 课程 ID 和班级 ID（两个参数） |
| `--noexam` | | 禁用 AI 考试 |

### 3.12 版本更新检查

- 从 `meta.json` 读取当前版本
- 请求 GitHub 获取最新版本
- 比较版本号提示更新

### 3.13 自动模式

- 未指定课程时自动刷所有课程（`fuckWhatever`）
- 自动检测课程类型（含字母为知到，纯数字为 Hike）
- 从 `execution.json` 读取课程列表（`--fetch` 生成）

## 4. API 端点汇总

> **注意**：所有基础 URL 均可通过 `config.toml` 的 `[urls]` 段覆盖。以下为默认域名。

### 知到（studyservice-api.zhihuishu.com）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/login/gologin` | GET | 跨站登录 |
| `/gateway/t/v1/learning/queryCourse` | POST | 查询课程信息 |
| `/gateway/t/v1/learning/videolist` | POST | 获取视频列表 |
| `/gateway/t/v1/learning/queryStudyReadBefore` | POST | 查询预习内容 |
| `/gateway/t/v1/learning/queryStuyInfo` | POST | 查询学习状态 |
| `/gateway/t/v1/learning/queryUserRecruitIdLastVideoId` | POST | 查询最近观看视频 |
| `/gateway/t/v1/learning/prelearningNote` | POST | 获取学习令牌 |
| `/gateway/t/v1/popupAnswer/loadVideoPointerInfo` | POST | 获取弹窗题目 |
| `/gateway/t/v1/popupAnswer/lessonPopupExam` | POST | 获取题目详情 |
| `/gateway/t/v1/popupAnswer/saveLessonPopupExamSaveAnswer` | POST | 保存弹窗答案 |
| `/gateway/t/v1/learning/saveDatabaseIntervalTimeV2` | POST | 上报视频进度 V2 |
| `/gateway/t/v1/learning/saveDatabaseIntervalTime` | POST | 上报视频进度 V1 |
| `/gateway/t/v1/learning/saveCacheIntervalTime` | POST | 缓存上报进度 |
| `/gateway/t/v1/course/threeDimensionalCourseWare` | GET | 课件访问 |

### 知到课程列表（onlineservice-api.zhihuishu.com）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/gateway/t/v1/student/course/share/queryShareCourseInfo` | POST | 获取课程列表 |
| `/gateway/t/v1/student/queryStudentAICourseList` | POST | 获取 AI 课程列表 |

### Hike（hikeservice.zhihuishu.com / studyresources.zhihuishu.com）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/student/course/aided/getMyCourseList` | GET | 获取课程列表 |
| `/studyResources/stuResouce/queryResourceMenuTree` | GET | 获取资源树 |
| `/studyResources/stuResouce/stuViewFile` | GET | 获取文件信息 |
| `/stuStudy/saveStuStudyRecord` | GET | 上报学习进度 |

### AI 课程（kg-ai-run.zhihuishu.com）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/run/gateway/t/stu/knowledge-study/course-basic` | POST | 获取知识点 |
| `/run/gateway/t/stu/studyRecord/completed` | POST | 标记资源完成 |
| `/run/gateway/t/stu/studyRecord/report` | POST | 上报视频进度 |
| `/run/gateway/t/stu/resources/list-knowledge-resource` | POST | 获取资源列表 |
| `/run/gateway/t/stu/exam/questions-paper` | POST | 获取考试信息 |
| `/run/gateway/t/stu/resources-lab/get-video-time` | POST | 获取视频时长 |

### AI 考试（studentexamtest.zhihuishu.com）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/gateway/t/v1/exam/user/openExam` | POST | 打开考试 |
| `/gateway/t/v1/exam/user/updateUserUsedTime` | POST | 更新考试用时 |
| `/gateway/t/v1/exam/user/getExamSheetInfo` | GET | 获取试卷内容 |
| `/gateway/t/v1/question/getExamQuestionInfo` | GET | 获取题目内容 |
| `/gateway/t/v1/answer/saveAnswer` | POST | 保存答案 |
| `/gateway/t/v1/exam/user/submit` | POST | 提交考试 |

### 登录（passport.zhihuishu.com）

| 端点 | 方法 | 用途 |
|------|------|------|
| `/login` | GET | 登录页面 |
| `/qrCodeLogin/getLoginQrImg` | GET | 获取二维码 |
| `/qrCodeLogin/getLoginQrInfo` | GET | 查询扫码状态 |

### 其他

| 端点 | 方法 | 用途 |
|------|------|------|
| `newbase.zhihuishu.com/video/initVideo` | GET | 初始化视频播放 |
| `ai-knowledge-map-platform.zhihuishu.com/knowledgemap/gateway/t/qa/platform/stream` | POST | 智慧树 AI 对话 |

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
| `TimeLimitExceeded` | 刷课时间超过设定限制 |
| `ValueError` | Cookies 无效、视频未找到、答案格式错误 |
| `Exception` | 登录失败、网络错误、API 返回错误 |

## 7. 技术栈

| 类别 | 选型 | 说明 |
|------|------|------|
| Python | >=3.13 | 支持 match 语句、类型参数语法等新特性 |
| HTTP 客户端 | httpx | 同步 API 为主，考试模块可选用异步；兼容 requests 风格，支持 HTTP/2 |
| 数据模型 | pydantic v2 | 替代 ObjDict，类型安全、自动验证、JSON 序列化开箱即用 |
| CLI | typer | 类型注解自动生成参数，代码简洁 |
| 日志 | loguru | 替代自定义 MonoLogger，API 简洁，开箱即用 |
| 加密 | pycryptodome | AES-128-CBC 加密，与原项目一致 |
| 配置 | TOML | Python 3.11+ 标准库 tomllib 支持，可写注释 |
| LLM | openai | OpenAI 兼容 API 调用 |
| PPT 解析 | openai + MoonShot | 文件提取 API |
| Token 计数 | tiktoken | Prompt 长度截断 |
| 图片处理 | Pillow | 二维码渲染 |
| 测试 | pytest | TDD 开发，fixture 机制强大 |
| Linter | ruff | 集成 flake8 + isort + pyupgrade，极快 |
| 类型检查 | mypy | 静态类型检查 |
| 格式化 | ruff format | 替代 black，统一工具链 |

### 执行模型
- **视频刷课**：同步执行（顺序流程，I/O 等待为主）
- **AI 考试**：异步执行（可并发答题、心跳更新等）

### 项目配置 (pyproject.toml)
```toml
[project]
name = "zhs"
authors = ["pjm314159"]
license = "GPLv3.0"
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
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.25",
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

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.13"
strict = true
```

## 8. 重写注意事项

1. **ObjDict → pydantic**：原项目自定义的 ObjDict 用 pydantic BaseModel 替代，API 响应用 pydantic 模型解析
2. **requests → httpx**：`requests.Session` → `httpx.Client`，API 几乎一致
3. **decrypt 模块**：仅用于逆向工程分析，不需要包含在重写中
4. **线程安全**：`watchVideo` 使用独立线程，`updateExamCostTime` 使用守护线程；异步考试模块用 asyncio 替代线程
5. **反检测**：随机暂停、随机延迟、模拟真人观看模式
6. **Cookie 管理**：httpx.Client 内置 cookie 持久化，支持从 dict/list 恢复
7. **重试机制**：httpx 内置 transport 支持重试，考试 API 重试 3 次
8. **TDD 开发**：先写测试再实现，核心模块（crypto、session、exam）需 80%+ 覆盖率
