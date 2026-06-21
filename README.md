# ZHS — 智慧树自动刷课工具

[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://docs.astral.sh/ruff/)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

ZHS 是一个针对智慧树平台的自动学习工具，支持知到共享课、Hike 职教云课、AI 智慧课程三类课程的自动学习。核心能力包括：扫码登录、视频进度模拟、弹窗答题、AI 自动作业与考试。

## 功能特性

- **三类课程全覆盖**：知到（Zhidao）/ Hike 职教云 / AI 智慧课程
- **命令式 CLI**：`zhs init / login / play / homework / exam / fetch` 子命令清晰分离
- **扫码登录**：自动保存 Cookie，避免重复登录
- **视频自动刷课**：模拟真人观看（随机暂停、随机延迟、进度条显示）
- **弹窗答题**：视频内弹窗题目自动选择正确答案
- **作业自动作答**：知到作业 + AI 课程作业，支持 LLM 答题与答案缓存
- **AI 考试**：AI 课程考试自动答题，批量保存答案，心跳保活
- **AI 解析**：调用智慧树 AI 解析接口获取题目解析（SSE 流式）
- **多 LLM 后端**：默认使用智慧树内置 AI，也可配置 OpenAI 兼容接口（DeepSeek、MoonShot 等）
- **PPT 转文本**：使用 python-pptx 本地提取 PPT 文本作为答题参考
- **代理支持**：HTTP / HTTPS / SOCKS5

## 技术栈

| 类别 | 选型                         |
|------|----------------------------|
| 语言 | Python 3.13+               |
| HTTP 客户端 | httpx（同步）（api限制）           |
| 数据模型 | pydantic v2                |
| CLI 框架 | typer                      |
| 日志 | loguru                     |
| 加密 | pycryptodome（AES-128-CBC）  |
| 配置 | TOML（tomllib + tomli-w）    |
| LLM | openai（兼容接口）               |
| Token 计数 | tiktoken                   |
| 二维码 | qrcode + Pillow            |
| PPT 解析 | python-pptx                |
| 测试 | pytest + respx + freezegun |
| Lint / Format | ruff                       |
| 类型检查 | mypy strict                |

## 安装

### 前置要求

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) 包管理器（推荐）
  - 注意使用`uv`要使用`uv run zhs`command 或者直接进入环境使用

### 步骤

```bash
# 克隆仓库
git clone <repo-url>
cd ZHS

# 安装依赖（含开发依赖）
uv sync --dev

# 或使用 pip
# pip install -e ".[dev]"
```

安装后 `zhs` 命令即可使用：

```bash
zhs --help
```

## 快速开始

### 1. 初始化配置

```bash
zhs init
```

在 `~/.zhs/` 下创建目录结构与默认 `config.toml` 配置文件。

### 2. 扫码登录

```bash
zhs login
```

程序会生成二维码图片并保存到 `~/.zhs/qrcode.png`，使用智慧树 APP 扫码即可登录。Cookie 会自动保存，下次运行无需重复登录。

如需在终端直接显示二维码：

```bash
zhs login --show-in-terminal
```

### 3. 获取课程列表

```bash
zhs fetch
```

打印所有课程列表并保存到 `~/.zhs/execution.json`。

### 4. 刷视频

```bash
# 刷单个知到课程
zhs play -c ABC123

# 刷单个 Hike 课程
zhs play -c 12345

# 刷 AI 课程（courseId:classId 格式）
zhs play -c 1001:2001 --type ai

# 或使用 --ai-course / --ai-class 显式指定
zhs play --ai-course 1001 --ai-class 2001

# 全刷所有课程
zhs play

# 指定速度与时间限制
zhs play -c ABC123 -s 1.5 -l 30
```

### 5. 写章节测试

```bash
# 知到课程作业（按课程 ID）
zhs homework -c ABC123

# AI 课程作业
zhs homework --ai-course 1001 --ai-class 2001

# 通过浏览器复制的作业 URL 直接做题
zhs homework --url "https://onlineexamh5new.zhihuishu.com/stuExamWeb.html#/webExamList/dohomework/..."

# 全刷作业
zhs homework
```

### 6. AI 课程考试

