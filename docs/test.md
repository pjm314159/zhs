# ZHS TDD 测试计划

> 本文档定义 ZHS 项目的完整测试策略、fixture 设计、Mock 方案和每个模块的详细测试用例。
> 开发流程严格遵循 Red → Green → Refactor 循环。
> **项目已全面同步化**：禁止 `asyncio` / `pytest-asyncio` / `AsyncMock` / `@pytest.mark.asyncio`。

---

## 1. 测试架构

### 1.1 目录结构

```
tests/
├── conftest.py                       # 全局 fixtures
├── fixtures/
│   └── __init__.py
├── test_exceptions.py                # 异常层级
├── test_crypto.py                    # AES/ev/签名/WatchPoint
├── test_config.py                    # TOML 加载/保存/迁移
├── test_session.py                   # API 查询封装
├── test_login.py                     # 登录流程
├── test_logger.py                    # 日志/脱敏
├── utils/
│   ├── __init__.py
│   ├── test_cookie.py                # Cookie 序列化
│   ├── test_display.py               # 显示工具
│   └── test_path.py                  # 路径工具
├── zhidao/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_models.py                # 知到模型
│   ├── test_course.py                # 课程列表
│   ├── test_video.py                 # 视频播放
│   ├── test_quiz.py                  # 弹窗答题
│   └── homework/                     # 知到作业子包
│       ├── __init__.py
│       ├── test_models.py            # 作业模型
│       ├── test_scanner.py           # 作业扫描
│       ├── test_worker.py            # 做题器
│       ├── test_analyzer.py          # 题目分析
│       ├── test_cache.py             # 答案缓存
│       └── test_ai_analysis_integration.py  # AI 分析集成
├── hike/
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_course.py
│   └── test_video.py
├── ai/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_models.py                # AI 课程模型
│   ├── test_course.py                # AI 课程管理
│   ├── test_ppt.py                   # PPT 转文本
│   ├── test_video.py                 # AI 视频播放
│   ├── test_homework.py              # AI 作业（HomeworkCtx）
│   └── test_exam.py                  # AI 考试（ExamCtx）
├── llm/
│   ├── __init__.py
│   ├── test_prompts.py               # Prompt 模板
│   ├── test_base.py                  # LLMProvider 抽象
│   ├── test_openai.py                # OpenAI 兼容
│   └── test_zhidao.py                # 智慧树内置 AI
├── cli/
│   ├── __init__.py
│   └── test_main.py                  # CLI 命令式接口
└── integration/                      # 集成测试（需真实 API + 扫码登录）
    ├── __init__.py
    ├── conftest.py                   # logged_in_session fixture
    ├── test_session_integration.py
    ├── test_login_integration.py
    ├── test_zhidao_integration.py
    ├── test_ai_integration.py
    ├── test_llm_integration.py
    └── test_cli_integration.py
```

### 1.2 测试分层策略

```mermaid
flowchart TD
    subgraph Unit["单元测试（无外部依赖）"]
        U1[crypto: AES/ev/签名/WatchPoint]
        U2[models: pydantic 模型]
        U3[prompts: 模板渲染]
        U4[cookie: 序列化]
        U5[path: 路径工具]
        U6[exceptions: 异常层级]
        U7[display: 显示工具]
    end

    subgraph Integration["集成测试（Mock HTTP）"]
        I1[config: TOML 加载/保存]
        I2[session: API 查询封装]
        I3[login: 登录流程]
        I4[course: 课程列表]
        I5[homework: 作业扫描/做题]
        I6[exam: AI 考试]
    end

    subgraph E2E["端到端测试（Mock 全部 API）"]
        E1[zhidao: 完整刷课流程]
        E2[hike: 完整刷课流程]
        E3[ai: 学习+作业+考试流程]
        E4[cli: 命令行入口]
    end

    subgraph Real["集成测试（真实 API）"]
        R1[需扫码登录]
        R2[标记 integration]
        R3[默认跳过]
    end

    Unit --> Integration --> E2E
    E2E -.可选.-> Real
```

| 层级 | Mock 策略 | 运行频率 | 标记 |
|------|----------|----------|------|
| 单元测试 | 无外部依赖，纯函数 | 每次提交 | 默认运行 |
| 集成测试 | `respx` Mock httpx 响应 | 每次提交 | 默认运行 |
| 端到端测试 | `respx` Mock 全部 API + `tmp_path` | 每次提交 | 默认运行 |
| 真实 API 测试 | 真实 HTTP + 扫码登录 | 手动 | `@pytest.mark.integration` |

### 1.3 pytest 配置

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-m 'not integration'"  # 默认跳过集成测试
markers = [
    "unit: 单元测试（无外部依赖）",
    "integration: 集成测试（需真实 API，需扫码登录）",
    "e2e: 端到端测试（Mock 全部 API）",
]
```

---

## 2. Fixtures 设计

### 2.1 全局 Fixtures (`tests/conftest.py`)

```python
"""ZHS 测试全局 fixtures"""

from pathlib import Path
from typing import Any

import pytest

from zhs.config import AppConfig


@pytest.fixture
def fixtures_dir() -> Path:
    """测试 fixtures 目录"""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_config() -> AppConfig:
    """默认 AppConfig 实例"""
    return AppConfig()


@pytest.fixture
def api_response_factory() -> Any:
    """通用 API 响应工厂"""

    def _make(
        code: int = 0,
        data: dict[str, Any] | list[dict[str, Any]] | None = None,
        message: str = "",
        status: int = 200,
    ) -> dict[str, Any]:
        return {"code": code, "data": data or {}, "message": message, "status": status}

    return _make
```

### 2.2 Session Fixtures（Mock HTTP）

> ⚠️ **重要**：`mock_session` fixture **禁止**使用 `@respx.mock` 装饰器！
> 因为 `@respx.mock` 的 Mock 环境仅在 fixture 函数体内生效，
> 当 fixture return 后 Mock 立即关闭，下游测试会穿透到真实网络。
>
> **正确做法**：在 fixture 内用 `with respx.mock:` 上下文管理器 + `yield`，
> 使 Mock 生命周期覆盖整个测试用例执行期。

```python
# tests/test_session.py
import respx
import pytest
from zhs.config import AppConfig
from zhs.session import ZhsSession


