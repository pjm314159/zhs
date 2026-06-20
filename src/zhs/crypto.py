"""ZHS 加解密模块

提供 AES-128-CBC 加解密、ev 编解码、Hike 签名、视频观看轨迹点生成等功能。
"""

import hashlib
from base64 import b64decode, b64encode
from collections.abc import Iterator, Sequence
from typing import Any

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


def _key_generator(key: str) -> Iterator[int]:
    """生成密钥字符的循环迭代器"""
    while True:
        for c in key:
            yield ord(c)
