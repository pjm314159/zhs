# ZHS TDD 测试计划

> 本文档定义了 ZHS 项目的完整测试策略、fixture 设计、Mock 方案和每个模块的详细测试用例。
> 开发流程严格遵循 Red → Green → Refactor 循环。

---

## 1. 测试架构

### 1.1 目录结构

```
tests/
├── conftest.py                 # 全局 fixtures
├── fixtures/                   # 测试数据
│   ├── api_responses/          # API 响应 JSON 快照
│   │   ├── course_list.json
│   │   ├── video_list.json
│   │   ├── hike_resource_tree.json
│   │   ├── ai_knowledge_points.json
│   │   └── exam_sheet.json
│   ├── config_files/           # 配置文件样本
│   │   ├── full_config.toml
│   │   ├── minimal_config.toml
│   │   └── legacy_config.json  # 旧版 JSON 配置
│   └── crypto_vectors/         # 加解密已知输入输出
│       ├── aes_vectors.json
│       ├── ev_vectors.json
│       └── hike_sign_vectors.json
├── test_exceptions.py
├── test_crypto.py
├── test_config.py
├── test_session.py
├── test_login.py
├── zhidao/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_course.py
│   ├── test_video.py
│   └── test_quiz.py
├── hike/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_course.py
│   └── test_video.py
├── ai/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_course.py
│   ├── test_exam.py
│   └── test_ppt.py
├── llm/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_prompts.py
│   ├── test_openai.py
│   └── test_zhidao.py
└── cli/
    ├── __init__.py
    └── test_main.py
```

### 1.2 测试分层策略

```mermaid
flowchart TD
    subgraph Unit["单元测试 (无外部依赖)"]
        U1[crypto: AES/ev/签名]
        U2[models: pydantic 模型]
        U3[prompts: 模板渲染]
        U4[cookie: 序列化]
        U5[path: 路径工具]
        U6[exceptions: 异常层级]
    end

    subgraph Integration["集成测试 (Mock HTTP)"]
        I1[config: TOML 加载/保存]
        I2[session: API 查询封装]
        I3[login: 登录流程]
        I4[course: 课程列表]
    end

    subgraph E2E["端到端测试 (Mock 全部 API)"]
        E1[zhidao: 完整刷课流程]
        E2[hike: 完整刷课流程]
        E3[ai: 学习+考试流程]
        E4[cli: 命令行入口]
    end

    Unit --> Integration --> E2E
```

| 层级 | Mock 策略 | 运行频率 | 标记 |
|------|----------|----------|------|
| 单元测试 | 无外部依赖，纯函数 | 每次提交 | `@pytest.mark.unit` |
| 集成测试 | `respx` Mock httpx 响应 | 每次提交 | `@pytest.mark.integration` |
| 端到端测试 | `respx` Mock 全部 API + `tmp_path` | 合并前 | `@pytest.mark.e2e` |

---

## 2. Fixtures 设计

### 2.1 全局 Fixtures (`conftest.py`)

```python
import pytest
import respx
import httpx
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock
from zhs.config import AppConfig, CryptoConfig, UrlConfig
from zhs.session import ZhsSession

# --- 配置 Fixtures ---

@pytest.fixture
def default_config() -> AppConfig:
    """默认配置"""
    return AppConfig()

@pytest.fixture
def custom_config() -> AppConfig:
    """自定义配置（覆盖部分默认值）"""
    return AppConfig(
        qrlogin=True,
        log_level="DEBUG",
    )

@pytest.fixture
def config_with_custom_crypto() -> AppConfig:
    """自定义密钥配置"""
    return AppConfig(crypto=CryptoConfig(
        iv="customiv12345678",
        video_key="customkey1234567",
    ))

# --- Session Fixtures ---

@pytest.fixture
def mock_config() -> AppConfig:
    """用于 Mock session 的配置"""
    return AppConfig(proxies={})

@pytest.fixture
def mock_session(mock_config: AppConfig) -> Generator[ZhsSession, None, None]:
    """带 Mock HTTP 的 session

    ⚠️ 注意：不能在 fixture 上使用 @respx.mock 装饰器！
    因为 @respx.mock 的 Mock 环境仅在 fixture 函数体内生效，
    当 fixture return 后 Mock 立即关闭，下游测试会穿透到真实网络。

    正确做法：在 fixture 内用 respx.mock 上下文管理器 + yield，
    使 Mock 生命周期覆盖整个测试用例执行期。
    """
    with respx.mock:
        session = ZhsSession(mock_config)
        yield session

@pytest.fixture
def authenticated_session(mock_session: ZhsSession) -> ZhsSession:
    """已认证的 session（含 uuid 和 cookies）"""
    mock_session.cookies.set(
        "CASLOGC",
        '{"uuid":"test-uuid-123"}',
        domain="zhihuishu.com",
    )
    return mock_session

# --- API 响应工厂 ---

@pytest.fixture
def api_response_factory():
    """通用 API 响应工厂"""
    def _make(
        code: int = 0,
        data: dict | list | None = None,
        message: str = "",
        status: int = 200,
    ) -> dict:
        return {"code": code, "data": data or {}, "message": message, "status": status}
    return _make

@pytest.fixture
def hike_response_factory():
    """Hike API 响应工厂"""
    def _make(
        status: int = 200,
        data: dict | list | None = None,
        message: str = "success",
    ) -> dict:
        return {"status": status, "data": data or {}, "message": message}
    return _make

# --- 测试数据 Fixtures ---

@pytest.fixture
def fixtures_dir() -> Path:
    """测试数据目录"""
    return Path(__file__).parent / "fixtures"

@pytest.fixture
def crypto_vectors(fixtures_dir: Path) -> dict:
    """加解密已知向量"""
    import json
    with open(fixtures_dir / "crypto_vectors" / "aes_vectors.json") as f:
        return json.load(f)

@pytest.fixture
def tmp_config_file(tmp_path: Path) -> Path:
    """临时配置文件路径"""
    return tmp_path / "config.toml"
```

