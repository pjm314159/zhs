# ZHS 代码规范与 Linter 配置

> 本文档定义 ZHS 项目的编码规范、ruff 规则说明及例外配置。

---

## 1. 工具链概览

| 工具 | 用途 | 触发时机 |
|------|------|----------|
| **ruff** | Linter + Formatter | 每次提交 / CI |
| **mypy** | 静态类型检查（strict） | 每次提交 / CI |
| **pytest** | 测试（含 respx HTTP Mock、freezegun 时间 Mock） | 每次提交 / CI |

运行命令（项目使用 `uv`）：

```bash
uv run ruff check src/ tests/           # Lint 检查
uv run ruff check src/ tests/ --fix     # 自动修复
uv run ruff format src/ tests/          # 格式化
uv run mypy src/ tests/                 # 类型检查
uv run pytest                           # 运行测试（默认跳过 integration）
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

#### F822 — `__all__` 中未定义的名称（PEP 562 懒加载）

当模块使用 PEP 562 `__getattr__` 懒加载导出名称时，`__all__` 中列出的名称在模块顶层并不存在，ruff 会报 `F822 Undefined name in '__all__'`。

```python
# zhs/zhidao/homework/cache.py — PEP 562 兼容入口
__all__ = ["HomeworkCache"]  # noqa: F822

def __getattr__(name: str):
    if name == "HomeworkCache":
        from zhs.cache.zhidao_cache import ZhidaoHomeworkCache
        return ZhidaoHomeworkCache
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

> **项目应用**：`zhs.zhidao.homework.cache` 是兼容入口，通过 PEP 562 懒加载 `ZhidaoHomeworkCache` 并别名为 `HomeworkCache`，避免破坏旧代码导入路径。

#### I001 — 导入排序

按以下顺序分组，组间空一行：

```python
# 1. 标准库
import json
import time
from pathlib import Path
from typing import Any

# 2. 第三方库
import httpx
from loguru import logger
from pydantic import BaseModel

# 3. 本项目模块
from zhs.config import AppConfig, CryptoConfig
from zhs.crypto import Cipher, encode_ev
from zhs.exceptions import ZhsError
```

> **禁止** `import asyncio`：项目已全面同步化，禁止使用 `asyncio`、`async def`、`await`。

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

#### UP046 / UP047 — PEP 695 泛型语法

Python 3.12+ 支持 PEP 695 类型参数语法，ruff `UP046` 要求泛型类使用新语法：

```python
# ✅ 正确：PEP 695 类型参数语法
class BaseQuestionCache[T](ABC):
    def get(self, key: str) -> T | None: ...
    def put(self, key: str, value: T) -> None: ...

# ❌ 错误：旧式 TypeVar + Generic
from typing import Generic, TypeVar
T = TypeVar("T")
class BaseQuestionCache(Generic[T], ABC):
    ...
```

> **项目应用**：`zhs.cache.base.BaseQuestionCache[T]` 使用此语法，子类 `ZhidaoHomeworkCache[HomeworkCacheEntry]` / `AiExamCache[dict[str, Any]]` 显式指定类型参数。

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
- `setup_logging()` 是幂等的：重复调用不会重复注册 sink（由 `_initialized` 标志保证）

```python
# ✅ 正确：CLI 入口配置
# __main__.py 中 _setup_logger() 调用 zhs.logger.setup_logging(config)
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

#### 敏感信息脱敏

- 日志中**禁止**输出完整的 cookie、token、password、apiKey 值
- `setup_logging()` 注册的 `_sensitive_filter` 会自动脱敏（基于 loguru 的 `filter` 机制，而非 `patcher`）
- 脱敏规则定义在 `zhs.logger._SENSITIVE_PATTERNS`，覆盖：
  - `CASLOGC=<value>` → `CASLOGC=***`
  - `token=<value>` → `token=***`
  - `password=<value>` → `password=***`
  - `apiKey=<value>` → `apiKey=***`
  - `Bearer <value>` → `Bearer ***`
- 仍应避免主动传入敏感值

```python
# ✅ 正确：不输出敏感值
logger.info("登录成功: uuid={}", uuid)