@pytest.fixture
def config() -> AppConfig:
    return AppConfig()


@pytest.fixture
def session(config: AppConfig) -> ZhsSession:
    """测试用 session（不 Mock HTTP，由测试用例自行 with respx.mock:）"""
    return ZhsSession(config)


@pytest.fixture
def mock_http() -> Any:
    """Mock HTTP 请求（推荐用法）"""
    with respx.mock:
        yield


@pytest.fixture
def authenticated_session(session: ZhsSession) -> ZhsSession:
    """已认证的 session（含 uuid 和 cookies）"""
    import httpx

    session.cookies = httpx.Cookies()
    session._cookies.set(
        "CASLOGC",
        '{"uuid":"test-uuid-123"}',
        domain="zhihuishu.com",
    )
    session._parse_uuid()
    return session
```

### 2.3 集成测试 Fixtures (`tests/integration/conftest.py`)

```python
"""集成测试 conftest — 提供真实 ZhsSession 和登录状态

运行方式：
    pytest tests/integration/ -m integration -v
    pytest tests/integration/ -m "integration and not manual_login"  # 跳过扫码
"""
import json
from collections.abc import Generator
from pathlib import Path

import pytest

from zhs.config import AppConfig, ConfigManager
from zhs.session import ZhsSession
from zhs.utils.cookie import cookies_to_list, list_to_cookies
from zhs.utils.path import get_data_dir


def pytest_configure(config: pytest.Config) -> None:
    """注册自定义标记"""
    config.addinivalue_line("markers", "integration: 需要真实 API 的集成测试")
    config.addinivalue_line("markers", "manual_login: 需要手动扫码登录")
    config.addinivalue_line("markers", "openai: 需要 OpenAI API Key")


@pytest.fixture(scope="session")
def app_config() -> AppConfig:
    return ConfigManager().load()


@pytest.fixture(scope="session")
def logged_in_session(app_config: AppConfig) -> Generator[ZhsSession]:
    """已登录的 ZhsSession（优先恢复 Cookie，否则扫码登录）"""
    session = ZhsSession(app_config)
    cookies_path = get_data_dir() / "cookies.json"

    if cookies_path.exists():
        with open(cookies_path, encoding="utf-8") as f:
            raw = json.load(f)
        session.cookies = list_to_cookies(raw)
        # 验证有效性...
    yield session
    session.close()
```

---

## 3. Mock 方案

### 3.1 HTTP Mock：respx（必须用上下文管理器）

```python
import respx
import httpx
from zhs.session import ZhsSession


# ✅ 正确：with respx.mock 上下文管理器
def test_zhidao_query(session: ZhsSession) -> None:
    with respx.mock:
        route = respx.post("https://onlineservice-api.zhihuishu.com/test").mock(
            return_value=httpx.Response(200, json={"code": 0, "data": {}})
        )
        result = session.zhidao_query("/test", data={"key": "value"})
        assert route.called
        assert "secretStr" in route.calls[0].request.content.decode()


# ✅ 正确：fixture 中用 with + yield
@pytest.fixture
def mock_http() -> Any:
    with respx.mock:
        yield


def test_with_fixture(session: ZhsSession, mock_http: Any) -> None:
    respx.post("...").mock(return_value=httpx.Response(200, json={...}))
    ...


# ❌ 错误：禁止 @respx.mock 装饰器（fixture 中）
@respx.mock  # 禁止！
def test_bad(session: ZhsSession) -> None:
    ...
```

### 3.2 时间 Mock：freezegun

```python
from freezegun import freeze_time


@freeze_time("2026-01-15 12:00:00")
def test_dateFormate_timestamp() -> None:
    """验证 dateFormate 时间戳为毫秒级"""
    import time

    assert int(time.time()) * 1000 == 1736932800000
```

### 3.3 同步 Mock：MagicMock（禁止 AsyncMock）

```python
from unittest.mock import MagicMock, patch


# ✅ 正确：MagicMock 用于同步方法
@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    session.crypto.exam_key = b"onbfhdyvz8x7otrp"
    session.crypto.key_bytes = MagicMock(
        side_effect=lambda name: getattr(session.crypto, name)
    )
    session.urls.exam = "https://studentexamtest.zhihuishu.com"
    return session