```bash
# 答题但不提交（默认）
zhs exam --ai-course 1001 --ai-class 2001

# 答题并提交
zhs exam --ai-course 1001 --ai-class 2001 --submit

# 自动遍历所有 AI 课程的未完成考试
zhs exam --type ai
```

## CLI 命令一览

| 命令 | 说明 |
|------|------|
| `zhs init` | 初始化 `~/.zhs/` 目录与默认配置 |
| `zhs login` | 扫码登录并保存 Cookie |
| `zhs play` | 刷视频（支持知到 / Hike / AI） |
| `zhs homework` | 写作业（知到作业 + AI 课程作业） |
| `zhs exam` | AI 课程考试 |
| `zhs fetch` | 获取并保存课程列表 |

每个命令均支持 `--proxy`、`-d/--debug`、`--console-log` 全局参数。详细参数说明见 [docs/tutorial.md](docs/tutorial.md)。

## 配置

配置文件位于 `~/.zhs/config.toml`，可参考项目根目录的 [config.toml.example](config.toml.example)。

### 主要配置项

```toml
# 基础设置
save_cookies = true
limit = 0                # 刷课时间限制（分钟，0 = 不限制）
threshold = 0.91         # 视频结束阈值（0.0-1.0）

[video]
zhidao_speed = 1.5       # 知到视频速度（最高 2.0）
hike_speed = 1.25        # Hike 视频速度
ai_speed = 1.5           # AI 课程视频速度

[homework]
threshold = 100          # 作业达标阈值（0-100）
max_submit = 0           # 最大重做次数（0 = 无限）
delay_min = 1.0          # 每题保存后最小延迟（秒）
delay_max = 2.0          # 每题保存后最大延迟（秒）
ai_homework_threshold = 90  # AI 作业跳过阈值

[exam]
save_nums = 5            # 每批保存答案的题目数
delay_min = 3.0          # 每批保存后最小延迟（秒）
delay_max = 5.0          # 每批保存后最大延迟（秒）

[display]
log_level = "INFO"       # DEBUG / INFO / WARNING / ERROR

[proxies]
http = ""                # HTTP 代理
https = ""               # HTTPS 代理

[qr]
image_path = ""          # 二维码保存路径（留空使用默认目录）

[ai]
enabled = true
use_zhidao_ai = true     # 默认使用智慧树内置 AI
api_key = ""             # OpenAI 兼容 API Key
base_url = "https://api.openai.com/v1"
model = "gpt-4o-mini"
max_token = 27900

[crypto]                 # 加密密钥（一般无需修改）
[urls]                   # API URL（一般无需修改）
```

> **AI 答题**：默认使用智慧树内置 AI，无需任何 API Key。前提是有ai智慧课程，内置的AI性能低下，建议是使用自定义的。如需使用自定义 LLM，将 `use_zhidao_ai = false` 并填写 `api_key` 与 `base_url`。

## 数据目录

程序数据默认保存在 `~/.zhs/`：

| 路径 | 说明 |
|------|------|
| `config.toml` | 配置文件 |
| `cookies.json` | 登录 Cookie |
| `execution.json` | `zhs fetch` 生成的课程列表 |
| `qrcode.png` | 登录二维码图片 |
| `logs/` | 日志目录（按天轮转，保留 30 天） |
| `cache/` | 缓存目录（AI 作业答案缓存等） |

## 开发

### 开发流程

本项目采用 TDD（测试驱动开发）流程，每个模块严格遵循 Red → Green → Refactor 循环。详见 [docs/test.md](docs/test.md) 。

### 质量检查

```bash
# 运行全部测试
uv run pytest

# Lint 检查
uv run ruff check src/ tests/

# 格式化检查
uv run ruff format --check src/ tests/

# 类型检查
uv run mypy src/ tests/
```

### 文档

| 文档 | 用途 |
|------|------|
| [docs/spec.md](docs/spec.md) | 功能规格、API 端点、数据结构 |
| [docs/design.md](docs/design.md) | 模块级设计、类签名、流程图 |
| [docs/tutorial.md](docs/tutorial.md) | 使用教程 |
| [docs/test.md](docs/test.md) | 测试策略与用例 |
| [docs/linter.md](docs/linter.md) | 代码规范 |

## About
本项目是使用python开发，我尽量完善代码的注释和写好文档，
便于社区的开发。

## 许可证

GPL-3.0-only