# ❌ 错误：输出完整 cookie
logger.debug("cookies: {}", dict(cookies))
```

> **注意**：loguru 0.7.3 的 `patch()` 返回新实例而非修改全局 logger，因此项目使用 `filter` 而非 `patcher` 实现脱敏。

### 4.5 同步代码规范（禁止 asyncio）

**项目已全面同步化，禁止使用 `asyncio`**：

- ❌ 禁止 `import asyncio`
- ❌ 禁止 `async def` / `await`
- ❌ 禁止 `asyncio.sleep()` / `asyncio.create_task()` / `asyncio.Semaphore`
- ❌ 禁止 `pytest-asyncio` / `@pytest.mark.asyncio` / `AsyncMock`
- ✅ 所有延迟使用 `time.sleep()`
- ✅ 所有 HTTP 请求使用 `httpx.Client`（同步）
- ✅ 后台任务使用 `threading.Thread`

```python
# ✅ 正确：同步延迟
import time
time.sleep(3)

# ✅ 正确：同步 HTTP 请求
client = httpx.Client()
resp = client.post(url, data=data)

# ✅ 正确：后台任务用 threading
import threading
def _heartbeat(self) -> None:
    while not self._stopped:
        self._update_time()
        time.sleep(10)

thread = threading.Thread(target=self._heartbeat, daemon=True)
thread.start()

# ❌ 错误：禁止 asyncio
import asyncio
await asyncio.sleep(3)
async def fetch(): ...
```

### 4.6 线程规范

- 后台任务使用 `threading.Thread(daemon=True)`，通过 `_stopped` 标志退出
- `_watch_video` 使用独立 `httpx.Client`，不共享 session 的 cookies/headers
- 线程内部必须 `try/except Exception` 全捕获并 `logger.error`，禁止裸 `except: pass`
- 不在线程间共享可变状态（cookies、headers）

```python
# ✅ 正确：daemon 线程 + _stopped 标志 + 全捕获
class HomeworkCtx:
    def __init__(self) -> None:
        self._stopped = False

    def _heartbeat(self) -> None:
        while not self._stopped:
            try:
                self._update_time()
            except Exception:
                logger.error("心跳失败", exc_info=True)
            time.sleep(10)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._heartbeat, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopped = True
        self._thread.join(timeout=5)

# ❌ 错误：吞掉异常
def _watch_video(self) -> None:
    try:
        ...
    except Exception:
        pass  # 禁止！
```

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

### 4.9 typer CLI 规范

- CLI 使用 typer 框架，命令式接口（`zhs play/homework/exam/fetch`）
- 禁止旧版 `zhs -c ID` 风格
- `typer.Option` 默认值用 `# noqa: B008` 抑制（typer 推荐写法）
- 命令参数必须有完整类型注解和 `help` 说明

```python
# ✅ 正确：typer 命令式
@app.command()
def play(
    course: list[str] | None = typer.Option(None, "-c", "--course", help="课程 ID"),  # noqa: B008
    speed: float | None = typer.Option(None, "-s", "--speed", help="播放速度"),  # noqa: B008
) -> None:
    """刷视频"""
    ...

# ❌ 错误：旧版 argparse 风格
parser.add_argument("-c", "--course")
```

### 4.10 循环导入解决模式

项目在重构后存在跨包依赖（如 `zhs.cache.zhidao_cache` ↔ `zhs.zhidao.homework.models`），使用以下两种模式解决：

#### 4.10.1 PEP 562 模块级 `__getattr__`（兼容入口）

当旧代码依赖某个导入路径，但实际实现已迁移到其他模块时，使用 PEP 562 懒加载：