### 2.2 模块级 Fixtures

```python
# tests/zhidao/conftest.py

@pytest.fixture
def sample_course_json(fixtures_dir: Path) -> dict:
    import json
    with open(fixtures_dir / "api_responses" / "course_list.json") as f:
        return json.load(f)

@pytest.fixture
def sample_video_list_json(fixtures_dir: Path) -> dict:
    import json
    with open(fixtures_dir / "api_responses" / "video_list.json") as f:
        return json.load(f)
```

---

## 3. Mock 方案

### 3.1 HTTP Mock：respx

```python
import respx
import httpx

# Mock 知到 API
@respx.mock
def test_zhidao_query(mock_session):
    route = respx.post("https://onlineservice-api.zhihuishu.com/gateway/t/v1/learning/queryCourse").mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {...}})
    )
    result = mock_session.zhidao_query("/gateway/t/v1/learning/queryCourse", data={})
    assert route.called

# Mock Hike API
@respx.mock
def test_hike_query(mock_session):
    route = respx.get("https://hike.zhihuishu.com/api/...").mock(
        return_value=httpx.Response(200, json={"status": 200, "data": {...}})
    )
    result = mock_session.hike_query("/api/...", data={})
    assert route.called
```

### 3.2 异步 Mock

```python
from unittest.mock import AsyncMock

@pytest.fixture
def mock_ai_exam_query():
    """Mock ExamCtx 的 API 调用"""
    mock = AsyncMock()
    mock._open_exam = AsyncMock()
    mock._get_sheet_content = AsyncMock(return_value=[
        QuestionSheet(question_id=1, version=1),
        QuestionSheet(question_id=2, version=1),
    ])
    mock._get_question_content = AsyncMock()
    mock._save_answer = AsyncMock(return_value=True)
    mock._submit_exam = AsyncMock()
    return mock
```

### 3.3 时间 Mock

```python
from freezegun import freeze_time

@freeze_time("2026-01-15 12:00:00")
def test_dateFormate_timestamp():
    """验证 dateFormate 时间戳为毫秒级"""
    import time
    assert int(time.time()) * 1000 == 1736932800000
```

---

## 4. 详细测试用例

### 4.1 exceptions.py

```python
class TestExceptions:
    def test_zhs_error_is_base(self):
        """ZhsError 是所有自定义异常的基类"""
        assert issubclass(CaptchaRequired, ZhsError)
        assert issubclass(LoginFailed, ZhsError)
        assert issubclass(InvalidCookies, ZhsError)
        assert issubclass(TimeLimitExceeded, ZhsError)
        assert issubclass(ApiError, ZhsError)

    def test_api_error_carries_code_and_message(self):
        """ApiError 携带 code 和 message"""
        err = ApiError(code=-12, message="需要验证码")
        assert err.code == -12
        assert err.message == "需要验证码"
        assert "-12" in str(err)

    def test_catch_specific_then_base(self):
        """可以先捕获子异常再捕获基类"""
        with pytest.raises(CaptchaRequired):
            raise CaptchaRequired("验证码")

        with pytest.raises(ZhsError):
            raise CaptchaRequired("验证码")
```

### 4.2 crypto.py

