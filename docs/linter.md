# ZHS 代码规范与 Linter 配置

> 本文档定义 ZHS 项目的编码规范、ruff 规则说明及例外配置。

---

## 1. 工具链概览

| 工具 | 用途 | 触发时机 |
|------|------|----------|
| **ruff** | Linter + Formatter | 每次提交 / CI |
| **mypy** | 静态类型检查 | 每次提交 / CI |
| **pytest** | 测试 | 每次提交 / CI |

运行命令：

```bash
ruff check src/          # Lint 检查
ruff check src/ --fix    # 自动修复
ruff format src/         # 格式化
mypy src/                # 类型检查
```

---

## 2. Ruff 规则详解

### 2.1 已启用的规则集

| 规则集 | 前缀 | 说明 | 关键规则示例 |
|--------|------|------|-------------|
| pycodestyle Error | `E` | 风格错误 | E501 行过长、E302 类前空行 |
| Pyflakes | `F` | 逻辑错误 | F401 未使用导入、F841 未使用变量 |
| isort | `I` | 导入排序 | I001 未排序的导入 |
| pyupgrade | `UP` | 现代化语法 | UP006 用 `list[X]` 替代 `List[X]`、UP035 过时类型 |
| flake8-bugbear | `B` | 常见陷阱 | B904 `except` 中未使用 `from` 链式抛出、B006 可变默认参数 |
| flake8-simplify | `SIM` | 简化建议 | SIM108 用三元表达式替代 if-else、SIM118 用 `key in dict` 替代 `key in dict.keys()` |

### 2.2 关键规则说明

#### E501 — 行长度限制

```
line-length = 120
```

- 默认 120 字符，与 pyproject.toml 中 `line-length` 一致
- 超长字符串（如 URL、密钥）可用 `# noqa: E501` 豁免
- 不要为了缩短行而过度拆分链式调用

```python
# ✅ 允许：URL 不拆分
API_URL = "https://onlineservice-api.zhihuishu.com/gateway/t/v1/learning/queryCourse"  # noqa: E501

# ❌ 禁止：为缩短行而破坏可读性
result = (session
    .zhidao_query(
        "/gateway/t/v1/learning/queryCourse",
        data={},
    ))
```

#### F401 — 未使用的导入

- 严格禁止未使用的导入
- `__init__.py` 中用于重新导出的导入用 `from .module import X  # noqa: F401` 标注

```python
# zhs/__init__.py
from zhs.crypto import Cipher, WatchPoint  # noqa: F401
```

#### I001 — 导入排序

按以下顺序分组，组间空一行：

```python
# 1. 标准库
import asyncio
import json
from pathlib import Path

# 2. 第三方库
import httpx
from loguru import logger
from pydantic import BaseModel

# 3. 本项目模块
from zhs.config import AppConfig, CryptoConfig
from zhs.crypto import Cipher, encode_ev
from zhs.exceptions import ZhsError
```

#### UP006 / UP035 — 现代化类型注解

Python 3.13 项目，使用内置泛型：

```python
# ✅ 正确
def foo(items: list[str]) -> dict[str, int]: ...
def bar() -> str | None: ...

# ❌ 错误
from typing import List, Dict, Optional
def foo(items: List[str]) -> Dict[str, int]: ...
def bar() -> Optional[str]: ...
```

#### B006 — 可变默认参数

```python
# ❌ 错误：可变默认参数
class Foo:
    def __init__(self, items: list = []): ...

# ✅ 正确
class Foo:
    def __init__(self, items: list | None = None):
        self.items = items or []
```

#### B904 — except 中未使用 from 链式抛出

```python
# ❌ 错误：丢失原始 traceback
try:
    ...
except ValueError as e:
    raise ZhsError(str(e))

# ✅ 正确：使用 from 保留异常链
try:
    ...
except ValueError as e:
    raise ZhsError(str(e)) from e
```

> **补充**：B907 规则提示将 `f"'{foo}'"` 替换为更具可读性的 `f"{foo!r}"`，与本条不同。

#### SIM108 — 三元表达式