# ❌ 错误：禁止 AsyncMock（项目已同步化）
from unittest.mock import AsyncMock  # 禁止！
```

### 3.4 临时文件：tmp_path

```python
def test_config_save(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    mgr = ConfigManager(config_path)
    mgr.save(AppConfig())
    assert config_path.exists()
```

---

## 4. 详细测试用例

### 4.1 exceptions.py

```python
from zhs.exceptions import (
    ApiError,
    CaptchaRequired,
    LoginFailed,
    SliderVerificationRequired,
    TimeLimitExceeded,
    ZhsError,
)


class TestExceptions:
    def test_zhs_error_is_base(self) -> None:
        """ZhsError 是所有自定义异常的基类"""
        assert issubclass(ApiError, ZhsError)
        assert issubclass(CaptchaRequired, ZhsError)
        assert issubclass(SliderVerificationRequired, ZhsError)
        assert issubclass(LoginFailed, ZhsError)
        assert issubclass(TimeLimitExceeded, ZhsError)

    def test_api_error_carries_code_and_message(self) -> None:
        """ApiError 携带 code 和 message"""
        err = ApiError(code=-12, message="需要验证码")
        assert err.code == -12
        assert err.message == "需要验证码"
        assert "-12" in str(err)

    def test_catch_specific_then_base(self) -> None:
        """可以先捕获子异常再捕获基类"""
        with pytest.raises(CaptchaRequired):
            raise CaptchaRequired("验证码")
        with pytest.raises(ZhsError):
            raise CaptchaRequired("验证码")

    def test_slider_verification_required(self) -> None:
        """滑块验证异常"""
        with pytest.raises(SliderVerificationRequired):
            raise SliderVerificationRequired("需要滑块验证")
```

> **注意**：项目已移除 `InvalidCookies` 异常，测试中不再包含。

### 4.2 crypto.py

```python
from hashlib import md5
from zhs.crypto import Cipher, WatchPoint, encode_ev, sign_hike


class TestCipher:
    def test_encrypt_decrypt_roundtrip(self) -> None:
        """AES 加解密对称性"""
        cipher = Cipher(b"azp53h0kft7qi78q", b"1g3qqdh4jvbskb9x")
        plaintext = "hello world"
        assert cipher.decrypt(cipher.encrypt(plaintext)) == plaintext

    def test_encrypt_empty_string(self) -> None:
        """加密空字符串不崩溃"""
        cipher = Cipher(b"azp53h0kft7qi78q", b"1g3qqdh4jvbskb9x")
        assert cipher.decrypt(cipher.encrypt("")) == ""

    def test_encrypt_chinese(self) -> None:
        """加密中文字符"""
        cipher = Cipher(b"azp53h0kft7qi78q", b"1g3qqdh4jvbskb9x")
        text = "智慧树在线课程"
        assert cipher.decrypt(cipher.encrypt(text)) == text

    def test_encrypt_long_string(self) -> None:
        """加密超长字符串（>1MB）"""
        cipher = Cipher(b"azp53h0kft7qi78q", b"1g3qqdh4jvbskb9x")
        text = "A" * 2_000_000
        assert cipher.decrypt(cipher.encrypt(text)) == text

    def test_different_keys_produce_different_ciphertext(self) -> None:
        """不同密钥产生不同密文"""
        iv = b"1g3qqdh4jvbskb9x"
        c1 = Cipher(b"azp53h0kft7qi78q", iv)
        c2 = Cipher(b"7q9oko0vqb3la20r", iv)
        assert c1.encrypt("test") != c2.encrypt("test")

    def test_invalid_key_length_raises(self) -> None:
        """密钥长度非 16 字节抛 ZhsError"""
        from zhs.exceptions import ZhsError

        with pytest.raises(ZhsError):
            Cipher(b"short", b"1g3qqdh4jvbskb9x")


class TestEncodeEv:
    def test_returns_string(self) -> None:
        """encode_ev 返回字符串"""
        encoded = encode_ev([100, 200, 300, 0, 1, 22])
        assert isinstance(encoded, str)
        assert len(encoded) > 0

    def test_deterministic(self) -> None:
        """相同输入产生相同输出"""
        data = [0, 1, 22]
        assert encode_ev(data) == encode_ev(data)

    def test_custom_key(self) -> None:
        """自定义密钥产生不同输出"""
        data = [100, 200]
        assert encode_ev(data) != encode_ev(data, key="zhihuishu")

    def test_empty_list(self) -> None:
        """空列表返回空字符串"""
        assert encode_ev([]) == ""

    def test_accepts_string_elements(self) -> None:
        """支持字符串元素（Sequence[int | str]）"""
        encoded = encode_ev([100, "abc", 22])
        assert isinstance(encoded, str)


class TestSignHike:
    def test_known_vector(self) -> None:
        """与已知签名结果对比"""
        params = {
            "uuid": "user-123",
            "courseId": "course-456",
            "fileId": "file-789",
            "studyTotalTime": "100",
            "startDate": "2026-01-01 00:00:00",
            "endDate": "2026-01-01 00:01:40",
            "endWatchTime": "100",
            "startWatchTime": "0",
        }
        salt = "o6xpt3b#Qy$Z"
        # 手动拼接验证顺序
        raw = (
            salt
            + params["uuid"]
            + params["courseId"]
            + params["fileId"]
            + params["studyTotalTime"]
            + params["startDate"]
            + params["endDate"]
            + params["endWatchTime"]
            + params["startWatchTime"]
            + params["uuid"]
        )
        assert sign_hike(params, salt) == md5(raw.encode()).hexdigest()

    def test_missing_fields_use_empty(self) -> None:
        """缺失字段使用空字符串"""
        result = sign_hike({}, "salt")
        assert result == md5(b"salt").hexdigest()


class TestWatchPoint:
    def test_initial_state(self) -> None:
        """初始值 [0, 1]"""
        wp = WatchPoint(init=0)
        result = wp.get()
        assert "0" in result
        assert "1" in result

    def test_gen_formula(self) -> None:
        """gen(time) = time // 5 + 2"""
        assert WatchPoint.gen(100) == 22  # 100 // 5 + 2 = 22
        assert WatchPoint.gen(0) == 2
        assert WatchPoint.gen(9) == 3  # 9 // 5 + 2 = 3

    def test_add_point(self) -> None:
        """add(100) 后包含 gen(100)=22"""
        wp = WatchPoint(init=0)
        wp.add(100)
        assert "22" in wp.get()

    def test_reset(self) -> None:
        """reset 恢复初始状态"""
        wp = WatchPoint(init=0)
        wp.add(100)
        wp.reset(init=0)
        result = wp.get()
        wp2 = WatchPoint(init=0)
        assert result == wp2.get()
```

> **注意**：项目已移除 `decode_ev` 和 `sign_zhidao_ai` 函数，测试中不再包含。

### 4.3 config.py

```python
from zhs.config import (
    AIConfig,
    AppConfig,
    ConfigManager,
    CryptoConfig,
    DisplayConfig,
    ExamConfig,
    HomeworkConfig,
    ProxyConfig,
    QRConfig,
    UrlConfig,
    VideoConfig,
)


class TestCryptoConfig:
    def test_default_values(self) -> None:
        c = CryptoConfig()
        assert c.iv == "1g3qqdh4jvbskb9x"
        assert c.video_key == "azp53h0kft7qi78q"
        assert c.hike_salt == "o6xpt3b#Qy$Z"
        assert c.ai_key == "hw2fdlwcj4cs1mx7"
        assert c.exam_key == "onbfhdyvz8x7otrp"
        assert c.ai_sign_prefix == "8ZflKEagfL"

    def test_key_bytes(self) -> None:
        c = CryptoConfig()
        assert c.key_bytes("video_key") == b"azp53h0kft7qi78q"
        assert c.key_bytes("iv") == b"1g3qqdh4jvbskb9x"


class TestUrlConfig:
    def test_default_values(self) -> None:
        u = UrlConfig()
        assert "zhihuishu.com" in u.base
        assert "passport" in u.passport
        assert u.homework == "https://studentexam-api.zhihuishu.com"
        assert u.exam == "https://studentexamtest.zhihuishu.com"
        assert u.ai_task == "https://kg-run-student.zhihuishu.com"


class TestAppConfig:
    def test_defaults(self) -> None:
        cfg = AppConfig()
        assert cfg.save_cookies is True
        assert cfg.limit == 0
        assert cfg.threshold == 0.91
        assert isinstance(cfg.video, VideoConfig)
        assert isinstance(cfg.homework, HomeworkConfig)
        assert isinstance(cfg.display, DisplayConfig)
        assert isinstance(cfg.proxies, ProxyConfig)
        assert isinstance(cfg.qr, QRConfig)
        assert isinstance(cfg.crypto, CryptoConfig)
        assert isinstance(cfg.urls, UrlConfig)
        assert isinstance(cfg.ai, AIConfig)
        assert isinstance(cfg.exam, ExamConfig)

    def test_video_defaults(self) -> None:
        cfg = AppConfig()
        assert cfg.video.zhidao_speed == 1.5
        assert cfg.video.hike_speed == 1.25
        assert cfg.video.ai_speed == 1.5

    def test_homework_defaults(self) -> None:
        cfg = AppConfig()
        assert cfg.homework.threshold == 100
        assert cfg.homework.max_submit == 0
        assert cfg.homework.ai_homework_threshold == 90

    def test_exam_defaults(self) -> None:
        cfg = AppConfig()
        assert cfg.exam.save_nums == 5
        assert cfg.exam.delay_min == 3.0
        assert cfg.exam.delay_max == 5.0


class TestConfigManager:
    def test_load_nonexistent_returns_defaults(self, tmp_path: Path) -> None:
        """文件不存在时返回默认配置"""
        mgr = ConfigManager(tmp_path / "nonexistent.toml")
        cfg = mgr.load()
        assert isinstance(cfg, AppConfig)

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        """保存后重新加载一致"""
        config_path = tmp_path / "config.toml"
        mgr = ConfigManager(config_path)
        original = AppConfig()
        mgr.save(original)
        loaded = mgr.load()
        assert loaded.save_cookies == original.save_cookies
        assert loaded.video.zhidao_speed == original.video.zhidao_speed

    def test_load_with_nested_sections(self, tmp_path: Path) -> None:
        """加载嵌套 TOML 配置"""
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            """
save_cookies = false
[video]
zhidao_speed = 2.0
[homework]
threshold = 80
[ai]
use_zhidao_ai = false
api_key = "sk-test"
"""
        )
        mgr = ConfigManager(config_path)
        cfg = mgr.load()
        assert cfg.save_cookies is False
        assert cfg.video.zhidao_speed == 2.0
        assert cfg.homework.threshold == 80
        assert cfg.ai.use_zhidao_ai is False
        assert cfg.ai.api_key == "sk-test"

    def test_migrate_legacy_json(self, tmp_path: Path) -> None:
        """旧版 JSON 配置迁移"""
        json_file = tmp_path / "config.json"
        json_file.write_text(
            '{"save_cookies": true, "logLevel": "DEBUG", '
            '"ai": {"openai": {"api_key": "sk-old"}}}'
        )
        toml_path = tmp_path / "config.toml"
        mgr = ConfigManager(toml_path)
        cfg = mgr.migrate(json_file)
        assert cfg.save_cookies is True
        assert cfg.display.log_level == "DEBUG"
        assert cfg.ai.api_key == "sk-old"