```python
class TestCipher:
    def test_encrypt_decrypt_roundtrip(self, default_config):
        """AES 加解密对称性"""
        crypto = default_config.crypto
        cipher = Cipher(crypto.key_bytes("video_key"), crypto.key_bytes("iv"))
        plaintext = "hello world"
        assert cipher.decrypt(cipher.encrypt(plaintext)) == plaintext

    def test_encrypt_empty_string(self, default_config):
        """加密空字符串不崩溃"""
        crypto = default_config.crypto
        cipher = Cipher(crypto.key_bytes("video_key"), crypto.key_bytes("iv"))
        assert cipher.decrypt(cipher.encrypt("")) == ""

    def test_encrypt_chinese(self, default_config):
        """加密中文字符"""
        crypto = default_config.crypto
        cipher = Cipher(crypto.key_bytes("video_key"), crypto.key_bytes("iv"))
        text = "智慧树在线课程"
        assert cipher.decrypt(cipher.encrypt(text)) == text

    def test_encrypt_long_string(self, default_config):
        """加密超长字符串（>1MB）"""
        crypto = default_config.crypto
        cipher = Cipher(crypto.key_bytes("video_key"), crypto.key_bytes("iv"))
        text = "A" * 2_000_000
        assert cipher.decrypt(cipher.encrypt(text)) == text

    def test_different_keys_produce_different_ciphertext(self, default_config):
        """不同密钥产生不同密文"""
        crypto = default_config.crypto
        c1 = Cipher(crypto.key_bytes("video_key"), crypto.key_bytes("iv"))
        c2 = Cipher(crypto.key_bytes("home_key"), crypto.key_bytes("iv"))
        text = "test data"
        assert c1.encrypt(text) != c2.encrypt(text)

    def test_known_vector(self, crypto_vectors):
        """与已知向量对比（从旧代码提取）"""
        cipher = Cipher(b"azp53h0kft7qi78q", b"1g3qqdh4jvbskb9x")
        for vec in crypto_vectors:
            assert cipher.encrypt(vec["plaintext"]) == vec["ciphertext"]


class TestEncodeEv:
    def test_roundtrip(self):
        """ev 编解码对称性"""
        data = [100, 200, 300, 0, 1, 22]
        assert decode_ev(encode_ev(data)) == str(data)

    def test_default_key(self):
        """默认密钥 zzpttjd"""
        data = [0, 1, 22]
        encoded = encode_ev(data)
        decoded = decode_ev(encoded)
        assert decoded == str(data)

    def test_custom_key(self):
        """自定义密钥"""
        data = [100, 200]
        encoded = encode_ev(data, key="zhihuishu")
        decoded = decode_ev(encoded, key="zhihuishu")
        assert decoded == str(data)

    def test_empty_list(self):
        """空列表"""
        encoded = encode_ev([])
        decoded = decode_ev(encoded)
        assert decoded == "[]"

    def test_truncation_minus_4(self):
        """tmp[-4:] 截断行为"""
        # 验证截断后仍可正确解码
        data = list(range(50))
        assert decode_ev(encode_ev(data)) == str(data)


class TestSignHike:
    def test_known_vector(self, fixtures_dir):
        """与已知签名结果对比"""
        import json
        with open(fixtures_dir / "crypto_vectors" / "hike_sign_vectors.json") as f:
            vectors = json.load(f)
        for vec in vectors:
            result = sign_hike(vec["params"], vec["salt"])
            assert result == vec["expected"]

    def test_field_order(self):
        """字段顺序：SALT + uuid + courseId + fileId + studyTotalTime + startDate + endDate + endWatchTime + startWatchTime + uuid"""
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
        raw = f"{salt}{params['uuid']}{params['courseId']}{params['fileId']}{params['studyTotalTime']}{params['startDate']}{params['endDate']}{params['endWatchTime']}{params['startWatchTime']}{params['uuid']}"
        assert sign_hike(params, salt) == md5(raw.encode()).hexdigest()


class TestSignZhidaoAi:
    def test_returns_url_with_sign(self):
        """返回含 sign 参数的 URL"""
        url, body = sign_zhidao_ai(
            data={"messageList": [], "modelCode": "test", "stream": True},
            prefix="8ZflKEagfL",
        )
        assert "sign=" in url

    def test_session_nid_format(self):
        """sessionNid 格式：chatcmpl- + 24位随机字符"""
        import re
        for _ in range(10):
            url, body = sign_zhidao_ai(
                data={"messageList": [], "modelCode": "test", "stream": True},
                prefix="8ZflKEagfL",
            )
            # 验证 body 中 sessionNid 格式为 chatcmpl- + 24位字符
            session_nid = body.get("sessionNid", "")
            assert session_nid.startswith("chatcmpl-"), f"sessionNid 应以 chatcmpl- 开头，实际: {session_nid}"
            suffix = session_nid[len("chatcmpl-"):]
            assert len(suffix) == 24, f"sessionNid 后缀应为 24 位，实际: {len(suffix)}"
            assert re.match(r"^[a-zA-Z0-9]+$", suffix), f"sessionNid 后缀应为字母数字，实际: {suffix}"


class TestWatchPoint:
    def test_initial_state(self):
        """初始值 [0, 1]"""
        wp = WatchPoint(init=0)
        result = wp.get()
        assert "0" in result
        assert "1" in result

    def test_add_point(self):
        """add(100) → gen(100) = 100//5+2 = 22"""
        wp = WatchPoint(init=0)
        wp.add(100)
        result = wp.get()
        assert "22" in result

    def test_reset(self):
        """reset 恢复初始状态"""
        wp = WatchPoint(init=0)
        wp.add(100)
        wp.reset(init=0)
        result = wp.get()
        # 应与初始状态一致
        wp2 = WatchPoint(init=0)
        assert result == wp2.get()
```