```python
# ❌ 冗长
if condition:
    result = "yes"
else:
    result = "no"

# ✅ 简洁
result = "yes" if condition else "no"

# 但如果分支逻辑复杂（> 80 字符或含函数调用），保留 if-else
```

#### SIM118 — `key in dict` 替代 `key in dict.keys()`

```python
# ❌ 冗余
if "uuid" in cookies.keys(): ...

# ✅ 简洁
if "uuid" in cookies: ...
```

---

## 3. 未启用但值得注意的规则

以下规则未在 `select` 中启用，但开发者应了解：

| 规则 | 前缀 | 未启用原因 | 建议 |
|------|------|-----------|------|
| flake8-comprehensions | `C4` | 部分建议与可读性冲突 | 手动遵循：优先用列表推导替代 `list(map(...))` |
| flake8-return | `RET` | 过于严格 | 保持函数出口简洁即可 |
| flake8-arguments | `ARG` | 回调函数常有未使用参数 | 用 `_` 前缀标记故意未使用的参数 |
| pep8-naming | `N` | 旧 API 字段名不兼容（如 `optionVos`） | pydantic 模型用 `alias` 适配 |
| flake8-logging-format | `G` | loguru 格式与 stdlib 不同 | 不适用 |
| flake8-quotes | `Q` | 项目统一双引号（ruff format 默认） | 无需额外规则 |

---

## 4. 项目特定约定

### 4.1 命名规范

| 类型 | 风格 | 示例 |
|------|------|------|
| 模块/包 | `snake_case` | `crypto.py`, `video.py` |
| 类 | `PascalCase` | `ZhsSession`, `ExamCtx` |
| 函数/方法 | `snake_case` | `play_video()`, `encode_ev()` |
| 常量 | `UPPER_SNAKE_CASE` | `DEFAULT_SPEED`, `MAX_RETRIES` |
| 私有方法 | `_leading_underscore` | `_watch_video()`, `_process_question()` |
| pydantic 字段 | `snake_case` | `video_key`, `study_progress` |
| pydantic 字段（映射旧 API） | `snake_case` + `alias` | `option_vos: list = Field(alias="optionVos")` |

### 4.2 类型注解

- **所有公开函数必须有完整类型注解**（mypy strict 强制）
- 私有方法也应有类型注解
- 使用 `...` 而非 `pass` 作为抽象方法/协议的占位

```python
# ✅
def play_video(self, rac_id: str, video_id: int) -> None: ...

# ❌
def play_video(self, rac_id, video_id):
    pass
```

### 4.3 异常处理

- 自定义异常继承 `ZhsError`
- 始终用 `raise ... from e` 链式抛出
- 不要捕获 `Exception` 基类，除非是线程入口或顶层防护

```python
# ✅ 线程入口防护
def _watch_video(self, video_id: int) -> None:
    try:
        ...
    except Exception:
        logger.error("watch_video thread failed", exc_info=True)

# ❌ 吞掉异常
try:
    ...
except Exception:
    pass
```

### 4.4 日志规范

使用 `loguru`，不要使用 `logging`：

```python
from loguru import logger

logger.info("开始刷课: course_id={}", course_id)
logger.warning("视频进度异常: played={} end={}", played_time, end_time)
logger.error("API 请求失败: url={} code={}", url, code)
logger.debug("ev 数据: {}", ev_data)
```

- `logger.info`：正常流程（登录成功、开始刷课、完成）
- `logger.warning`：可恢复的异常（进度异常、重试）
- `logger.error`：不可恢复错误（API 失败、认证过期）
- `logger.debug`：调试信息（加解密数据、请求详情）

#### 初始化与配置

- **禁止**在业务模块中配置 loguru sink（`logger.add()`/`logger.remove()`）
- 日志配置统一由 `zhs.logger.setup_logging(config)` 完成，仅在 CLI 入口调用
- 业务模块只需 `from loguru import logger`，无需 import `zhs.logger`
- `setup_logging()` 必须在业务逻辑之前调用

```python
# ✅ 正确：CLI 入口配置
# __main__.py
from zhs.logger import setup_logging
setup_logging(config)

# ✅ 正确：业务模块使用
# login.py
from loguru import logger
logger.info("登录成功")

# ❌ 错误：业务模块自行配置
# login.py
from loguru import logger
logger.add("login.log")  # 禁止！
```