```

### 4.4 session.py

```python
import httpx
import pytest
import respx

from zhs.config import AppConfig
from zhs.exceptions import ApiError, CaptchaRequired
from zhs.session import ZhsSession


@pytest.fixture
def config() -> AppConfig:
    return AppConfig()


@pytest.fixture
def session(config: AppConfig) -> ZhsSession:
    return ZhsSession(config)


class TestZhsSessionInit:
    def test_init_no_error(self, config: AppConfig) -> None:
        s = ZhsSession(config)
        assert s is not None

    def test_urls_property(self, session: ZhsSession) -> None:
        assert session.urls.base == "https://onlineservice-api.zhihuishu.com"

    def test_crypto_property(self, session: ZhsSession) -> None:
        assert session.crypto.video_key == "azp53h0kft7qi78q"


class TestCookieUuid:
    def test_uuid_from_caslogc(self, session: ZhsSession) -> None:
        session._cookies.set("CASLOGC", '{"uuid":"test-uuid-123"}', domain="zhihuishu.com")
        session._parse_uuid()
        assert session.uuid == "test-uuid-123"

    def test_uuid_none_when_no_cookies(self, session: ZhsSession) -> None:
        assert session.uuid is None

    def test_exit_record_set(self, session: ZhsSession) -> None:
        """Cookie 设置时自动添加 exitRecod_{uuid}=2"""
        session._cookies.set("CASLOGC", '{"uuid":"abc"}', domain="zhihuishu.com")
        session._parse_uuid()
        cookies_dict = dict(session.cookies)
        assert any("exitRecod" in k for k in cookies_dict)


