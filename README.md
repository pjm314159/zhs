# ZHS — Zhihuishu Auto-Learning Tool

[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://docs.astral.sh/ruff/)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

**[中文文档](README_zh.md)**

ZHS is an auto-learning tool for the Zhihuishu platform, supporting three types of courses: Zhidao shared courses, Hike vocational education courses, and AI smart courses. Core capabilities include: QR code login, video progress simulation, popup quiz answering, AI auto homework and exams.

## Features

- **Three Course Types Supported**: Zhidao / Hike / AI Smart Courses
- **Command-line Interface**: Clear subcommand separation with `zhs init / login / play / homework / exam / fetch / cache`
- **QR Code Login**: Auto-saves cookies to avoid repeated logins
- **Auto Video Watching**: Simulates human viewing behavior (random pauses, random delays, progress bar display)
- **Popup Quiz Answering**: Automatically selects correct answers for popup questions during video playback
- **Auto Homework**: Zhidao homework + AI course homework, supports LLM answering and answer caching
- **AI Exams**: Auto-answer AI course exams, batch save answers, heartbeat keep-alive
- **AI Analysis**: Calls Zhihuishu AI analysis API to get question explanations (SSE streaming)
- **Multiple LLM Backends**: Default uses Zhihuishu built-in AI, also supports OpenAI-compatible interfaces (DeepSeek, MoonShot, etc.). **Custom AI is recommended as the default AI has low performance**
- **PPT to Text**: Uses python-pptx to extract PPT text locally as answer reference
- **Proxy Support**: HTTP / HTTPS / SOCKS5

## Tech Stack

| Category | Technology |
|----------|------------|
| Language | Python 3.13+ |
| HTTP Client | httpx (synchronous) (API limitation) |
| Data Models | pydantic v2 |
| CLI Framework | typer |
| Logging | loguru |
| Encryption | pycryptodome (AES-128-CBC) |
| Configuration | TOML (tomllib + tomli-w) |
| LLM | openai (compatible interface) |
| Token Counting | tiktoken |
| QR Code | qrcode + Pillow |
| PPT Parsing | python-pptx |
| HTML Text Extraction | beautifulsoup4 |
| Testing | pytest + respx + freezegun |
| Lint / Format | ruff |
| Type Checking | mypy strict |

## Installation

### Prerequisites

- Python 3.13+
- **Quickest start**: install with `pip install zhs` — most recommended for **users**
- Or use the [uv](https://docs.astral.sh/uv/) package manager (recommended for development)
  - Note: When using `uv`, run with `uv run zhs` command or enter the environment directly
- Or use the pre-built .whl file: `pip install [version].whl` [**Release**](https://github.com/pjm314159/zhs/releases)

### Steps

```bash
# Clone the repository
git clone <repo-url>
cd ZHS

# Install dependencies (including dev dependencies)
uv sync --dev

# Or use pip
# pip install -e ".[dev]"
```

After installation, the `zhs` command is ready to use:

```bash
zhs --help
```

## Quick Start

### 1. Initialize Configuration

```bash
zhs init
```

Creates directory structure and default `config.toml` configuration file under `~/.zhs/`.

### 2. QR Code Login

```bash
zhs login
```

The program generates a QR code image and saves it to `~/.zhs/qrcode.png`. Scan with the Zhihuishu app to login. Cookies are automatically saved for subsequent runs.

To display the QR code directly in terminal:

```bash
zhs login --show-in-terminal
```

### 3. Fetch Course List

```bash
zhs fetch
```

Prints all courses and saves to `~/.zhs/execution.json` (outputs `courseId` which can be used as the `-c` parameter).

### 4. Watch Videos

```bash
# Watch a single Zhidao course (courseId)
zhs play -c 1000008156 --type zhidao

# Watch a single Hike course
zhs play -c 12345

# Watch an AI course (courseId:classId format)
zhs play -c 1001:2001 --type ai

# Or specify explicitly with --ai-course / --ai-class
zhs play --ai-course 1001 --ai-class 2001

# Auto-parse from URL (Zhidao video page / AI learning page / AI course page)
zhs play --url "https://studyvideoh5.zhihuishu.com/stuStudy?recruitAndCourseId=xxx"
zhs play --url "https://ai-smart-course-student-pro.zhihuishu.com/learnPage/courseId/nodeUid/classId"
zhs play --url "https://ai-smart-course-student-pro.zhihuishu.com/singleCourse/knowledgeStudy/courseId/classId"

# Watch all courses
zhs play

# Specify speed and time limit
zhs play -c 1000008156 --type zhidao -s 1.5 -l 30
```

> **`--url` and `-c` are mutually exclusive**. `--url` automatically parses course parameters from browser URLs:
> - Zhidao video page (`recruitAndCourseId=`) → Watch that single course only
> - AI learning page (`learnPage/{courseId}/{nodeUid}/{classId}`) → Direct mode, watch only that knowledge point
> - AI course page (`knowledgeStudy/{courseId}/{classId}`) → Scan mode, watch all

### 5. Complete Chapter Tests

```bash
# Zhidao course homework (by courseId)
zhs homework -c 1000008156 --type zhidao

# AI course homework
zhs homework --ai-course 1001 --ai-class 2001

# Directly answer from browser URL (Zhidao homework / AI learning page / AI course page)
zhs homework --url "https://onlineexamh5new.zhihuishu.com/stuExamWeb.html#/webExamList/dohomework/..."
zhs homework --url "https://ai-smart-course-student-pro.zhihuishu.com/learnPage/courseId/nodeUid/classId"
zhs homework --url "https://ai-smart-course-student-pro.zhihuishu.com/singleCourse/knowledgeStudy/courseId/classId"

# Complete all homework
zhs homework
```

> AI course `learnPage` URLs containing `nodeUid` (knowledge point ID) use **direct mode** (only that knowledge point); `knowledgeStudy` URLs use **scan mode** (all).

### 6. AI Course Exams

```bash
# Answer but don't submit (default)
zhs exam --ai-course 1001 --ai-class 2001

# Answer and submit
zhs exam --ai-course 1001 --ai-class 2001 --submit

# Directly take a specific exam via testDetail URL
zhs exam --url "https://ai-smart-course-student-pro.zhihuishu.com/testDetail/courseId/classId/examTestId/examPaperId/..."

# Auto-traverse all unfinished exams in AI courses
zhs exam --type ai
```

## CLI Commands Overview

| Command | Description |
|---------|-------------|
| `zhs init` | Initialize `~/.zhs/` directory and default configuration |
| `zhs login` | QR code login and save cookies |
| `zhs play` | Watch videos (supports Zhidao / Hike / AI, supports `--url`) |
| `zhs homework` | Complete homework (Zhidao + AI course homework, supports `--url`) |
| `zhs exam` | AI course exams (supports `--url` for specific exams) |
| `zhs fetch` | Fetch and save course list (outputs `courseId`) |
| `zhs cache` | Question bank cache management (`export` to JSON / `import` from JSON) |

All commands support global parameters `--proxy`, `-d/--debug`, `--console-log`. `play`/`homework`/`exam` support `--url` (mutually exclusive with `-c`, auto-parses course parameters from browser URLs). See [docs/tutorial.md](docs/tutorial.md) for detailed parameter descriptions.

## Configuration

Configuration file is located at `~/.zhs/config.toml`. For more configuration options, refer to [config.toml.example](config.toml.example) in the project root.

### Main Configuration Options

```toml
# Basic Settings
save_cookies = true
limit = 0                # Time limit in minutes (0 = no limit)
threshold = 0.91         # Video end threshold (0.0-1.0)

[video]
zhidao_speed = 1.5       # Zhidao video speed (max 2.0)
hike_speed = 1.25        # Hike video speed
ai_speed = 1.5           # AI course video speed

[homework]
threshold = 100          # Homework pass threshold (0-100)
max_submit = 0           # Maximum retry count (0 = unlimited)
delay_min = 1.0          # Minimum delay after saving each question (seconds)
delay_max = 2.0          # Maximum delay after saving each question (seconds)
ai_homework_threshold = 90  # AI homework skip threshold

[exam]
save_nums = 5            # Number of questions saved per batch
delay_min = 3.0          # Minimum delay after saving each batch (seconds)
delay_max = 5.0          # Maximum delay after saving each batch (seconds)

[display]
log_level = "INFO"       # DEBUG / INFO / WARNING / ERROR

[proxies]
http = ""                # HTTP proxy
https = ""               # HTTPS proxy

[qr]
image_path = ""          # QR code save path (empty for default directory)

[ai]
enabled = true
use_builtin_ai = true    # AI smart courses only: use Zhihuishu built-in AI
api_key = ""             # OpenAI-compatible API Key (used by AI courses when use_builtin_ai = false; required for Zhidao homework/exam)
base_url = "https://api.openai.com/v1"
model = "gpt-4o-mini"
max_token = 27900

[crypto]                 # Encryption keys (generally no modification needed)
[urls]                   # API URLs (generally no modification needed)
```

> **AI Answering**: For **AI smart courses**, the built-in Zhihuishu AI is used by default (no API key required). **Prerequisite: an AI smart course must exist**. The built-in AI performs poorly; a custom LLM is recommended — set `use_builtin_ai = false` and fill in `api_key` and `base_url`. The API key is not limited to that case: AI smart courses also use it when `use_builtin_ai = false`, while **Zhidao homework/exam have no built-in AI and require `api_key`**.

## Data Directory

Program data is saved under `~/.zhs/` by default:

| Path | Description |
|------|-------------|
| `config.toml` | Configuration file |
| `cookies.json` | Login cookies |
| `execution.json` | Course list generated by `zhs fetch` |
| `qrcode.png` | Login QR code image |
| `logs/` | Log directory (daily rotation, 30 days retention) |
| `cache/` | Answer cache directory (SQLite database, see below) |

### Cache Storage

Answer cache is stored in SQLite database `~/.zhs/cache/questions_bank.db`, containing two tables:

| Table | Description |
|-------|-------------|
| `zhidao_questions` | Zhidao homework answer cache (dual key: eid + question_id, includes correct/incorrect flags, AI analysis) |
| `ai_questions` | AI homework/exam answer cache (single key: question_id, shared by HomeworkCtx and ExamCtx) |

Export to human-readable JSON for sharing with `zhs cache export -c COURSE_ID`, import with `zhs cache import PATH`.
Legacy JSON cache can be migrated to SQLite using `.temp/migrate_cache_to_db.py`.

## Development

### Development Workflow

This project follows TDD (Test-Driven Development) workflow, strictly adhering to the Red → Green → Refactor cycle for each module. See [docs/test.md](docs/test.md) for details.

### Quality Checks

```bash
# Run all tests
uv run pytest

# Lint check
uv run ruff check src/ tests/

# Format check
uv run ruff format --check src/ tests/

# Type check
uv run mypy src/ tests/
```

### Documentation

| Document | Purpose |
|----------|---------|
| [docs/spec.md](docs/spec.md) | Feature specifications, API endpoints, data structures |
| [docs/design.md](docs/design.md) | Module-level design, class signatures, flowcharts |
| [docs/tutorial.md](docs/tutorial.md) | User tutorial |
| [docs/test.md](docs/test.md) | Testing strategy and cases |
| [docs/linter.md](docs/linter.md) | Code standards |

## About
This project is developed using Python. I strive to improve code comments and documentation to facilitate community development.

## License

GPL-3.0-only