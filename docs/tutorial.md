# ZHS 使用教程

> 本文档介绍 ZHS（智慧树自动刷课工具）的安装、配置、登录和各命令的使用方式。
> ZHS 使用命令式 CLI 接口，支持知到 / Hike / AI 三类课程的视频刷课、作业、考试。

---

## 1. 安装

### 1.1 前置要求

- Python ≥ 3.13
- [uv](https://docs.astral.sh/uv/) 包管理器（推荐）或 pip

### 1.2 安装步骤

```bash
# 克隆仓库
git clone <repo-url>
cd ZHS

# 使用 uv 安装依赖（含开发依赖）
uv sync --dev

# 或使用 pip 安装为可编辑包
pip install -e ".[dev]"
```

安装完成后，`zhs` 命令即可用：

```bash
zhs --help
```

---

## 2. 初始化与配置

### 2.1 初始化数据目录

首次使用必须运行 `zhs init` 创建数据目录和默认配置：

```bash
zhs init
```

输出示例：

```
配置文件已创建: ~/.zhs/config.toml
数据目录: ~/.zhs
```

数据目录结构：

```
~/.zhs/
├── config.toml       # 配置文件
├── cookies.json      # 登录 Cookie（登录后生成）
├── execution.json    # 课程列表（zhs fetch 生成）
├── cache/            # 缓存目录（PPT、作业答案等）
└── logs/             # 日志目录（按日期轮转）
```

### 2.2 配置文件说明

配置文件位于 `~/.zhs/config.toml`，使用 TOML 格式，按功能分组：

```toml
# ===== 顶层基础设置 =====
save_cookies = true              # 保存 Cookie，避免重复登录
limit = 0                        # 刷课时间限制（分钟），0 = 不限制
threshold = 0.91                 # 视频完成阈值（0.0-1.0）

# ===== 视频播放速度 =====
[video]
zhidao_speed = 1.5               # 知到视频速度（最高 2.0）
hike_speed = 1.25                # Hike 视频速度（最高 2.0）
ai_speed = 1.5                   # AI 课程视频速度（最高 2.0）

# ===== 作业配置 =====
[homework]
threshold = 100                  # 作业达标阈值（0-100，默认 100）
max_submit = 0                   # 最大重做次数（0 = 无限次）
homework_delay_min = 1.0         # 每题保存后最小休息时间（秒）
homework_delay_max = 2.0         # 每题保存后最大休息时间（秒）
homework_page_size = 100         # 扫描作业列表分页大小
ai_homework_threshold = 90       # AI 课程作业跳过阈值（masteryScore > 此值则跳过）

# ===== 显示设置 =====
[display]
log_level = "INFO"               # 日志级别: DEBUG/INFO/WARNING/ERROR

# ===== 代理设置 =====
[proxies]
http = ""                        # HTTP 代理地址
https = ""                       # HTTPS 代理地址

# ===== 二维码设置 =====
[qr]
image_path = ""                  # 二维码图片保存路径（留空则使用临时目录）

# ===== AI 配置 =====
[ai]
enabled = true                   # 是否启用 AI 功能
use_zhidao_ai = true             # 是否使用智慧树内置 AI（无需 API Key）
api_key = ""                     # OpenAI 兼容 API Key（自定义 AI 时需要）
base_url = "https://api.openai.com/v1"  # API 地址
model = "gpt-4o-mini"            # 模型名称
max_token = 27900                # 最大 Token 数

# ===== AI 考试配置 =====
[exam]
save_nums = 5                    # 每批保存答案的题目数量
delay_min = 3.0                  # 每批保存后最小休息时间（秒）
delay_max = 5.0                  # 每批保存后最大休息时间（秒）

# ===== 加密密钥（一般无需修改） =====
[crypto]
iv = "1g3qqdh4jvbskb9x"
home_key = "7q9oko0vqb3la20r"
video_key = "azp53h0kft7qi78q"
qa_key = "kcGOlISPkYKRksSK"
ai_key = "hw2fdlwcj4cs1mx7"
exam_key = "onbfhdyvz8x7otrp"
hike_salt = "o6xpt3b#Qy$Z"
ev_key = "zzpttjd"
ai_sign_prefix = "8ZflKEagfL"

# ===== API URL（一般无需修改） =====
[urls]
base = "https://onlineservice-api.zhihuishu.com"
passport = "https://passport.zhihuishu.com"
study = "https://studyservice-api.zhihuishu.com"
hike = "https://hike.zhihuishu.com"
ai = "https://kg-ai-run.zhihuishu.com"
ai_task = "https://kg-run-student.zhihuishu.com"
exam = "https://studentexamtest.zhihuishu.com"
homework = "https://studentexam-api.zhihuishu.com"
ai_analysis = "https://ai-course-assistant-api.zhihuishu.com"
newbase = "https://newbase.zhihuishu.com"
```

### 2.3 AI 配置说明

ZHS 支持两种 AI 答题模式：

| 模式 | 配置 | 适用场景 |
|------|------|----------|
| **智慧树内置 AI**（默认） | `use_zhidao_ai = true` | 无需 API Key，使用智慧树官方 AI 接口 |
| **自定义 LLM** | `use_zhidao_ai = false` + `api_key` | OpenAI / DeepSeek / MoonShot 等兼容接口 |

> 默认使用智慧树内置 AI，无需配置任何 API Key 即可使用 AI 答题功能。这个只适用于你有ai智慧课程才可用，且由于这个built-in AI比较烂，指令遵从性较差  
> 如需使用自定义 LLM，将 `use_zhidao_ai` 设为 `false` 并填写 `api_key` 和 `base_url`。

---

## 3. 登录

ZHS 仅支持**扫码登录**，使用 `zhs login` 命令：

```bash
zhs login
```

程序会：

1. 生成二维码图片并保存到 `~/.zhs/qrcode.png`（或配置文件指定的路径）
2. 等待手机智慧树 APP 扫码确认
3. 登录成功后自动保存 Cookie

### 3.1 终端显示二维码

如果无法打开图片查看器，可在终端直接显示：

```bash
zhs login --show-in-terminal
```

### 3.2 指定二维码保存路径

```bash
zhs login --image-path /path/to/qrcode.png
```

### 3.3 通过代理登录

```bash
zhs login --proxy http://127.0.0.1:7890
```

登录成功后，Cookie 会自动保存到 `~/.zhs/cookies.json`，后续命令无需重复登录。

---

## 4. 命令总览

ZHS 使用命令式 CLI 接口，所有命令通过 `zhs <command>` 调用：

| 命令 | 用途 | 示例 |
|------|------|------|
| `zhs init` | 初始化数据目录与配置 | `zhs init` |
| `zhs login` | 扫码登录 | `zhs login` |
| `zhs play` | 刷视频（知到/Hike/AI） | `zhs play -c ABC123` |
| `zhs homework` | 写作业（知到/AI） | `zhs homework -c ABC123` |
| `zhs exam` | AI 课程考试 | `zhs exam --ai-course 1001 --ai-class 2001` |
| `zhs fetch` | 获取课程列表 | `zhs fetch` |

查看帮助：

```bash
zhs --help              # 查看所有命令
zhs play --help         # 查看某个命令的参数
```

---

## 5. 刷视频：`zhs play`

### 5.1 全刷模式（默认）

不指定课程 ID 时，自动刷所有课程（先知到 → Hike → AI）：

```bash
zhs play
```

### 5.2 刷指定知到课程

知到课程 ID 通常包含字母（如 `ABC123`）：

```bash
zhs play -c ABC123
```

### 5.3 刷指定 Hike 课程

Hike 课程 ID 通常为纯数字（如 `12345`）：

```bash
zhs play -c 12345
```

### 5.4 刷 AI 课程

AI 课程需要提供 `courseId` 和 `classId`：

```bash
zhs play --ai-course 1001 --ai-class 2001
```

也可使用 `courseId:classId` 字符串格式（与其他课程统一）：

```bash
zhs play -c 1001:2001 --type ai
```

### 5.5 强制指定课程类型

当自动检测不准确时，可手动指定 `--type`：

```bash
# 强制按知到课程处理
zhs play -c 12345 --type zhidao

# 强制按 Hike 课程处理
zhs play -c ABC123 --type hike

# 强制按 AI 课程处理
zhs play -c 1001:2001 --type ai

# 仅刷某一类课程（全刷模式下过滤）
zhs play --type zhidao
```

课程类型自动检测规则：

- 显式 `--type` 优先级最高
- ID 含字母 → 知到（zhidao）
- ID 纯数字 → Hike（hike）
- AI 课程需通过 `--ai-course`/`--ai-class` 或 `courseId:classId` 格式指定

### 5.6 覆盖配置参数

```bash
# 指定播放速度（覆盖 config.toml 中的 video.*_speed）
zhs play -c ABC123 -s 1.5

# 限制每门课程刷课时间（分钟）
zhs play -c ABC123 -l 30
```

---

## 6. 写作业：`zhs homework`

### 6.1 全刷作业模式

扫描所有知到课程和 AI 课程的作业：

```bash
zhs homework
```

### 6.2 按课程 ID 写作业

```bash
# 知到课程作业
zhs homework -c ABC123

# AI 课程作业
zhs homework --ai-course 1001 --ai-class 2001
```

### 6.3 通过 URL 写指定作业

从浏览器复制作业 URL（`onlineexamh5new.zhihuishu.com/stuExamWeb.html#/webExamList/dohomework/...`）：

```bash
zhs homework --url "https://onlineexamh5new.zhihuishu.com/stuExamWeb.html#/webExamList/dohomework/{recruitId}/{stuExamId}/{examId}/{courseId}/{schoolId}/0"
```

URL 中参数顺序为：`recruitId / stuExamId / examId / courseId / schoolId`。

### 6.4 作业参数

```bash
# 不使用 AI 模型（随机生成答案）
zhs homework -c ABC123 --no-ai

# 指定达标阈值百分比（0-100，默认 100）
zhs homework -c ABC123 --homework-threshold 80

# 指定最大重做次数（0 = 无限次）
zhs homework -c ABC123 --max-submit 3
```

---

## 7. AI 课程考试：`zhs exam`

> 目前仅支持 AI 课程的考试功能。

### 7.1 基本用法

```bash
# 指定 AI 课程考试（答题但不提交）
zhs exam --ai-course 1001 --ai-class 2001

# 答题并提交考试
zhs exam --ai-course 1001 --ai-class 2001 --submit
```

### 7.2 全部 AI 课程考试

```bash
zhs exam --type ai
```

### 7.3 提交说明

- **不提交**（默认）：仅答题并保存到缓存，可重复运行。
- **提交**（`--submit`）：答题后提交考试，提交后无法修改。提交成功后会尝试保存答案到缓存供后续参考。

---

## 8. 获取课程列表：`zhs fetch`

```bash
# 获取所有课程列表（知到 + Hike + AI）
zhs fetch

# 仅获取课程列表（不扫描作业）
zhs fetch --type course
```

课程列表会保存到 `~/.zhs/execution.json`，包含课程名称和 ID：

```json
{
  "zhidao": [{"name": "课程名", "id": "ABC123"}],
  "hike": [{"name": "课程名", "id": "12345"}],
  "ai": [{"name": "课程名", "courseId": "1001", "classId": "2001"}]
}
```

---

## 9. 通用参数

以下参数适用于 `play` / `homework` / `exam` / `fetch` 命令：

| 参数 | 说明 |
|------|------|
| `--proxy <url>` | 代理地址（如 `http://127.0.0.1:7890`、`socks5://127.0.0.1:1080`） |
| `-d, --debug` | 调试模式（输出 DEBUG 级别日志） |
| `--console-log` | 日志输出到控制台（默认仅写入文件） |

`play` / `homework` / `exam` 共有参数：

| 参数 | 说明 |
|------|------|
| `-c, --course <id>` | 课程 ID（可多次指定） |
| `--type <type>` | 课程类型：`zhidao` / `hike` / `ai` / `auto` |
| `--ai-course <id>` | AI 课程 courseId |
| `--ai-class <id>` | AI 课程 classId |

---

## 10. 使用示例

```bash
# 首次使用：初始化 + 登录
zhs init
zhs login

# 获取课程列表，查看有哪些课程
zhs fetch

# 刷单个知到课程，1.5 倍速
zhs play -c ABC123 -s 1.5

# 刷单个 Hike 课程，限制 30 分钟
zhs play -c 12345 -l 30

# 刷 AI 课程（视频 + 作业）
zhs play --ai-course 1001 --ai-class 2001

# 全刷所有课程
zhs play

# 仅刷知到课程
zhs play --type zhidao

# 写知到课程作业
zhs homework -c ABC123

# 通过 URL 写指定作业
zhs homework --url "https://onlineexamh5new.zhihuishu.com/..."

# AI 课程考试并提交
zhs exam --ai-course 1001 --ai-class 2001 --submit

# 使用代理 + 调试模式
zhs play -c ABC123 --proxy http://127.0.0.1:7890 -d --console-log
```

---

## 11. 代理支持

支持以下代理协议：

```bash
# HTTP/HTTPS 代理
zhs play --proxy http://127.0.0.1:7890

# SOCKS5 代理
zhs play --proxy socks5://127.0.0.1:1080

# 全协议代理
zhs play --proxy all://127.0.0.1:7890
```

也可在 `config.toml` 中配置：

```toml
[proxies]
http = "http://127.0.0.1:7890"
https = "http://127.0.0.1:7890"
```

命令行 `--proxy` 参数优先级高于配置文件。

---

## 12. 数据目录

程序数据默认保存在 `~/.zhs/` 目录：

| 文件/目录 | 说明 |
|----------|------|
| `config.toml` | 配置文件（`zhs init` 生成） |
| `cookies.json` | 登录 Cookie（`zhs login` 生成） |
| `execution.json` | 课程列表（`zhs fetch` 生成） |
| `cache/` | 缓存目录（PPT 转文本、作业答案等） |
| `logs/` | 日志目录（按日期轮转，保留 30 天，gz 压缩） |
| `qrcode.png` | 登录二维码图片（`zhs login` 生成） |

---

## 13. 常见问题

### Q1: 登录二维码扫不了？

- 尝试 `zhs login --show-in-terminal` 在终端直接显示二维码
- 或指定 `--image-path` 保存到自定义路径后手动打开
- 检查网络连接，必要时使用代理：`zhs login --proxy http://...`

### Q2: 课程类型检测错误？

使用 `--type` 参数手动指定：

```bash
zhs play -c 12345 --type zhidao    # 强制按知到处理
zhs play -c ABC123 --type hike     # 强制按 Hike 处理
zhs play -c 1001:2001 --type ai    # 强制按 AI 处理
```

### Q3: AI 答题报错？

- 默认使用智慧树内置 AI，无需额外配置
- 如需自定义 LLM，在 `config.toml` 中设置 `ai.use_zhidao_ai = false` 并填写 `api_key` 和 `base_url`
- 完全禁用 AI（随机答题）：`zhs homework -c ABC123 --no-ai`

### Q4: 视频播放卡住？

- 检查网络连接
- 尝试使用代理：`zhs play --proxy ...`
- 开启调试模式查看详细日志：`zhs play -c ABC123 -d --console-log`
- 查看日志文件：`~/.zhs/logs/zhs_YYYY-MM-DD.log`

### Q5: Cookie 过期？

重新登录：

```bash
# 重新登录
zhs login
```

### Q6: 如何只刷视频不答题？

- 知到课程：`zhs play` 只刷视频，作业使用 `zhs homework` 单独执行
- AI 课程：`zhs play --ai-course X --ai-class Y` 会同时刷视频和作业，目前无法分离

### Q7: 作业如何达标？

- 默认达标阈值 100%（`homework.threshold = 100`）
- 未达标会自动重做，直到达标或达到 `max_submit` 次数
- 可通过 `--homework-threshold` 调整阈值，或 `--max-submit` 限制重做次数

### Q8: 考试如何提交？

- 默认不提交：`zhs exam --ai-course X --ai-class Y`（仅答题，可重复运行）
- 提交考试：`zhs exam --ai-course X --ai-class Y --submit`（提交后无法修改）

### Q9: 日志在哪里？

- 日志文件：`~/.zhs/logs/zhs_YYYY-MM-DD.log`（按日期轮转，保留 30 天，gz 压缩）
- 控制台输出：默认不输出，使用 `--console-log` 或 `-d` 开启

### Q10: 如何查看课程 ID？

```bash
# 获取所有课程列表
zhs fetch

# 查看 execution.json
cat ~/.zhs/execution.json
```

知到课程 ID 含字母（如 `ABC123`），Hike 课程 ID 为纯数字（如 `12345`），AI 课程需要 `courseId` 和 `classId` 两个参数。