class TestZhidaoQuery:
    def test_encrypts_data(self, session: ZhsSession) -> None:
        """zhidao_query 自动加密 data + 添加 dateFormate"""
        with respx.mock:
            route = respx.post("https://onlineservice-api.zhihuishu.com/test").mock(
                return_value=httpx.Response(200, json={"code": 0, "data": {}})
            )
            session.zhidao_query("/test", data={"key": "value"})
            assert route.called
            body = route.calls[0].request.content.decode()
            assert "secretStr" in body
            assert "dateFormate" in body

    def test_code_minus_12_raises_captcha(self, session: ZhsSession) -> None:
        """返回码 -12 抛 CaptchaRequired"""
        with respx.mock:
            respx.post("https://onlineservice-api.zhihuishu.com/test").mock(
                return_value=httpx.Response(200, json={"code": -12, "message": "captcha"})
            )
            with pytest.raises(CaptchaRequired):
                session.zhidao_query("/test", data={})

    def test_non_zero_code_raises_api_error(self, session: ZhsSession) -> None:
        """非 0 返回码抛 ApiError"""
        with respx.mock:
            respx.post("https://onlineservice-api.zhihuishu.com/test").mock(
                return_value=httpx.Response(200, json={"code": 500, "message": "error"})
            )
            with pytest.raises(ApiError):
                session.zhidao_query("/test", data={})


class TestHikeQuery:
    def test_adds_timestamp(self, session: ZhsSession) -> None:
        """hike_query 自动添加 _ 时间戳"""
        with respx.mock:
            route = respx.get("https://hike.zhihuishu.com/test").mock(
                return_value=httpx.Response(200, json={"status": 200, "data": {}})
            )
            session.hike_query("/test", data={}, method="GET")
            assert "_" in str(route.calls[0].request.url)

    def test_with_signature(self, session: ZhsSession) -> None:
        """hike_query sig=True 时自动签名"""
        with respx.mock:
            route = respx.get("https://hike.zhihuishu.com/test").mock(
                return_value=httpx.Response(200, json={"status": 200, "data": {}})
            )
            session.hike_query("/test", data={}, sig=True, method="GET")
            assert "signature" in str(route.calls[0].request.url)


class TestAiExamQuery:
    def test_uses_exam_key(self, session: ZhsSession) -> None:
        """ai_exam_query 使用 exam_key 加密 + dateFormate"""
        with respx.mock:
            route = respx.post("https://studentexamtest.zhihuishu.com/test").mock(
                return_value=httpx.Response(200, json={"code": 0, "data": {}})
            )
            session.ai_exam_query("/test", data={"key": "value"})
            assert route.called
            body = route.calls[0].request.content.decode()
            assert "secretStr" in body
            assert "dateFormate" in body


class TestAiTaskQuery:
    def test_uses_ai_key(self, session: ZhsSession) -> None:
        """ai_task_query 使用 ai_key 加密"""
        with respx.mock:
            route = respx.post("https://kg-run-student.zhihuishu.com/test").mock(
                return_value=httpx.Response(200, json={"code": 200, "data": {}})
            )
            session.ai_task_query("/test", data={})
            assert route.called


class TestHomeworkQuery:
    def test_no_dateformate(self, session: ZhsSession) -> None:
        """homework_query 使用 exam_key 但不发送 dateFormate"""
        with respx.mock:
            route = respx.post("https://studentexam-api.zhihuishu.com/test").mock(
                return_value=httpx.Response(200, json={"status": "200", "data": {}})
            )
            session.homework_query("/test", data={})
            assert route.called
            body = route.calls[0].request.content.decode()
            assert "secretStr" in body
            # homework_query 不发送 dateFormate（与 zhidao_query/ai_exam_query 不同）

    def test_status_not_200_raises(self, session: ZhsSession) -> None:
        """status != "200" 抛 ApiError"""
        with respx.mock:
            respx.post("https://studentexam-api.zhihuishu.com/test").mock(
                return_value=httpx.Response(200, json={"status": "500", "message": "err"})
            )
            with pytest.raises(ApiError):
                session.homework_query("/test", data={})
```

### 4.5 login.py

```python
class TestLoginManager:
    def test_qr_login_polling(self, session: ZhsSession) -> None:
        """扫码轮询：-1 → 0(仅提示一次) → 1"""
        with respx.mock:
            call_count = 0

            def qr_status_side_effect(request):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return httpx.Response(200, json={"status": -1})
                elif call_count == 2:
                    return httpx.Response(200, json={"status": 0})
                else:
                    return httpx.Response(
                        200, json={"status": 1, "oncePassword": "otp"}
                    )

            # ... 验证轮询逻辑

    def test_qr_expired_retries(self, session: ZhsSession) -> None:
        """扫码 status=2 过期 → 递归重试（_max_retries 防止无限递归）"""

    def test_cookie_restore(self, session: ZhsSession, tmp_path: Path) -> None:
        """Cookie 恢复登录"""
```

### 4.6 zhidao/video.py

```python
class TestZhidaoVideoPlayer:
    def test_play_video_already_done(self) -> None:
        """已看完视频 → 跳过（end_threshold 检查）"""

    def test_played_time_capped_at_end_time(self) -> None:
        """played_time = min(played_time + speed, end_time)"""
        played_time = 95
        speed = 1.5
        end_time = 100
        assert min(played_time + speed, end_time) == 96.5

        played_time = 99
        assert min(played_time + speed, end_time) == 100  # 截断

    def test_random_pause_no_progress(self) -> None:
        """随机暂停时 played_time = last_submit（不前进）"""

    def test_report_v2_initial_format(self) -> None:
        """saveDatabaseIntervalTimeV2 initial=True 格式"""

    def test_report_v2_regular_format(self) -> None:
        """saveDatabaseIntervalTimeV2 initial=False 格式（ewssw/sdsew/zwsds）"""

    def test_watch_video_uses_independent_client(self) -> None:
        """_watch_video 使用独立 httpx.Client（不共享 session cookies）"""

    def test_watch_video_daemon_thread(self) -> None:
        """_watch_video 线程 daemon=True"""

    def test_answer_delay_mechanism(self) -> None:
        """弹窗答题 answer_delay=2 递减"""
