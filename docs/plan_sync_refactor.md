# AI Homework 异步转同步重构计划

> Branch: `feat/zhidao_homework`
> 目标: 将 `src/zhs/ai/homework.py` 从异步改为同步，删除旧异步接口，移除 pytest-asyncio 依赖

---

## 1. 背景与动机

### 1.1 问题
现有 `HomeworkCtx`（`src/zhs/ai/homework.py`）使用 `asyncio` 异步实现：
- `asyncio.Semaphore(3)` 限制并发为 3
- `asyncio.gather(*tasks)` 并发处理题目
- `asyncio.create_task(self._heartbeat())` 异步心跳
- `await asyncio.sleep()` 异步延迟

**作业 API（`studentexamtest.zhihuishu.com`）有时间速率限制**，并发请求会触发限流，导致 API 失败。异步并发反而成为负担。

### 1.2 解决方案
改为同步顺序执行：
- 逐题顺序处理（不再并发），天然避免限流
- 心跳改用 daemon 线程
- 延迟用 `time.sleep()`
- 删除 session.py 中所有异步接口（`ai_exam_query`/`async_api_query`/`_get_async_client`/`aclose`/`_async_client`）
- 移除 `pytest-asyncio` 依赖（项目不再有异步代码）

---

## 2. 变更清单

### 2.1 `src/zhs/ai/homework.py` — 异步转同步

**删除**:
- `import asyncio`
- `_semaphore: asyncio.Semaphore = asyncio.Semaphore(3)` 类属性
- `_heartbeat_task: asyncio.Task[None] | None = None` 属性

**修改**:
| 方法 | 异步签名 | 同步签名 |
|------|---------|---------|
| `start()` | `async def start(...) -> tuple[bool, int, int]` | `def start(...) -> tuple[bool, int, int]` |
| `_api_query()` | `async def _api_query(...)` → `await self._session.ai_exam_query(...)` | `def _api_query(...)` → `self._session.ai_exam_query(...)` |
| `_open_homework()` | `async def` + `await` | `def` + 直接调用 |
| `_get_sheet_content()` | `async def` + `await` | `def` + 直接调用 |
| `_get_question_content()` | `async def` + `await` | `def` + 直接调用 |
| `_save_answer()` | `async def` + `await` | `def` + 直接调用 |
| `_submit_homework()` | `async def` + `await` | `def` + 直接调用 |
| `_check_results()` | `async def` + `await` | `def` + 直接调用 |
| `_heartbeat()` | `async def` + `await asyncio.sleep()` | `def` + `time.sleep()` |
| `_process_question()` | `async def` + `async with self._semaphore` + `await asyncio.sleep(random.uniform(3, 5))` | `def` + `time.sleep(random.uniform(3, 5))` |

**并发改顺序**:
```python
# 旧（异步并发）
tasks = [self._process_question(sheet) for sheet in sheets]
await asyncio.gather(*tasks)

# 新（同步顺序）
for sheet in sheets:
    self._process_question(sheet)
```

**心跳改线程**:
```python
# 旧（asyncio task）
self._heartbeat_task = asyncio.create_task(self._heartbeat())
# ...
if self._heartbeat_task:
    self._heartbeat_task.cancel()

# 新（daemon 线程）
import threading
self._heartbeat_thread = threading.Thread(target=self._heartbeat, daemon=True)
self._heartbeat_thread.start()
# 线程通过 self._stopped 标志自动退出，无需显式 cancel
```

### 2.2 `src/zhs/session.py` — 删除异步接口

**删除以下方法/属性**:
- `_async_client: httpx.AsyncClient | None = None`（`__init__` 中）
- `_get_async_client()` 方法
- `async_api_query()` 方法
- `ai_exam_query()` **异步**方法
- `aclose()` 异步方法

**新增同步 `ai_exam_query()` 方法**（替代异步版本，签名相同但去掉 `async/await`）:
```python
def ai_exam_query(
    self,
    url: str,
    data: dict[str, Any],
    key: bytes | None = None,
    ok_code: int = 0,
    method: str = "POST",
) -> dict[str, Any]:
    """AI 考试 API 同步查询，密钥从 config.crypto 获取"""
    if key is None:
        key = self.crypto.key_bytes("exam_key")
    iv = self.crypto.key_bytes("iv")

    cipher = Cipher(key, iv)
    encrypted_data = cipher.encrypt(json.dumps(data))

    form_data = {
        "secretStr": encrypted_data,
        "dateFormate": str(int(time.time()) * 1000),
    }

    result = self.api_query(url, data=form_data, method=method)

    code = result.get("code", 0)
    if code != ok_code:
        raise ApiError(code=code, message=result.get("message", ""))

    return result
```

> 注：AI 考试 API（`studentexamtest`）与知到作业 API（`studentexam-api`）不同：
> - AI 考试：发送 `dateFormate` 字段，检查 `code` 字段
> - 知到作业：不发送 `dateFormate`，检查 `status` 字段
> 因此保留两个独立方法（`ai_exam_query` 同步 + `homework_query` 同步）。

### 2.3 `src/zhs/ai/course.py` — 移除 asyncio

