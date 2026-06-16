"""ZHS 加解密模块

提供 AES-128-CBC 加解密、ev 编解码、Hike 签名、智慧树 AI 签名、视频观看轨迹点生成等功能。
"""

import hashlib
import json
import random
import string
from base64 import b64decode, b64encode
from collections.abc import Iterator, Sequence
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from Crypto.Cipher import AES

from zhs.exceptions import ZhsError


class Cipher:
    """AES-128-CBC 加解密器

    使用 PKCS7 填充，密钥和 IV 由调用方显式传入，不硬编码。
    """

    def __init__(self, key: bytes, iv: bytes) -> None:
        if len(key) != 16:
            raise ZhsError(f"AES 密钥长度必须为 16 字节，当前为 {len(key)} 字节")
        if len(iv) != 16:
            raise ZhsError(f"AES IV 长度必须为 16 字节，当前为 {len(iv)} 字节")
        self.key = key
        self.iv = iv

    @staticmethod
    def _pad(data: str) -> bytes:
        """PKCS7 填充（基于 UTF-8 字节长度）"""
        data_bytes = data.encode("utf-8")
        pad_len = 16 - len(data_bytes) % 16
        return data_bytes + bytes([pad_len] * pad_len)

    @staticmethod
    def _unpad(data: bytes) -> str:
        """移除 PKCS7 填充"""
        pad_len = data[-1]
        return data[:-pad_len].decode("utf-8")

    def encrypt(self, plaintext: str) -> str:
        """加密明文，返回 base64 编码的密文"""
        cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        encrypted = cipher.encrypt(self._pad(plaintext))
        return b64encode(encrypted).decode()

    def decrypt(self, ciphertext: str) -> str:
        """解密 base64 编码的密文，返回明文"""
        try:
            cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
            decrypted = cipher.decrypt(b64decode(ciphertext))
        except Exception as e:
            raise ZhsError(f"解密失败: {e}") from e
        return self._unpad(decrypted)


class WatchPoint:
    """视频观看轨迹点生成器

    维护轨迹点列表，gen(time) = time // 5 + 2，初始值为 [0, 1]。
    """

    def __init__(self, init: int = 0) -> None:
        self.wp: list[int] = [0, 1]
        self.last: int = int(init) or 1

    def add(self, end: int, start: int | None = None) -> None:
        """添加时间点，按间隔 2 秒生成轨迹点"""
        wp_interval = 2
        s = self.last if start is None else int(start)
        e = int(end)
        self.last = e
        for i in range(s, e + 1, wp_interval):
            self.wp.append(self.gen(i))

    def get(self) -> str:
        """获取轨迹点字符串（逗号分隔）"""
        return ",".join(map(str, self.wp))

    def reset(self, init: int = 0) -> None:
        """重置轨迹点状态"""
        self.wp = [0, 1]
        self.last = int(init) or 1

    @staticmethod
    def gen(time: int) -> int:
        """生成单个轨迹点值"""
        return int(time // 5 + 2)


def encode_ev(data: Sequence[int | str], key: str = "zzpttjd") -> str:
    """ev 编码（XOR）

    将数据列表用分号连接后，逐字符与密钥循环 XOR，再取十六进制后 4 位拼接。
    """
    key_chars = _key_generator(key)
    data_str = ";".join(map(str, data))
    ev = ""
    for c in data_str:
        tmp = hex(ord(c) ^ next(key_chars)).replace("0x", "")
        if len(tmp) < 2:
            tmp = "0" + tmp
        ev += tmp[-4:]
    return ev


def decode_ev(encoded: str, key: str = "zzpttjd") -> str:
    """ev 解码

    将编码字符串逆向解码为原始字符串。
    """
    key_chars = _key_generator(key)
    ev = list(encoded)
    ls: list[int] = []
    while ev:
        d2, d1 = ev.pop(), ev.pop()
        c = int(d1 + d2, 16)
        ls.append(c)
    ret = ""
    for c in ls[::-1]:
        ret += chr(c ^ next(key_chars))
    return ret


def sign_hike(params: dict[str, Any], salt: str) -> str:
    """Hike API 签名（MD5）

    按固定字段顺序拼接后取 MD5 摘要：
    SALT + uuid + courseId + fileId + studyTotalTime + startDate + endDate + endWatchTime + startWatchTime + uuid
    """
    raw = (
        salt
        + str(params.get("uuid", ""))
        + str(params.get("courseId", ""))
        + str(params.get("fileId", ""))
        + str(params.get("studyTotalTime", ""))
        + str(params.get("startDate", ""))
        + str(params.get("endDate", ""))
        + str(params.get("endWatchTime", ""))
        + str(params.get("startWatchTime", ""))
        + str(params.get("uuid", ""))
    )
    return hashlib.md5(raw.encode()).hexdigest()


def sign_zhidao_ai(data: dict[str, Any], prefix: str = "8ZflKEagfL") -> tuple[str, dict[str, Any]]:
    """智慧树 AI 对话签名

    生成 sessionNid（chatcmpl- + 24 位随机字符），构建签名，
    返回带 sign 参数的 URL 和更新后的 body 字典。
    """
    url = data.pop("url", "")
    if "sessionNid" not in data:
        data["sessionNid"] = _generate_session_nid()

    input_string = _build_input_string(data)
    signature = _generate_signature(input_string, prefix)

    scheme, netloc, path, query_string, fragment = urlsplit(url)
    query_params = dict(parse_qsl(query_string))
    query_params["sign"] = signature
    new_query_string = urlencode(query_params)
    signed_url = urlunsplit((scheme, netloc, path, new_query_string, fragment))

    return signed_url, data


def _key_generator(key: str) -> Iterator[int]:
    """生成密钥字符的循环迭代器"""
    while True:
        for c in key:
            yield ord(c)


def _generate_session_nid() -> str:
    """生成随机会话 ID（chatcmpl- + 24 位随机字符）"""
    chars = string.ascii_lowercase + string.digits
    return "chatcmpl-" + "".join(random.choice(chars) for _ in range(24))


def _build_input_string(data: dict[str, Any]) -> str:
    """构建签名输入字符串"""
    json_data = {
        "messageList": "[object Object]",
        "modelCode": data.get("modelCode", ""),
        "sessionNid": data.get("sessionNid", ""),
        "stream": data.get("stream", False),
    }
    return json.dumps(json_data, separators=(",", ":")).replace('"true"', "true").replace('"false"', "false")


def _generate_signature(input_string: str, prefix: str) -> str:
    """生成 MD5 签名"""
    return hashlib.md5((prefix + input_string).encode("utf-8")).hexdigest()