```

### 4.7 hike/video.py

```python
class TestHikeVideoPlayer:
    def test_traverse_video_type(self) -> None:
        """data_type=3 → play_video"""

    def test_traverse_none_with_file_id(self) -> None:
        """data_type=None + file_id → play_file"""

    def test_traverse_none_without_file_id(self) -> None:
        """data_type=None + 无 file_id → 跳过"""

    def test_traverse_unknown_type_with_file_id(self) -> None:
        """非标准 data_type + file_id → play_file"""

    def test_traverse_unknown_type_without_file_id(self) -> None:
        """非标准 data_type + 无 file_id → 跳过 + 日志"""

    def test_play_file_catches_key_error(self) -> None:
        """play_file try/except 防护 KeyError"""

    def test_save_stu_study_record_overwrites_time(self) -> None:
        """saveStuStudyRecord 返回值覆盖 played_time"""

    def test_study_time_none_defaults_to_zero(self) -> None:
        """studyTime 为 None 时默认 0"""

    def test_default_speed(self) -> None:
        """默认速度 1.25"""
```

### 4.8 zhidao/homework/ 子包

#### 4.8.1 homework/test_models.py

```python
class TestHomeworkItem:
    def test_from_api_json(self) -> None:
        """从 API JSON 构建 HomeworkItem（alias 映射）"""

    def test_optional_fields_default_none(self) -> None:
        """可选字段默认 None"""


class TestHomeworkQuestion:
    def test_question_type_mapping(self) -> None:
        """questionType 字段映射到 HomeworkQuestionType"""

    def test_options_list(self) -> None:
        """questionOptions 列表正确解析"""
```

#### 4.8.2 homework/test_scanner.py

```python
class TestHomeworkScanner:
    def test_scan_homework_returns_list(self, mock_session) -> None:
        """scan_homework 返回 HomeworkItem 列表"""

    def test_filter_pending_excludes_done(self) -> None:
        """filter_pending 排除已完成作业（state=2 或 score 达标）"""

    def test_pagination(self) -> None:
        """分页扫描（page_size 配置）"""
```

#### 4.8.3 homework/test_worker.py

```python
class TestHomeworkWorker:
    def test_run_homework_returns_score_rate(self) -> None:
        """run_homework 返回得分率（0.0-100.0）"""

    def test_strip_html(self) -> None:
        """_strip_html 去除 HTML 标签"""
        from zhs.zhidao.homework.worker import _strip_html
        assert _strip_html("<p>hello</p>") == "hello"

    def test_slider_verification_raises(self) -> None:
        """遇到滑块验证抛 SliderVerificationRequired"""

    def test_threshold_reached_no_redo(self) -> None:
        """达标后不再重做"""

    def test_max_submit_limit(self) -> None:
        """达到 max_submit 次数后停止"""
```

#### 4.8.4 homework/test_analyzer.py

```python
class TestHomeworkAnalyzer:
    def test_analyze_question_returns_answer(self) -> None:
        """analyze 返回答案"""

    def test_parse_choice_answer(self) -> None:
        """解析选择题答案"""

    def test_parse_fill_blank_answer(self) -> None:
        """解析填空题答案"""
```

#### 4.8.5 homework/test_cache.py

```python
class TestHomeworkCache:
    def test_save_and_load(self, tmp_path) -> None:
        """保存后加载一致"""

    def test_cache_miss_returns_none(self, tmp_path) -> None:
        """缓存未命中返回 None"""
```

### 4.9 ai/video.py

```python
class TestAiVideoPlayer:
    def test_play_video_speed_doubled(self) -> None:
        """AI 视频播放速度 *2"""

    def test_watch_interval_2s(self) -> None:
        """_watch_video 间隔 2 秒"""

    def test_ai_query_uses_ai_key(self) -> None:
        """_ai_query 使用 zhidao_query + ai_key"""

    def test_watch_video_uses_independent_client(self) -> None:
        """_watch_video 使用独立 httpx.Client + daemon 线程"""
```

### 4.10 ai/homework.py（HomeworkCtx）

```python
class TestHomeworkCtx:
    def test_init(self, mock_session, ai_config) -> None:
        """HomeworkCtx 初始化"""
        from zhs.ai.homework import HomeworkCtx

        ctx = HomeworkCtx(
            session=mock_session,
            course_id="1001",
            class_id="2001",
            ai_config=ai_config,
        )
        assert ctx._course_id == "1001"

    def test_heartbeat_daemon_thread(self) -> None:
        """心跳使用 daemon 线程"""

    def test_stopped_flag_exits_heartbeat(self) -> None:
        """_stopped 标志退出心跳循环"""

    def test_sequential_processing(self) -> None:
        """顺序处理题目（不并发），每题 sleep delay_min-delay_max"""

    def test_save_answer_separator(self) -> None:
        """_save_answer 用 #@# 分隔选项 ID"""
        answers = ["opt1", "opt2", "opt3"]
        assert "#@#".join(answers) == "opt1#@#opt2#@#opt3"

    def test_uses_zhidao_ai_provider_by_default(self) -> None:
        """默认使用 ZhidaoAIProvider（use_zhidao_ai=True）"""

    def test_uses_openai_provider_when_configured(self) -> None:
        """use_zhidao_ai=False 时使用 OpenAIProvider"""