```python
# 旧
import asyncio
is_success, correct, total = asyncio.run(
    homework_ctx.start(reference_materials=reference_materials)
)

# 新（删除 import asyncio，直接调用）
is_success, correct, total = homework_ctx.start(
    reference_materials=reference_materials
)
```

### 2.4 `tests/ai/test_homework.py` — 测试转同步

**删除**:
- `from unittest.mock import AsyncMock`
- `@pytest.mark.asyncio` 装饰器
- `patch("zhs.ai.homework.asyncio.sleep", new_callable=AsyncMock)`

**修改**:
- `AsyncMock` → `MagicMock`
- `await homework_ctx._submit_homework()` → `homework_ctx._submit_homework()`
- `await homework_ctx._process_question(sheet)` → `homework_ctx._process_question(sheet)`
- `await homework_ctx._open_homework()` → `homework_ctx._open_homework()`
- `patch("zhs.ai.homework.asyncio.sleep", ...)` → `patch("zhs.ai.homework.time.sleep", ...)`

**删除测试**:
- `test_semaphore_value`（不再有 semaphore）

**新增测试**:
- `test_heartbeat_uses_thread`（验证心跳使用 daemon 线程）

### 2.5 `tests/test_session.py` — 测试转同步

`TestAiExamQuery` 类的 3 个异步测试改为同步：
- 删除 `@pytest.mark.asyncio`
- 删除 `await`、`await session.aclose()`
- 改为同步调用 `session.ai_exam_query(...)`

### 2.6 `pyproject.toml` — 移除 pytest-asyncio

**删除**:
```toml
# dependencies 中
"pytest-asyncio>=0.25",  # 异步测试支持（AI 考试模块）

# [tool.pytest.ini_options] 中
asyncio_mode = "auto"       # 自动识别 async 测试函数，无需 @pytest.mark.asyncio
```

### 2.7 文档更新

| 文档 | 更新内容 |
|------|---------|
| `docs/design.md` | HomeworkCtx 章节改为同步设计，删除 asyncio 流程图 |
| `docs/test.md` | 删除异步测试相关内容 |
| `docs/log.md` | 记录本次重构 |
| `docs/linter.md` | 删除 asyncio 相关规范，新增同步规范 |
| `.trae/rules/project_rules.md` | 更新规则（见下文） |

---

## 3. TDD 执行步骤

### Step 1: RED — 修改测试（先让测试失败）

1. 修改 `tests/ai/test_homework.py`：
   - 删除 `AsyncMock`、`@pytest.mark.asyncio`
   - 将异步测试改为同步测试
   - 删除 `test_semaphore_value`
   - 新增 `test_heartbeat_uses_thread`
2. 修改 `tests/test_session.py`：
   - 将 `TestAiExamQuery` 改为同步
3. 运行 `pytest tests/ai/test_homework.py tests/test_session.py` → 确认失败（红色）

### Step 2: GREEN — 修改实现（让测试通过）

1. 修改 `src/zhs/session.py`：
   - 删除异步方法（`_async_client`、`_get_async_client`、`async_api_query`、`aclose`）
   - 将 `ai_exam_query` 改为同步
2. 修改 `src/zhs/ai/homework.py`：
   - 删除 `import asyncio`
   - 所有 `async def` → `def`
   - 所有 `await` 删除
   - `asyncio.gather` → `for` 循环
   - `asyncio.create_task` → `threading.Thread`
   - `asyncio.sleep` → `time.sleep`
3. 修改 `src/zhs/ai/course.py`：
   - 删除 `import asyncio`
   - `asyncio.run(...)` → 直接调用
4. 修改 `pyproject.toml`：
   - 删除 `pytest-asyncio` 依赖
   - 删除 `asyncio_mode` 配置
5. 运行 `pytest` → 确认全绿

### Step 3: REFACTOR — 重构与验证

1. `ruff check src/ tests/` → 修复 lint 错误
2. `ruff format src/ tests/` → 格式化
3. `mypy src/ tests/` → 修复类型错误
4. `pytest` → 确认仍全绿
5. 更新文档

---

## 4. 验证标准

| 检查项 | 命令 | 期望结果 |
|--------|------|---------|
| 全量测试 | `pytest` | 全部通过 |
| Lint | `ruff check src/ tests/` | All checks passed |
| Format | `ruff format --check src/ tests/` | 已格式化 |
| 类型检查 | `mypy src/ tests/` | Success: no issues |
| 无 asyncio 残留 | `grep -r "asyncio" src/zhs/ai/` | 无匹配 |
| 无 async 残留 | `grep -r "async def\|await " src/zhs/ai/homework.py` | 无匹配 |
| 无 pytest-asyncio | `grep "pytest-asyncio" pyproject.toml` | 无匹配 |

---

## 5. 风险与回滚

### 风险
- 心跳线程可能与主线程竞争 `httpx.Client`（httpx.Client 线程安全，风险低）
- 顺序处理比并发慢（但这是预期效果，避免限流）

### 回滚
- 所有改动在单一 commit 中，可通过 `git revert` 回滚