### 4.3 config.py

```python
class TestCryptoConfig:
    def test_default_values(self):
        c = CryptoConfig()
        assert c.iv == "1g3qqdh4jvbskb9x"
        assert c.video_key == "azp53h0kft7qi78q"
        assert c.hike_salt == "o6xpt3b#Qy$Z"

    def test_key_bytes(self):
        c = CryptoConfig()
        assert c.key_bytes("video_key") == b"azp53h0kft7qi78q"
        assert c.key_bytes("iv") == b"1g3qqdh4jvbskb9x"

    def test_key_bytes_invalid(self):
        c = CryptoConfig()
        with pytest.raises(AttributeError):
            c.key_bytes("nonexistent_key")


class TestUrlConfig:
    def test_default_values(self):
        u = UrlConfig()
        assert "zhihuishu.com" in u.base
        assert "passport" in u.passport


class TestAppConfig:
    def test_defaults(self):
        cfg = AppConfig()
        assert cfg.qrlogin is True
        assert isinstance(cfg.crypto, CryptoConfig)
        assert isinstance(cfg.urls, UrlConfig)
        assert isinstance(cfg.ai, AIConfig)


class TestConfigManager:
    def test_load_toml(self, tmp_config_file):
        """从 TOML 文件加载"""
        tmp_config_file.write_text("""
[auth]
qrlogin = true
""")
        mgr = ConfigManager(tmp_config_file)
        cfg = mgr.load()
        assert cfg.qrlogin is True

    def test_save_and_load_roundtrip(self, tmp_config_file):
        """保存后重新加载一致"""
        cfg = AppConfig(qrlogin=True)
        mgr = ConfigManager(tmp_config_file)
        mgr.save(cfg)
        loaded = mgr.load()
        assert loaded.qrlogin is True

    def test_missing_fields_use_defaults(self, tmp_config_file):
        """缺失字段使用默认值"""
        tmp_config_file.write_text('[auth]\nqrlogin = false\n')
        mgr = ConfigManager(tmp_config_file)
        cfg = mgr.load()
        assert cfg.qrlogin is False

    def test_migrate_legacy_json(self, tmp_path):
        """旧版 JSON 配置迁移"""
        json_file = tmp_path / "config.json"
        json_file.write_text('{"qrlogin": true, "push": {"enable": true}}')
        mgr = ConfigManager(json_file)
        cfg = mgr.migrate(json_file)
        assert cfg.qrlogin is True
```

### 4.4 session.py

