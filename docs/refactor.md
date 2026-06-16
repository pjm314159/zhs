# CLI 重构开发计划

> branch: `refactor/cli`
> 参考: `.temp/refactor_cli.md`, `.temp/feat_homework.md`

---

## 1. 目标

1. **重构 CLI 接口**：从 `zhs -c ID` 风格改为命令式 `zhs play/homework/exam/fetch`
2. **抽象 AI 课程代码**：将 `AiCourseManager.run_course()` 中的视频播放和考试逻辑分离
3. **重命名 AI exam → homework**：AI 课程的"考试"实际上是作业，统一命名为 homework
4. **新增 `zhs init` 命令**：初始化 `.zhs/` 目录结构

---

## 2. 变更清单

### 2.1 AI 模块重构

#### 2.1.1 `ai/course.py` → `ai/video.py`（AI 视频播放器）

从 `AiCourseManager` 中提取视频播放相关方法到新的 `AiVideoPlayer` 类：

**提取的方法**：
- `play_video()` → `AiVideoPlayer.play_video()`
- `_watch_video()` → `AiVideoPlayer._watch_video()`
- `_report_video_progress()` → `AiVideoPlayer._report_video_progress()`

**保留在 `AiCourseManager`**：
- `get_ai_course_list()`
- `get_knowledge_points()`
- `list_knowledge_resources()`
- `complete_resource()`
- `query_ai_exam()` → 重命名为 `query_homework()`
- `_process_resource()` → 调用 `AiVideoPlayer` 而非自身 `play_video()`
- `_should_take_exam()` → 重命名为 `_should_do_homework()`
- `run_course()` → 调用 `AiVideoPlayer` + `HomeworkCtx`

**新的 `AiVideoPlayer` 签名**：
```python
class AiVideoPlayer:
    def __init__(self, session: ZhsSession, speed: float = 1.5) -> None: ...
    def play_video(self, course_id, class_id, file_id, knowledge_id, start_at=0) -> None: ...
```

#### 2.1.2 `ai/exam.py` → `ai/homework.py`（AI 作业上下文）

**重命名**：`ExamCtx` → `HomeworkCtx`

**内部重命名**：
- `exam_test_id` → 保持（API 字段名不变）
- `exam_paper_id` → 保持（API 字段名不变）
- `_open_exam()` → `_open_homework()`
- `_submit_exam()` → `_submit_homework()`
- `_exam_base_url` → `_homework_base_url`
- `_exam_stopped` → `_stopped`

**对外接口不变**：
- `start(reference_materials)` 返回 `(bool, int, int)` 不变
- 内部 API URL 和字段名不变（服务端 API 不变）

#### 2.1.3 `ai/course.py` 更新

`run_course()` 方法更新：
- 使用 `AiVideoPlayer` 替代自身的 `play_video()`
- 使用 `HomeworkCtx` 替代 `ExamCtx`
- `no_exam` 参数 → `no_homework`
- 日志中 "考试" → "作业"

### 2.2 Config 更新

#### `config.py`

**`UrlConfig` 新增字段**：
```python
homework: str = "https://studentexam-api.zhihuishu.com"  # 知到作业 API
ai_analysis: str = "https://ai-course-assistant-api.zhihuishu.com"  # AI 解析 API
```

**`AppConfig` 新增字段**：
```python
homework_threshold: int = 100  # 作业满分阈值百分比
max_submit: int = 3  # 最大提交次数
```

**`AppConfig` 字段重命名**：
- `threshold` → 保持（视频播放完成阈值，与 homework_threshold 不同）

### 2.3 Session 更新

#### `session.py`

**新增方法**：
```python
def homework_query(self, url: str, data: dict, ok_code: int = 200) -> dict:
    """知到作业 API 查询（AES-128-CBC + exam_key，无 dateFormate）"""
```

与 `zhidao_query` 的区别：
- 不发送 `dateFormate` 字段
- 使用 `exam_key` 加密
- `ok_code` 默认 200（非 0）

### 2.4 CLI 重构

#### 新命令结构

```
zhs [global-args] <command> [command-args]
```

**全局参数**：
- `--help`, `--debug`, `--console-log`, `--proxy`

**命令列表**：

| 命令 | 功能 | 关键参数 |
|------|------|----------|
| `zhs init` | 初始化 `.zhs/` 目录 | — |
| `zhs login` | 扫码登录 | `--show-in-terminal`, `--image-path` |
| `zhs play` | 刷视频 | `--type`, `--course`, `--limit`, `--speed` |
| `zhs homework` | 写作业 | `--type`, `--course`, `--no-ai`, `--homework-threshold`, `--max-submit` |
| `zhs exam` | AI 课程考试 | `--type`, `--course` |
| `zhs fetch` | 获取课程数据 | `--type` |