```python
# zhs/zhidao/homework/cache.py — 兼容入口
"""向后兼容：HomeworkCache 已迁移到 zhs.cache.zhidao_cache.ZhidaoHomeworkCache"""
__all__ = ["HomeworkCache"]  # noqa: F822


def __getattr__(name: str):
    if name == "HomeworkCache":
        from zhs.cache.zhidao_cache import ZhidaoHomeworkCache
        return ZhidaoHomeworkCache
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

> **注意**：新代码应直接从 `zhs.cache.zhidao_cache` 导入 `ZhidaoHomeworkCache`，避免使用兼容入口。

#### 4.10.2 `TYPE_CHECKING` 守卫（仅类型注解需要）

当模块 A 仅在类型注解中引用模块 B（运行时通过参数注入实例），使用 `TYPE_CHECKING` 守卫避免运行时循环导入：

```python
# zhs/zhidao/homework/analyzer.py
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zhs.cache.zhidao_cache import ZhidaoHomeworkCache  # 仅类型检查时导入


class HomeworkAnalyzer:
    def __init__(self, cache: ZhidaoHomeworkCache) -> None:
        """cache 类型注解，运行时由调用方传入实例"""
        self._cache = cache
```

> **关键**：`from __future__ import annotations` 使所有类型注解变为字符串，运行时不求值，配合 `TYPE_CHECKING` 守卫可在不触发循环导入的前提下使用类型注解。

#### 4.10.3 何时使用哪种模式

| 场景 | 模式 | 示例 |
|------|------|------|
| 旧导入路径需保留向后兼容 | PEP 562 `__getattr__` | `zhs.zhidao.homework.cache.HomeworkCache` |
| 仅类型注解需要引用（运行时实例由参数注入） | `TYPE_CHECKING` 守卫 | `analyzer.py` / `worker.py` 中的 `ZhidaoHomeworkCache` |
| 运行时确实需要调用对方函数 | 重构依赖关系（提取公共模块） | — |

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

### 6.1 PEP 562 `__getattr__` 与 mypy

mypy 无法解析 PEP 562 模块级 `__getattr__` 懒加载的名称作为类型。当兼容入口导出的名称被用作类型注解时，mypy 会报 `Variable "..." is not valid as a type`。

```python
# ❌ 错误：mypy 无法将 HomeworkCache 识别为类型
from zhs.zhidao.homework.cache import HomeworkCache

def foo(cache: HomeworkCache) -> None: ...  # mypy 报错
```

**解决**：直接从实际实现模块导入，不使用兼容入口：

```python
# ✅ 正确：直接从实现模块导入
from zhs.cache.zhidao_cache import ZhidaoHomeworkCache

def foo(cache: ZhidaoHomeworkCache) -> None: ...
```

### 6.2 PEP 695 泛型与 mypy

PEP 695 类型参数语法（`class Foo[T]:`）在 mypy 1.13+ 完全支持，无需特殊配置。

```python
# mypy 正确识别 T 为类型参数
class BaseQuestionCache[T](ABC):
    def get(self, key: str) -> T | None: ...
```

### 6.3 `TYPE_CHECKING` 守卫与 mypy

`TYPE_CHECKING` 在 mypy 检查时为 `True`，运行时为 `False`。配合 `from __future__ import annotations` 可在避免运行时循环导入的同时保持类型安全：

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zhs.cache.zhidao_cache import ZhidaoHomeworkCache

class Analyzer:
    def __init__(self, cache: ZhidaoHomeworkCache) -> None:
        # mypy 知道 cache 是 ZhidaoHomeworkCache，运行时不触发导入
        self._cache = cache
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
ruff check src/ tests/           # 0 errors
ruff format --check src/ tests/  # 0 changes needed
mypy src/ tests/                 # 0 errors
pytest                            # all green（默认跳过 integration 标记）
```

完整命令（含集成测试，需真实 API + 扫码登录）：

```bash
pytest -m integration tests/integration/
```