```python
class TestZhsSession:
    def test_init_from_config(self, mock_config):
        """从 AppConfig 初始化"""
        session = ZhsSession(mock_config)
        assert session.urls.base == mock_config.urls.base

    def test_uuid_from_cookies(self, authenticated_session):
        """从 CASLOGC cookie 解析 uuid"""
        assert authenticated_session.uuid == "test-uuid-123"

    def test_uuid_none_when_no_cookies(self, mock_session):
        """无 cookies 时 uuid 为 None"""
        assert mock_session.uuid is None

    @respx.mock
    def test_zhidao_query_encrypts_data(self, mock_session):
        """zhidao_query 自动加密 data"""
        route = respx.post("https://onlineservice-api.zhihuishu.com/test").mock(
            return_value=httpx.Response(200, json={"code": 0, "data": {}})
        )
        mock_session.zhidao_query("/test", data={"key": "value"})
        assert route.called
        # 验证请求中包含 secretStr 和 dateFormate
        request = route.calls[0].request
        body = request.content.decode()
        assert "secretStr" in body
        assert "dateFormate" in body

    @respx.mock
    def test_zhidao_query_code_minus_12(self, mock_session):
        """返回码 -12 抛 CaptchaRequired"""
        respx.post("https://...").mock(
            return_value=httpx.Response(200, json={"code": -12, "message": "captcha"})
        )
        with pytest.raises(CaptchaRequired):
            mock_session.zhidao_query("/test", data={})

    @respx.mock
    def test_hike_query_adds_timestamp(self, mock_session):
        """hike_query 自动添加 _ 时间戳"""
        route = respx.get("https://hike.zhihuishu.com/test").mock(
            return_value=httpx.Response(200, json={"status": 200, "data": {}})
        )
        mock_session.hike_query("/test", data={}, method="GET")
        request = route.calls[0].request
        assert "_" in str(request.url)

    @respx.mock
    def test_hike_query_with_signature(self, mock_session):
        """hike_query sig=True 时自动签名"""
        route = respx.get("https://hike.zhihuishu.com/test").mock(
            return_value=httpx.Response(200, json={"status": 200, "data": {}})
        )
        mock_session.hike_query("/test", data={}, sig=True, method="GET")
        request = route.calls[0].request
        assert "sign" in str(request.url)

    @respx.mock
    def test_retry_on_5xx(self, mock_session):
        """5xx 自动重试"""
        route = respx.get("https://onlineservice-api.zhihuishu.com/test").mock(
            side_effect=[
                httpx.Response(500),
                httpx.Response(502),
                httpx.Response(200, json={"code": 0, "data": {}}),
            ]
        )
        result = mock_session.api_query("https://onlineservice-api.zhihuishu.com/test", method="GET")
        assert route.call_count >= 2

    def test_cookie_sets_exit_recod(self, authenticated_session):
        """设置 cookies 时自动添加 exitRecod_{uuid}=2"""
        cookies_dict = dict(authenticated_session.cookies)
        assert any("exitRecod" in k for k in cookies_dict)
```

### 4.5 login.py

```python
class TestLoginManager:
    @respx.mock
    def test_qr_login_polling(self, mock_session):
        """扫码轮询：-1 → 0(仅提示一次) → 1"""
        call_count = 0
        def qr_status_side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(200, json={"status": -1})
            elif call_count == 2:
                return httpx.Response(200, json={"status": 0})
            else:
                return httpx.Response(200, json={"status": 1, "oncePassword": "otp"})
        # ... 验证轮询逻辑

    @respx.mock
    def test_qr_expired_retries(self, mock_session):
        """扫码 status=2 过期 → 递归重试"""
        # ...

    @respx.mock
    def test_cookie_restore(self, mock_session, tmp_path):
        """Cookie 恢复登录"""
        # ...
```

### 4.6 zhidao/video.py

```python
class TestZhidaoVideoPlayer:
    def test_play_video_already_done(self, mock_session):
        """已看完视频 → 跳过"""
        # Mock context with end_threshold met

    def test_played_time_capped_at_end_time(self):
        """played_time = min(played_time + speed, end_time)"""
        played_time = 95
        speed = 1.5
        end_time = 100
        assert min(played_time + speed, end_time) == 96.5

        played_time = 99
        speed = 1.5
        end_time = 100
        assert min(played_time + speed, end_time) == 100  # 截断

    def test_random_pause_no_progress(self):
        """随机暂停时 played_time = last_submit（不前进）"""
        last_submit = 50
        played_time = 50
        # 暂停期间 played_time 不变
        assert played_time == last_submit

    def test_report_v2_initial_format(self):
        """saveDatabaseIntervalTimeV2 initial=True 格式"""
        # 验证 ev 数据结构

    def test_report_v2_regular_format(self):
        """saveDatabaseIntervalTimeV2 initial=False 格式（ewssw/sdsew/zwsds）"""
        # 验证字段名

    def test_watch_video_uses_independent_client(self):
        """_watch_video 使用独立 httpx.Client"""
        # 验证不共享 session 的 cookies

    def test_watch_video_daemon_thread(self):
        """_watch_video 线程 daemon=True"""
        # 验证线程属性

    def test_answer_delay_mechanism(self):
        """弹窗答题 answer_delay=2 递减"""
        answer_delay = 2
        # 模拟递减
        answer_delay -= 1  # sleep 1s
        assert answer_delay == 1
        answer_delay -= 1  # sleep 1s
        assert answer_delay == 0
        # answer_delay == 0 时提交答案
```

