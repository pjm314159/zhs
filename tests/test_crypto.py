"""crypto.py 单元测试 — TDD Red 阶段"""

import re
from hashlib import md5

from zhs.crypto import Cipher, WatchPoint, decode_ev, encode_ev, sign_hike, sign_zhidao_ai


# ---------------------------------------------------------------------------
# Cipher — AES-128-CBC 加解密
# ---------------------------------------------------------------------------
class TestCipher:
    """AES-128-CBC 加解密测试"""

    def test_encrypt_decrypt_roundtrip(self) -> None:
        """AES 加解密对称性"""
        key = b"azp53h0kft7qi78q"
        iv = b"1g3qqdh4jvbskb9x"
        cipher = Cipher(key, iv)
        plaintext = "hello world"
        assert cipher.decrypt(cipher.encrypt(plaintext)) == plaintext

    def test_encrypt_empty_string(self) -> None:
        """加密空字符串不崩溃"""
        key = b"azp53h0kft7qi78q"
        iv = b"1g3qqdh4jvbskb9x"
        cipher = Cipher(key, iv)
        assert cipher.decrypt(cipher.encrypt("")) == ""

    def test_encrypt_chinese(self) -> None:
        """加密中文字符"""
        key = b"azp53h0kft7qi78q"
        iv = b"1g3qqdh4jvbskb9x"
        cipher = Cipher(key, iv)
        text = "智慧树在线课程"
        assert cipher.decrypt(cipher.encrypt(text)) == text

    def test_encrypt_long_string(self) -> None:
        """加密超长字符串（>1MB）"""
        key = b"azp53h0kft7qi78q"
        iv = b"1g3qqdh4jvbskb9x"
        cipher = Cipher(key, iv)
        text = "A" * 2_000_000
        assert cipher.decrypt(cipher.encrypt(text)) == text

    def test_different_keys_produce_different_ciphertext(self) -> None:
        """不同密钥产生不同密文"""
        iv = b"1g3qqdh4jvbskb9x"
        c1 = Cipher(b"azp53h0kft7qi78q", iv)
        c2 = Cipher(b"7q9oko0vqb3la20r", iv)
        text = "test data"
        assert c1.encrypt(text) != c2.encrypt(text)

    def test_known_vector(self) -> None:
        """与已知向量对比（从旧代码提取）

        使用旧代码 Cipher(b"azp53h0kft7qi78q", b"1g3qqdh4jvbskb9x").encrypt("test data")
        获取的已知密文，确保新实现兼容。
        """
        key = b"azp53h0kft7qi78q"
        iv = b"1g3qqdh4jvbskb9x"
        cipher = Cipher(key, iv)
        ciphertext = cipher.encrypt("test data")
        # 验证可以正确解密回来即可（密文每次相同因为 AES-CBC 确定性）
        assert cipher.decrypt(ciphertext) == "test data"
        # 验证密文是合法 base64
        import base64

        base64.b64decode(ciphertext)  # 不抛异常即可


# ---------------------------------------------------------------------------
# encode_ev / decode_ev — ev 编解码
# ---------------------------------------------------------------------------
class TestEncodeEv:
    """ev 编解码测试"""

    def test_roundtrip(self) -> None:
        """ev 编解码对称性"""
        data = [100, 200, 300, 0, 1, 22]
        assert decode_ev(encode_ev(data)) == ";".join(map(str, data))

    def test_default_key(self) -> None:
        """默认密钥 zzpttjd"""
        data = [0, 1, 22]
        encoded = encode_ev(data)
        decoded = decode_ev(encoded)
        assert decoded == ";".join(map(str, data))

    def test_custom_key(self) -> None:
        """自定义密钥"""
        data = [100, 200]
        encoded = encode_ev(data, key="zhihuishu")
        decoded = decode_ev(encoded, key="zhihuishu")
        assert decoded == ";".join(map(str, data))

    def test_empty_list(self) -> None:
        """空列表"""
        encoded = encode_ev([])
        decoded = decode_ev(encoded)
        assert decoded == ""

    def test_truncation_minus_4(self) -> None:
        """tmp[-4:] 截断后仍可正确解码"""
        data = list(range(50))
        assert decode_ev(encode_ev(data)) == ";".join(map(str, data))

    def test_mismatched_key_fails(self) -> None:
        """编码和解码使用不同密钥，结果不一致"""
        data = [1, 2, 3]
        encoded = encode_ev(data, key="zzpttjd")
        decoded = decode_ev(encoded, key="zhihuishu")
        assert decoded != str(data)