**`zhs play` 参数**：
- `--type`: `zhidao` / `hike` / `ai` / `auto`（默认 auto）
- `--course`: 课程 ID，不指定则刷所有
- `--limit`: 每门课程时间限制（分钟）
- `--speed`: 播放速度

**`zhs homework` 参数**：
- `--type`: `zhidao` / `ai` / `auto`（默认 auto）
- `--course`: 课程 ID，不指定则写所有
- `--no-ai`: 不使用 AI 模型（随机生成）
- `--homework-threshold`: 满分阈值百分比（0-100）
- `--max-submit`: 最大提交次数

**`zhs exam` 参数**：
- `--type`: `ai` / `auto`
- `--course`: 课程 ID

**`zhs fetch` 参数**：
- `--type`: `all` / `course` / `homework`

#### 删除的旧参数

- `-c` / `--course` → 各命令的 `--course`
- `-f` / `--fetch` → `zhs fetch` 命令
- `--ai-course` / `--ai-class` → `--course courseId:classId --type ai`
- `--noexam` → `zhs play --type ai` 不含 homework
- `--no-ai-exam` → `zhs homework --no-ai`
- `-v` / `--videos` → 暂不保留（低频使用）

### 2.5 `zhs init` 命令

创建 `.zhs/` 目录结构：
```
.zhs/
├── config.toml      # 用户配置
├── cache/           # 本地缓存
└── logs/            # 日志目录
```

如果 `config.toml` 不存在，创建默认配置并保存。

---

## 3. 开发顺序

### Phase 1：AI 模块重构（无 CLI 变更）

| Task | 内容 | 依赖 |
|------|------|------|
| 1.1 | 创建 `ai/video.py`（AiVideoPlayer），从 `ai/course.py` 提取视频播放 | — |
| 1.2 | 重命名 `ai/exam.py` → `ai/homework.py`，`ExamCtx` → `HomeworkCtx` | — |
| 1.3 | 更新 `ai/course.py`：使用 AiVideoPlayer + HomeworkCtx | 1.1, 1.2 |
| 1.4 | 更新 `config.py`：新增 UrlConfig.homework/ai_analysis, AppConfig.homework_threshold/max_submit | — |
| 1.5 | 更新 `session.py`：新增 `homework_query` 方法 | 1.4 |
| 1.6 | 更新所有测试文件 | 1.1-1.5 |
| 1.7 | 全量检查：pytest + ruff + mypy | 1.6 |

### Phase 2：CLI 重构

| Task | 内容 | 依赖 |
|------|------|------|
| 2.1 | 重写 `__main__.py`：新命令结构 | Phase 1 |
| 2.2 | 新增 `zhs init` 命令 | 2.1 |
| 2.3 | 新增 `zhs play` 命令 | 2.1 |
| 2.4 | 新增 `zhs homework` 命令（占位，暂不实现知到作业逻辑） | 2.1 |
| 2.5 | 新增 `zhs exam` 命令 | 2.1 |
| 2.6 | 新增 `zhs fetch` 命令 | 2.1 |
| 2.7 | 更新所有测试文件 | 2.1-2.6 |
| 2.8 | 全量检查：pytest + ruff + mypy | 2.7 |

---

## 4. 文件变更清单

### 新增文件
- `src/zhs/ai/video.py` — AiVideoPlayer 类
- `src/zhs/ai/homework.py` — HomeworkCtx 类（从 exam.py 重命名）

### 删除文件
- `src/zhs/ai/exam.py` — 重命名为 homework.py

### 修改文件
- `src/zhs/ai/course.py` — 使用 AiVideoPlayer + HomeworkCtx
- `src/zhs/ai/__init__.py` — 更新导出
- `src/zhs/config.py` — 新增字段
- `src/zhs/session.py` — 新增 homework_query
- `src/zhs/__main__.py` — 完全重写
- `tests/` 下对应测试文件

### 不变文件
- `src/zhs/ai/models.py` — 数据模型不变
- `src/zhs/ai/ppt.py` — PPT 转换不变
- `src/zhs/zhidao/*` — 知到模块不变
- `src/zhs/hike/*` — Hike 模块不变
- `src/zhs/llm/*` — LLM 模块不变
- `src/zhs/utils/*` — 工具模块不变
- `src/zhs/crypto.py` — 加密模块不变
- `src/zhs/exceptions.py` — 异常不变
- `src/zhs/login.py` — 登录不变
- `src/zhs/logger.py` — 日志不变

---

## 5. 向后兼容

- 旧版 `zhs -c ID` 命令不再支持，需使用 `zhs play -c ID`
- 旧版 `zhs -f` 改为 `zhs fetch`
- 旧版 `zhs --ai-course ID --ai-class ID` 改为 `zhs play -c courseId:classId --type ai`
- 旧版 `zhs login` 保持不变
- `config.toml` 格式保持兼容，新增字段有默认值