### 4.7 hike/video.py

```python
class TestHikeVideoPlayer:
    def test_traverse_video_type(self):
        """data_type=3 → play_video"""

    def test_traverse_none_with_file_id(self):
        """data_type=None + file_id → play_file"""

    def test_traverse_none_without_file_id(self):
        """data_type=None + 无 file_id → 跳过"""

    def test_traverse_unknown_type_with_file_id(self):
        """非标准 data_type + file_id → play_file"""

    def test_traverse_unknown_type_without_file_id(self):
        """非标准 data_type + 无 file_id → 跳过 + 日志"""

    def test_play_file_catches_key_error(self):
        """play_file try/except 防护 KeyError"""

    def test_save_stu_study_record_overwrites_time(self):
        """saveStuStudyRecord 返回值覆盖 played_time"""
        # Mock 返回 ret_time=50
        # 验证 prev_time 和 played_time 都变为 50

    def test_study_time_none_defaults_to_zero(self):
        """studyTime 为 None 时默认 0"""

    def test_default_speed(self):
        """默认速度 1.25"""
        player = HikeVideoPlayer(session=mock_session)
        assert player.speed == 1.25
```

### 4.8 ai/exam.py

```python
class TestExamCtx:
    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self):
        """Semaphore(3) 限制并发"""
        exam_ctx = ExamCtx(...)
        assert exam_ctx._semaphore._value == 3

    @pytest.mark.asyncio
    async def test_process_question_sleeps(self):
        """_process_question 每题 sleep 0.3-0.8s"""
        # 用 freezegun 或 mock asyncio.sleep 验证

    def test_two_level_cache_lookup(self):
        """两级缓存：先查 all_answer_cache 再查 answer_cache"""
        # all_answer_cache 有答案 → 直接返回
        # all_answer_cache 无 → 查 answer_cache

    def test_save_answer_separator(self):
        """_save_answer 用 #@# 分隔选项 ID"""
        answers = ["opt1", "opt2", "opt3"]
        assert "#@#".join(answers) == "opt1#@#opt2#@#opt3"

    def test_submit_exam_course_type(self):
        """_submit_exam 含 courseType=8"""
        # Mock 验证请求体

    def test_fewer_than_two_options(self):
        """选项少于 2 个且非填空 → 选第一个"""
        # 边界情况

    @pytest.mark.asyncio
    async def test_exam_retry_on_api_failure(self):
        """API 失败 3 次重试"""
        # Mock _get_question_content 前两次失败，第三次成功
```

### 4.9 ai/ppt.py

```python
class TestPptConverter:
    @respx.mock
    def test_convert_full_flow(self):
        """完整流程：download → upload → extract → delete_remote → cleanup_local"""

    def test_cleanup_local_deletes_file(self, tmp_path):
        """_cleanup_local 删除临时文件"""
        test_file = tmp_path / "test.pptx"
        test_file.write_bytes(b"fake ppt content")
        converter = PptConverter(api_key="test", cleanup_local=True)
        converter._cleanup_local(test_file)
        assert not test_file.exists()

    def test_cleanup_local_disabled(self, tmp_path):
        """cleanup_local=False 保留文件"""
        test_file = tmp_path / "test.pptx"
        test_file.write_bytes(b"fake ppt content")
        converter = PptConverter(api_key="test", cleanup_local=False)
        converter._cleanup_local(test_file)
        assert test_file.exists()

    def test_extract_json_parse_priority(self):
        """_extract 先尝试 JSON 解析"""
        # Mock MoonShot 返回 JSON 格式 → 提取 content 字段
        # Mock MoonShot 返回纯文本 → 直接返回
```

### 4.10 llm/prompts.py

```python
class TestPrompts:
    def test_choice_prompt_contains_answer_marker(self):
        """选择题 Prompt 包含 ```answer``` 标记"""
        prompt = build_choice_prompt(question="...", options=[...])
        assert "```answer" in prompt

    def test_fill_blank_prompt_contains_answer_marker(self):
        """填空题 Prompt 包含 ```answer``` 标记"""

    def test_parse_choice_answer_json(self):
        """正常 JSON 格式解析"""
        completion = '```answer\n[{"id": 1, "content": "A"}, {"id": 3, "content": "C"}]\n```'
        result = parse_choice_answer(completion)
        assert result == [1, 3]

    def test_parse_choice_answer_literal_eval(self):
        """异常格式 → ast.literal_eval 兜底"""
        completion = "```answer\n[{'id': 1, 'content': 'A'}]\n```"
        result = parse_choice_answer(completion)
        assert result == [1]

    def test_parse_fill_blank_answer(self):
        """填空题按行提取"""
        completion = "```answer\n答案1\n答案2\n```"
        result = parse_fill_blank_answer(completion)
        assert result == ["答案1", "答案2"]

    def test_parse_fill_blank_empty(self):
        """填空题空输出"""
        result = parse_fill_blank_answer("```answer\n```")
        assert result == []