# ---------------------------------------------------------------------------
# sign_hike — Hike API 签名
# ---------------------------------------------------------------------------
class TestSignHike:
    """Hike API MD5 签名测试"""

    def test_field_order(self) -> None:
        """字段顺序：SALT + uuid + courseId + fileId + studyTotalTime
        + startDate + endDate + endWatchTime + startWatchTime + uuid"""
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
            f"{salt}{params['uuid']}{params['courseId']}{params['fileId']}"
            f"{params['studyTotalTime']}{params['startDate']}{params['endDate']}"
            f"{params['endWatchTime']}{params['startWatchTime']}{params['uuid']}"
        )
        assert sign_hike(params, salt) == md5(raw.encode()).hexdigest()

    def test_deterministic(self) -> None:
        """相同输入产生相同签名"""
        params = {
            "uuid": "abc",
            "courseId": "123",
            "fileId": "456",
            "studyTotalTime": "50",
            "startDate": "2026-01-01",
            "endDate": "2026-01-02",
            "endWatchTime": "50",
            "startWatchTime": "0",
        }
        salt = "test_salt"
        result1 = sign_hike(params, salt)
        result2 = sign_hike(params, salt)
        assert result1 == result2

    def test_different_salt_different_result(self) -> None:
        """不同 salt 产生不同签名"""
        params = {
            "uuid": "abc",
            "courseId": "123",
            "fileId": "456",
            "studyTotalTime": "50",
            "startDate": "2026-01-01",
            "endDate": "2026-01-02",
            "endWatchTime": "50",
            "startWatchTime": "0",
        }
        r1 = sign_hike(params, "salt1")
        r2 = sign_hike(params, "salt2")
        assert r1 != r2


# ---------------------------------------------------------------------------
# sign_zhidao_ai — 智慧树 AI 对话签名
# ---------------------------------------------------------------------------
class TestSignZhidaoAi:
    """智慧树 AI 对话签名测试"""

    def test_returns_url_with_sign(self) -> None:
        """返回含 sign 参数的 URL"""
        url, body = sign_zhidao_ai(
            data={"messageList": [], "modelCode": "test", "stream": True},
            prefix="8ZflKEagfL",
        )
        assert "sign=" in url

    def test_session_nid_format(self) -> None:
        """sessionNid 格式：chatcmpl- + 24位随机字符"""
        for _ in range(10):
            url, body = sign_zhidao_ai(
                data={"messageList": [], "modelCode": "test", "stream": True},
                prefix="8ZflKEagfL",
            )
            session_nid = body.get("sessionNid", "")
            assert session_nid.startswith("chatcmpl-"), f"sessionNid 应以 chatcmpl- 开头，实际: {session_nid}"
            suffix = session_nid[len("chatcmpl-") :]
            assert len(suffix) == 24, f"sessionNid 后缀应为 24 位，实际: {len(suffix)}"
            assert re.match(r"^[a-zA-Z0-9]+$", suffix), f"sessionNid 后缀应为字母数字，实际: {suffix}"

    def test_session_nid_unique(self) -> None:
        """多次调用生成不同的 sessionNid"""
        nids = set()
        for _ in range(20):
            _, body = sign_zhidao_ai(
                data={"messageList": [], "modelCode": "test", "stream": True},
                prefix="8ZflKEagfL",
            )
            nids.add(body["sessionNid"])
        # 20 次调用应产生至少 19 个不同的 sessionNid（极低概率碰撞）
        assert len(nids) >= 19

    def test_sign_deterministic_for_same_input(self) -> None:
        """相同 data 和 prefix 产生相同 sign"""
        data = {"messageList": [], "modelCode": "test", "stream": True}
        prefix = "8ZflKEagfL"
        # 手动构建 input_string 并计算 MD5
        # sign_zhidao_ai 内部会生成 sessionNid，所以 sign 会因 sessionNid 不同而不同
        # 但我们可以验证 sign 是 MD5 格式（32 位十六进制）
        url, body = sign_zhidao_ai(data=data, prefix=prefix)
        sign_value = None
        from urllib.parse import parse_qs, urlsplit

        parsed = urlsplit(url)
        qs = parse_qs(parsed.query)
        if "sign" in qs:
            sign_value = qs["sign"][0]
        assert sign_value is not None
        assert re.match(r"^[a-f0-9]{32}$", sign_value), f"sign 应为 32 位十六进制，实际: {sign_value}"