```

### 4.11 ai/exam.py（ExamCtx）

```python
class TestExamCtx:
    def test_basic_init(self, exam_ctx) -> None:
        """基本初始化"""
        assert exam_ctx._course_id == "7123456789012345678"
        assert exam_ctx._class_id == "523456"

    def test_save_nums_from_config(self, exam_ctx) -> None:
        """save_nums 从 ExamConfig 获取"""
        assert exam_ctx._save_nums == 2

    def test_heartbeat_thread_attribute(self, exam_ctx) -> None:
        """心跳线程属性初始化为 None"""
        assert exam_ctx._heartbeat_thread is None

    def test_stopped_flag(self, exam_ctx) -> None:
        """stopped 标志初始化为 False"""
        assert exam_ctx._stopped is False

    def test_batch_save_every_save_nums(self) -> None:
        """每 save_nums 题保存一次（saveBatchAnswer）"""

    def test_fill_answer_separator(self) -> None:
        """填空题答案用 / 分隔（与 HomeworkCtx 的 #@# 不同）"""
        answers = ["答案1", "答案2"]
        assert "/".join(answers) == "答案1/答案2"

    def test_tasklist_uses_ai_key(self) -> None:
        """taskList 使用 ai_key 加密（其余用 exam_key）"""

    def test_heartbeat_update_user_used_time(self) -> None:
        """心跳调用 updateUserUsedTime"""

    def test_submit_exam_course_type(self) -> None:
        """_submit_exam 含 courseType=8"""

    def test_fewer_than_two_options(self) -> None:
        """选项少于 2 个且非填空 → 选第一个"""

    def test_exam_retry_on_api_failure(self) -> None:
        """API 失败 3 次重试"""
```

> **HomeworkCtx vs ExamCtx 关键差异**：
>
> | 特性 | HomeworkCtx | ExamCtx |
> |------|-------------|---------|
> | 加密密钥 | exam_key | taskList 用 ai_key，其余 exam_key |
> | 答案分隔符 | `#@#` | `/`（填空题） |
> | 保存方式 | 单题保存 | 批量保存（save_nums 题/批） |
> | 心跳方法 | updateUserUsedTime | updateUserUsedTime |
> | dateFormate | 不发送 | 发送 |

### 4.12 ai/ppt.py

```python
class TestPptConverter:
    def test_convert_full_flow(self) -> None:
        """完整流程：download → upload → extract → delete_remote → cleanup_local"""

    def test_cleanup_local_deletes_file(self, tmp_path) -> None:
        """_cleanup_local 删除临时文件"""
        test_file = tmp_path / "test.pptx"
        test_file.write_bytes(b"fake ppt content")
        converter = PptConverter(api_key="test", cleanup_local=True)
        converter._cleanup_local(test_file)
        assert not test_file.exists()

    def test_cleanup_local_disabled(self, tmp_path) -> None:
        """cleanup_local=False 保留文件"""
        test_file = tmp_path / "test.pptx"
        test_file.write_bytes(b"fake ppt content")
        converter = PptConverter(api_key="test", cleanup_local=False)
        converter._cleanup_local(test_file)
        assert test_file.exists()

    def test_extract_json_parse_priority(self) -> None:
        """_extract 先尝试 JSON 解析"""

    def test_should_cleanup_local_attribute(self) -> None:
        """_should_cleanup_local 属性（避免与方法 _cleanup_local 冲突）"""
```

### 4.13 llm/prompts.py

```python
class TestPrompts:
    def test_choice_prompt_contains_answer_marker(self) -> None:
        """选择题 Prompt 包含 ```answer``` 标记"""
        prompt = build_choice_prompt(question="...", options=[...])
        assert "```answer" in prompt

    def test_fill_blank_prompt_contains_answer_marker(self) -> None:
        """填空题 Prompt 包含 ```answer``` 标记"""

    def test_parse_choice_answer_json(self) -> None:
        """正常 JSON 格式解析"""
        completion = '```answer\n[{"id": 1, "content": "A"}, {"id": 3, "content": "C"}]\n```'
        result = parse_choice_answer(completion)
        assert result == [1, 3]

    def test_parse_choice_answer_literal_eval(self) -> None:
        """异常格式 → ast.literal_eval 兜底"""
        completion = "```answer\n[{'id': 1, 'content': 'A'}]\n```"
        result = parse_choice_answer(completion)
        assert result == [1]

    def test_parse_fill_blank_answer(self) -> None:
        """填空题按行提取"""
        completion = "```answer\n答案1\n答案2\n```"
        result = parse_fill_blank_answer(completion)
        assert result == ["答案1", "答案2"]

    def test_parse_fill_blank_empty(self) -> None:
        """填空题空输出"""
        result = parse_fill_blank_answer("```answer\n```")
        assert result == []

    def test_truncate_prompt(self) -> None:
        """_truncate_prompt 超过 max_token 截断"""
```

### 4.14 cli/test_main.py

```python
from typer.testing import CliRunner
from zhs.__main__ import app

runner = CliRunner()


class TestCLI:
    def test_help(self) -> None:
        """zhs --help 不报错"""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0

    def test_init_command(self) -> None:
        """zhs init 不报错"""

    def test_play_command_routes_zhidao(self) -> None:
        """zhs play -c ABC123 → 路由到知到"""

    def test_play_command_routes_hike(self) -> None:
        """zhs play -c 12345 → 路由到 Hike"""

    def test_play_command_type_override(self) -> None:
        """zhs play -c 12345 --type zhidao 显式指定"""

    def test_homework_command(self) -> None:
        """zhs homework -c ABC123"""

    def test_exam_command_requires_ai(self) -> None:
        """zhs exam 无 --type ai 或 --ai-course → 报错"""

    def test_fetch_command(self) -> None:
        """zhs fetch 不报错"""

    def test_cli_overrides_config(self) -> None:
        """CLI 参数覆盖 config 值（如 -s 覆盖 video speed）"""
```

### 4.15 logger.py

```python
import re
from pathlib import Path
from loguru import logger
from zhs.config import AppConfig
from zhs.logger import _SENSITIVE_PATTERNS, get_log_dir, setup_logging