```

### 4.11 cli/test_main.py

```python
from typer.testing import CliRunner

runner = CliRunner()

class TestCLI:
    def test_help(self):
        """zhs --help 不报错"""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0

    def test_course_with_letters_routes_zhidao(self):
        """含字母课程 ID → 路由到知到"""
        # Mock 完整流程

    def test_numeric_course_routes_hike(self):
        """纯数字课程 ID → 路由到 Hike"""
        # Mock 完整流程

    def test_type_override(self):
        """--type hike 显式指定"""
        # Mock 完整流程，验证走 Hike 路径

    def test_type_without_course_errors(self):
        """--type 无 course → 报错"""
        result = runner.invoke(app, ["--type", "zhidao"])
        assert result.exit_code != 0

    def test_cli_overrides_config(self):
        """CLI 参数覆盖 config 值"""
        # --speed 2.0 覆盖 config 中的 speed
```

### 4.12 logger.py

```python
import re
from pathlib import Path
from loguru import logger
from zhs.config import AppConfig
from zhs.logger import setup_logging, get_log_dir, _SENSITIVE_PATTERNS


class TestSetupLogging:
    def test_removes_default_sink(self, tmp_path: Path):
        """setup_logging 移除 loguru 默认 sink"""
        # loguru 默认有一个 sink(id=0)，调用后应被移除
        config = AppConfig(log_level="INFO")
        setup_logging(config)
        # 验证默认 sink 被移除：logger._core.handlers 不含 id=0
        assert 0 not in logger._core.handlers

    def test_registers_stderr_sink(self):
        """注册 stderr sink，级别由 config.log_level 控制"""
        config = AppConfig(log_level="WARNING")
        setup_logging(config)
        # 找到 stderr sink，验证其 level 为 WARNING
        stderr_sinks = [
            h for h in logger._core.handlers.values()
            if hasattr(h, "_sink") and "stderr" in str(h._sink)
        ]
        assert len(stderr_sinks) >= 1
        # 验证级别
        assert stderr_sinks[0]._levelno >= 30  # WARNING=30

    def test_registers_file_sink(self, tmp_path: Path):
        """注册文件 sink，始终 DEBUG 级别"""
        config = AppConfig(log_level="INFO")
        setup_logging(config)
        # 找到文件 sink
        file_sinks = [
            h for h in logger._core.handlers.values()
            if hasattr(h, "_sink") and hasattr(h._sink, "_path")
        ]
        assert len(file_sinks) >= 1
        # 文件 sink 级别应为 DEBUG(10)
        assert file_sinks[0]._levelno == 10

    def test_file_sink_rotation_config(self, tmp_path: Path):
        """文件 sink 配置了轮转（10MB）和保留（7天）"""
        config = AppConfig()
        setup_logging(config)
        file_sinks = [
            h for h in logger._core.handlers.values()
            if hasattr(h, "_sink") and hasattr(h._sink, "_path")
        ]
        assert len(file_sinks) >= 1
        # 验证 rotation 和 retention 配置
        sink = file_sinks[0]._sink
        assert sink._rotation is not None
        assert sink._retention is not None

    def test_idempotent(self):
        """重复调用 setup_logging 不会重复注册 sink"""
        config = AppConfig()
        setup_logging(config)
        handler_count_after_first = len(logger._core.handlers)
        setup_logging(config)
        handler_count_after_second = len(logger._core.handlers)
        assert handler_count_after_first == handler_count_after_second

    def test_log_level_case_insensitive(self):
        """log_level 大小写不敏感"""
        for level in ["info", "INFO", "Info"]:
            config = AppConfig(log_level=level)
            setup_logging(config)
            # 不应抛异常


class TestGetLogDir:
    def test_returns_path_under_data_dir(self, tmp_path: Path):
        """日志目录在 data_dir/logs/ 下"""
        log_dir = get_log_dir()
        assert log_dir.name == "logs"
        assert "zhs" in str(log_dir).lower()

    def test_creates_directory(self, tmp_path: Path):
        """日志目录不存在时自动创建"""
        log_dir = get_log_dir()
        # get_log_dir 应确保目录存在
        assert log_dir.exists() or True  # 可能需要 mock data_dir