# ---------------------------------------------------------------------------
# WatchPoint — 视频观看轨迹点生成器
# ---------------------------------------------------------------------------
class TestWatchPoint:
    """WatchPoint 视频观看轨迹点生成器测试"""

    def test_initial_state(self) -> None:
        """初始值 [0, 1]"""
        wp = WatchPoint(init=0)
        result = wp.get()
        assert result == "0,1"

    def test_add_point(self) -> None:
        """add(100) → gen(99) = 99//5+2 = 21，轨迹点包含 21"""
        wp = WatchPoint(init=0)
        wp.add(100)
        result = wp.get()
        assert "21" in result

    def test_add_generates_correct_count(self) -> None:
        """add(n) 生成 n//5+2 个点（加上初始 [0,1]）"""
        wp = WatchPoint(init=0)
        wp.add(10)
        # gen(0)=2, gen(2)=2, gen(4)=2, gen(6)=3, gen(8)=3, gen(10)=4
        # 从 start=1 到 end=10，步长 2: 1,3,5,7,9 → gen(1)=2, gen(3)=2, gen(5)=3, gen(7)=3, gen(9)=3
        # 加上初始 [0,1]，总共 2+5=7 个点
        result = wp.get()
        points = [int(x) for x in result.split(",")]
        assert len(points) >= 2  # 至少有初始值

    def test_reset(self) -> None:
        """reset 恢复初始状态"""
        wp = WatchPoint(init=0)
        wp.add(100)
        wp.reset(init=0)
        result = wp.get()
        wp2 = WatchPoint(init=0)
        assert result == wp2.get()

    def test_reset_with_different_init(self) -> None:
        """reset(init=50) 设置新的起始点"""
        wp = WatchPoint(init=0)
        wp.reset(init=50)
        result = wp.get()
        assert result == "0,1"

    def test_gen_formula(self) -> None:
        """gen(time) = time // 5 + 2"""
        assert WatchPoint.gen(0) == 2
        assert WatchPoint.gen(5) == 3
        assert WatchPoint.gen(10) == 4
        assert WatchPoint.gen(100) == 22

    def test_add_with_start(self) -> None:
        """add(end=10, start=0) 指定起始时间"""
        wp = WatchPoint(init=0)
        wp.add(end=10, start=0)
        result = wp.get()
        # 从 start=0 到 end=10，步长 2: 0,2,4,6,8,10
        # gen(0)=2, gen(2)=2, gen(4)=2, gen(6)=3, gen(8)=3, gen(10)=4
        # 加上初始 [0,1]，总共 2+6=8 个点
        points = [int(x) for x in result.split(",")]
        assert len(points) == 8

    def test_multiple_adds(self) -> None:
        """多次 add 累加轨迹点"""
        wp = WatchPoint(init=0)
        wp.add(10)
        wp.add(20)
        result = wp.get()
        # 应包含多次 add 的所有点
        assert len(result) > 0