class TestSetupLogging:
    def test_removes_default_sink(self) -> None:
        """setup_logging 移除 loguru 默认 sink"""
        config = AppConfig()
        setup_logging(config)
        assert 0 not in logger._core.handlers

    def test_registers_stderr_sink(self) -> None:
        """注册 stderr sink，级别由 config.display.log_level 控制"""

    def test_registers_file_sink(self) -> None:
        """注册文件 sink，始终 DEBUG 级别"""

    def test_file_sink_rotation_config(self) -> None:
        """文件 sink 配置了轮转（10MB）和保留（7天）+ zip 压缩"""

    def test_idempotent(self) -> None:
        """重复调用 setup_logging 不会重复注册 sink（_initialized 标志）"""
        config = AppConfig()
        setup_logging(config)
        count1 = len(logger._core.handlers)
        setup_logging(config)
        count2 = len(logger._core.handlers)
        assert count1 == count2

    def test_log_level_case_insensitive(self) -> None:
        """log_level 大小写不敏感"""


class TestGetLogDir:
    def test_returns_path_under_data_dir(self) -> None:
        """日志目录在 data_dir/logs/ 下"""
        log_dir = get_log_dir()
        assert log_dir.name == "logs"
        assert "zhs" in str(log_dir).lower()

    def test_creates_directory(self) -> None:
        """日志目录不存在时自动创建"""
        log_dir = get_log_dir()
        assert log_dir.exists()


class TestSensitiveFilter:
    """_sensitive_filter 基于 loguru filter 机制（非 patcher）"""

    def test_caslogc_filtered(self) -> None:
        """CASLOGC 值被脱敏"""
        for pattern in _SENSITIVE_PATTERNS:
            result = pattern.sub(r"\1***", "CASLOGC=%7B%22uuid%22%7D")
            if "CASLOGC" in result:
                assert "***" in result

    def test_token_filtered(self) -> None:
        """token 值被脱敏"""
        for pattern in _SENSITIVE_PATTERNS:
            result = pattern.sub(r"\1***", "token=abc123def")
            if "token" in result:
                assert "***" in result

    def test_password_filtered(self) -> None:
        """password 值被脱敏"""
        for pattern in _SENSITIVE_PATTERNS:
            result = pattern.sub(r"\1***", "password=mysecret")
            if "password" in result:
                assert "***" in result

    def test_apikey_filtered(self) -> None:
        """apiKey 值被脱敏"""
        for pattern in _SENSITIVE_PATTERNS:
            result = pattern.sub(r"\1***", "apiKey=sk-xxxx")
            if "apiKey" in result:
                assert "***" in result

    def test_authorization_bearer_filtered(self) -> None:
        """Authorization Bearer token 被脱敏"""
        for pattern in _SENSITIVE_PATTERNS:
            result = pattern.sub(r"\1***", "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9")
            if "Authorization" in result or "Bearer" in result:
                assert "***" in result

    def test_normal_text_unchanged(self) -> None:
        """普通文本不被脱敏"""
        text = "登录成功: uuid=Xe6arnRO"
        for pattern in _SENSITIVE_PATTERNS:
            text = pattern.sub(r"\1***", text)
        assert text == "登录成功: uuid=Xe6arnRO"
```

---

## 5. 测试数据管理

### 5.1 加解密向量

由于 AES-CBC 是确定性加密（相同 key+iv+plaintext → 相同 ciphertext），
测试中直接用 `cipher.encrypt(plaintext)` 生成密文，再用 `cipher.decrypt(ciphertext)` 验证对称性即可，
无需维护外部向量文件。

### 5.2 Hike 签名向量

`sign_hike` 是 MD5 摘要，确定性函数，测试中直接拼接原始字符串验证：

```python
raw = salt + uuid + courseId + ... + uuid
assert sign_hike(params, salt) == md5(raw.encode()).hexdigest()
```

### 5.3 API 响应快照

集成测试（`tests/integration/`）从真实 API 捕获响应，
单元测试中通过 `respx.mock` 直接构造响应 JSON，无需外部快照文件。

---

## 6. 运行命令

```bash
# 运行全部测试（默认跳过 integration 标记）
uv run pytest

# 仅运行指定模块
uv run pytest tests/test_crypto.py -v

# 运行并显示打印
uv run pytest -s tests/test_session.py

# 运行集成测试（需真实 API + 扫码登录）
uv run pytest -m integration tests/integration/ -v

# 跳过需要扫码的集成测试
uv run pytest -m "integration and not manual_login" tests/integration/

# 查看覆盖率
uv run pytest --cov=zhs --cov-report=html
```

### 6.1 覆盖率目标

| 模块 | 目标覆盖率 | 说明 |
|------|-----------|------|
| crypto.py | 95% | 纯函数，易于测试 |
| config.py | 90% | 文件 I/O + 迁移逻辑 |
| session.py | 85% | 依赖 HTTP Mock |
| login.py | 80% | 多分支流程 |
| zhidao/video.py | 75% | 复杂主循环 |
| hike/video.py | 75% | 资源树遍历 |
| zhidao/homework/ | 80% | 作业扫描/做题/缓存 |
| ai/video.py | 75% | AI 视频播放 |
| ai/homework.py | 80% | 同步作业处理 |
| ai/exam.py | 80% | 同步考试处理 |
| llm/ | 85% | Prompt + 解析 |
| cli/ | 70% | 集成测试为主 |

---

## 7. CI 集成

```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install -e ".[dev]"
      - run: ruff check src/ tests/
      - run: ruff format --check src/ tests/
      - run: mypy src/ tests/
      - run: pytest  # 默认跳过 integration 标记
```

---

## 8. 测试约束（强约束）

1. **禁止 `@respx.mock` 装饰器**：必须用 `with respx.mock:` 上下文管理器
2. **禁止 `AsyncMock`**：项目已同步化，使用 `MagicMock`
3. **禁止 `@pytest.mark.asyncio`**：项目已移除 `pytest-asyncio` 依赖
4. **禁止 `assert True` 占位测试**：必须有实际断言
5. **禁止 `except Exception: pass`**：至少 `logger.error`
6. **禁止测试中硬编码密钥**：从 `CryptoConfig` 获取
7. **集成测试必须标记 `@pytest.mark.integration`**：默认跳过
8. **fixture 中 Mock 生命周期必须覆盖测试用例**：用 `with + yield`