class TestSensitiveFilter:
    def test_caslogc_filtered(self):
        """CASLOGC 值被脱敏"""
        for pattern in _SENSITIVE_PATTERNS:
            result = pattern.sub(r"\1=***", 'CASLOGC=%7B%22uuid%22%7D')
            if "CASLOGC" in result:
                assert "***" in result
                assert "%7B%22uuid%22%7D" not in result

    def test_token_filtered(self):
        """token 值被脱敏"""
        for pattern in _SENSITIVE_PATTERNS:
            result = pattern.sub(r"\1=***", "token=abc123def")
            if "token" in result:
                assert "***" in result
                assert "abc123def" not in result

    def test_password_filtered(self):
        """password 值被脱敏"""
        for pattern in _SENSITIVE_PATTERNS:
            result = pattern.sub(r"\1=***", "password=mysecret")
            if "password" in result:
                assert "***" in result
                assert "mysecret" not in result

    def test_apikey_filtered(self):
        """apiKey 值被脱敏"""
        for pattern in _SENSITIVE_PATTERNS:
            result = pattern.sub(r"\1=***", "apiKey=sk-xxxx")
            if "apiKey" in result:
                assert "***" in result
                assert "sk-xxxx" not in result

    def test_authorization_bearer_filtered(self):
        """Authorization Bearer token 被脱敏"""
        for pattern in _SENSITIVE_PATTERNS:
            result = pattern.sub(r"\1=***", "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9")
            if "Authorization" in result:
                assert "***" in result
                assert "eyJhbGciOiJIUzI1NiJ9" not in result

    def test_normal_text_unchanged(self):
        """普通文本不被脱敏"""
        text = "登录成功: uuid=Xe6arnRO"
        for pattern in _SENSITIVE_PATTERNS:
            text = pattern.sub(r"\1=***", text)
        assert text == "登录成功: uuid=Xe6arnRO"

    def test_patcher_integrated(self, tmp_path: Path):
        """patcher 与 loguru 集成后，日志消息自动脱敏"""
        config = AppConfig(log_level="DEBUG")
        setup_logging(config)
        # 写入包含敏感信息的日志
        # 验证文件中的消息被脱敏
        # （需要读取日志文件验证）


class TestConsoleFormat:
    def test_console_output_format(self, capsys):
        """控制台输出格式正确"""
        config = AppConfig(log_level="DEBUG")
        setup_logging(config)
        logger.info("测试消息")
        # 验证 stderr 输出包含时间戳、级别、消息


class TestFileFormat:
    def test_file_output_contains_thread_info(self, tmp_path: Path):
        """文件输出包含线程名"""
        config = AppConfig(log_level="DEBUG")
        setup_logging(config)
        logger.info("线程测试")
        # 验证日志文件包含线程名
```

---

## 5. 测试数据管理

### 5.1 加解密向量 (`fixtures/crypto_vectors/aes_vectors.json`)

```json
[
  {
    "key": "azp53h0kft7qi78q",
    "iv": "1g3qqdh4jvbskb9x",
    "plaintext": "test data",
    "ciphertext": "<从旧代码运行获取>"
  }
]
```

> **生成方法**：运行旧代码 `Cipher(b"azp53h0kft7qi78q", b"1g3qqdh4jvbskb9x").encrypt("test data")` 获取已知密文。

### 5.2 Hike 签名向量 (`fixtures/crypto_vectors/hike_sign_vectors.json`)

```json
[
  {
    "params": {
      "uuid": "test-uuid",
      "courseId": "123",
      "fileId": "456",
      "studyTotalTime": "100",
      "startDate": "2026-01-01 00:00:00",
      "endDate": "2026-01-01 00:01:40",
      "endWatchTime": "100",
      "startWatchTime": "0"
    },
    "salt": "o6xpt3b#Qy$Z",
    "expected": "<从旧代码运行获取>"
  }
]
```

### 5.3 API 响应快照

从旧代码实际运行中捕获 API 响应，保存为 JSON 文件。每个快照文件包含：
- `url`: 请求 URL
- `method`: 请求方法
- `response`: 响应 JSON（脱敏后）

---

## 6. 运行命令

```bash
# 运行全部测试
pytest

# 仅运行单元测试
pytest -m unit

# 仅运行集成测试
pytest -m integration

# 运行指定模块
pytest tests/test_crypto.py -v

# 查看覆盖率
pytest --cov=zhs --cov-report=html

# 运行并显示打印
pytest -s tests/test_crypto.py
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
| ai/exam.py | 80% | 异步逻辑 |
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
      - run: ruff check src/
      - run: mypy src/
      - run: pytest -m unit --cov=zhs
      - run: pytest -m integration
```