#### 敏感信息

- 日志中**禁止**输出完整的 cookie、token、password、apiKey 值
- `setup_logging()` 注册的 patcher 会自动脱敏，但仍应避免主动传入敏感值
- 脱敏规则见 `design.md` 2.11.4

```python
# ✅ 正确：不输出敏感值
logger.info("登录成功: uuid={}", uuid)

# ❌ 错误：输出完整 cookie
logger.debug("cookies: {}", dict(cookies))
```

### 4.5 异步代码规范

- `asyncio.Semaphore` 用于限制并发
- `await asyncio.sleep()` 用于延迟，不要用 `time.sleep()`
- 异步函数用 `async def`，调用用 `await`
- 心跳等后台任务用 `asyncio.create_task()` + 显式取消

```python
# ✅
async def _heartbeat(self, interval: int = 10) -> None:
    while self._running:
        await self._update_time()
        await asyncio.sleep(interval)

# ❌ 在异步上下文中使用 time.sleep
async def _heartbeat(self):
    while True:
        self._update_time()
        time.sleep(10)  # 阻塞事件循环！
```

### 4.6 线程规范

- `_watch_video` 使用独立 `httpx.Client`，不共享 session
- 线程必须 `daemon=True`
- 线程内部 `try/except Exception` 全捕获
- 不在线程间共享可变状态（cookies、headers）

### 4.7 字符串引号

- ruff format 默认双引号，遵循即可
- f-string 中嵌套引号用相反引号：

```python
# ✅
f"course_id={self.course_id}"
f'key="{key}"'

# ❌ 混用
f'course_id={self.course_id}'
```

### 4.8 文件编码

- 所有 `.py` 文件 UTF-8 编码
- 不需要 `# -*- coding: utf-8 -*-` 声明（Python 3 默认）

---

## 5. Ruff 例外配置

### 5.1 按文件豁免

```toml
# pyproject.toml
[tool.ruff.lint.per-file-ignores]
"__init__.py" = ["F401"]          # 允许未使用的导入（重新导出）
"tests/**/*.py" = ["B011"]        # 测试中允许 assert False
```

### 5.2 行内豁免

```python
# 单行豁免
long_url = "https://very-long-url.example.com/api/v1/endpoint"  # noqa: E501

# 特定规则豁免
from zhs.crypto import Cipher  # noqa: F401

# 多规则豁免
x = {"key": "very long value that exceeds line limit"}  # noqa: E501, B018
```

### 5.3 全局忽略规则

当前无全局忽略规则。如需添加，在 `pyproject.toml` 中：

```toml
[tool.ruff.lint]
ignore = []
```

---

## 6. Mypy 严格模式要点

`strict = true` 启用以下检查：

| 检查项 | 说明 |
|--------|------|
| `disallow_untyped_defs` | 所有函数必须有类型注解 |
| `disallow_any_generics` | 泛型必须指定类型参数 |
| `warn_return_any` | 返回 Any 时警告 |
| `warn_unused_configs` | 未使用的 mypy 配置警告 |
| `disallow_untyped_calls` | 调用无类型注解函数时警告 |
| `strict_optional` | None 检查严格模式 |

常见 mypy 问题及解决：

```python
# 问题：httpx 响应 json() 返回 Any
# 解决：显式标注类型
def get_data() -> dict:
    result: dict = response.json()  # 显式标注
    return result

# 问题：pydantic model 字段类型推断
# 解决：Field 显式标注
class MyModel(BaseModel):
    items: list[str] = Field(default_factory=list)
```

---

## 7. Pre-commit 集成（可选）

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        additional_dependencies: [pydantic>=2.10, httpx>=0.28]
```

安装：

```bash
pip install pre-commit
pre-commit install
```

---

## 8. CI 检查清单

每次提交必须通过：

```bash
ruff check src/           # 0 errors
ruff format --check src/  # 0 changes needed
mypy src/                 # 0 errors
pytest -m unit            # all green
```
