"""易盾自定义加密原语。

不是标准 AES：自定义 S 盒 + 固定种子 + 轮密钥操作，按 64 字节分组，
最后用私有 base64 字母表编码「4 字节原始 IV + 密文块」。

两处调用差异：滑块在明文后拼 ``crc32``，点选不拼。
"""

import random
import urllib.parse

# 标准 base64 的变体字母表与填充字符
BASE64_ALPHABET = "i/x1XgU0z7k8N+lCpOnPrv6\\qu2Gj9HRcwTYZ4bfSJBhaWstAeoMIEQ5mDdVFLKy"
BASE64_PADDING = "3"

# 私有字母表（第三位是 "."），密文里的句点就来自这里
PRIVATE_B64_ALPHABET = "MB.CfHUzEeJpsuGkgNwhqiSaI4Fd9L6jYKZAxn1/Vml0c5rbXRP+8tD3QTO2vWyo"
PRIVATE_B64_PADDING = "7"

__SEED_KEY__ = "fd6a43ae25f74398b61c03c83be37449"
__ROUND_KEY__ = "037606da0296055c"

__SBOX__ = (
    "a7be3f3933fa8c5fcf86c4b6908b569ba1e26c1a6d7cfbf60ae4b00e074a194dac4b73e7f8985411"
    "59a39d08183b76eedee3ed341e6685d2357440158394b1ff03a9004cbbb5ca7dcb7f41489a16e03d"
    "cc9c71eb3c9796685b1d01b4d56193a6e1f1a2470445c191ae49c5d82765dc82c350f263387a24a5"
    "02fcbf442e2dddaad0e936d9ea22b89275307b42518fbc3a626ba806d4ecd6d725f50cc8c72fefa4"
    "551ccd6fc9b2b7ab954f815c7264c6e51f4eaf99885a79892b1b60a0b3526e57ba5d178d3709588"
    "47eb9fd28f9ce0bc023f4148a2adfe632126769057043d3bd8eda0df7872629f3809ef05310e8311"
    "3216afe202c460fc23e789f77d1addb5e"
)

_B64_GROUP = 64
_SAMPLE_NUM = 50
_CB_POS = (1, 10, 12, 13, 26, 31)
_CB_CODE = "vfnv46"
_UUID_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def _to_byte(value: int) -> int:
    """收敛到有符号字节（-128~127），与参考实现一致。"""
    value &= 0xFF
    return value - 256 if value > 127 else value


def _hex_to_byte(text: str) -> int:
    return _to_byte(int(text, 16))


def _int_to_bytes(value: int) -> list[int]:
    return [_to_byte(value >> shift) for shift in (24, 16, 8, 0)]


def _string_to_bytes(text: str) -> list[int]:
    """按 JS 的 encodeURIComponent 语义把字符串转成字节。"""
    encoded = urllib.parse.quote(text, safe="")
    result: list[int] = []
    index = 0
    while index < len(encoded):
        if encoded[index] == "%" and index + 2 < len(encoded):
            result.append(_hex_to_byte(encoded[index + 1:index + 3]))
            index += 3
        else:
            result.append(_to_byte(ord(encoded[index])))
            index += 1
    return result


def _bytes_to_hex(values: list[int]) -> str:
    return "".join(f"{value & 0xFF:02x}" for value in values)


def _xor_byte(first: int, second: int) -> int:
    return _to_byte(_to_byte(first) ^ _to_byte(second))


def _xors(data: list[int], key: list[int]) -> list[int]:
    if not key:
        return data[:]
    return [_xor_byte(value, key[index % len(key)]) for index, value in enumerate(data)]


def _shift_add(first: int, second: int) -> int:
    return _to_byte(first + second)


def _shifts(data: list[int], key: list[int]) -> list[int]:
    if not key:
        return data[:]
    return [_shift_add(value, key[index % len(key)]) for index, value in enumerate(data)]


def _padding_zero(length: int) -> list[int]:
    return [0] * length


def _copy_to(source: list[int], source_offset: int, target: list[int], target_offset: int, count: int) -> None:
    for index in range(count):
        if source_offset + index < len(source):
            target[target_offset + index] = source[source_offset + index]


def _expand_key(key_bytes: list[int]) -> list[int]:
    if not key_bytes:
        return _padding_zero(_B64_GROUP)
    if len(key_bytes) >= _B64_GROUP:
        return key_bytes[:_B64_GROUP]
    return [key_bytes[index % len(key_bytes)] for index in range(_B64_GROUP)]


# ---------------------------------------------------------------- base64


def _b64_encode_3to4(chunk: list[int], alphabet: str, padding: str) -> str:
    length = len(chunk)
    b0 = chunk[0]
    b1 = chunk[1] if length > 1 else 0
    b2 = chunk[2] if length > 2 else 0
    if length == 1:
        return alphabet[(b0 >> 2) & 0x3F] + alphabet[((b0 << 4) & 0x30) + ((b1 >> 4) & 0xF)] + padding + padding
    if length == 2:
        return (
            alphabet[(b0 >> 2) & 0x3F]
            + alphabet[((b0 << 4) & 0x30) + ((b1 >> 4) & 0xF)]
            + alphabet[((b1 << 2) & 0x3C) + ((b2 >> 6) & 0x3)]
            + padding
        )
    return (
        alphabet[(b0 >> 2) & 0x3F]
        + alphabet[((b0 << 4) & 0x30) + ((b1 >> 4) & 0xF)]
        + alphabet[((b1 << 2) & 0x3C) + ((b2 >> 6) & 0x3)]
        + alphabet[b2 & 0x3F]
    )


def _b64_decode_4to3(indices: list[int]) -> list[int]:
    length = len(indices)
    result: list[int] = []
    if length >= 2:
        result.append(_to_byte(((indices[0] << 2) & 0xFF) + ((indices[1] >> 4) & 0x3)))
    if length >= 3:
        result.append(_to_byte(((indices[1] << 4) & 0xFF) + ((indices[2] >> 2) & 0xF)))
    if length >= 4:
        result.append(_to_byte(((indices[2] << 6) & 0xFF) + (indices[3] & 0x3F)))
    return result


def _base64_encode_core(values: list[int], alphabet: str, padding: str) -> str:
    if not values:
        return ""
    unsigned = [value & 0xFF for value in values]
    parts: list[str] = []
    index = 0
    while index < len(unsigned):
        chunk = unsigned[index:index + 3]
        parts.append(_b64_encode_3to4(chunk, alphabet, padding))
        index += 3
    return "".join(parts)


def _base64_decode_core(value: str, alphabet: str, padding: str) -> list[int]:
    padding_index = value.find(padding)
    characters = value[:padding_index] if padding_index != -1 else value
    indices = [alphabet.index(character) for character in characters]
    result: list[int] = []
    index = 0
    while index < len(indices):
        result.extend(_b64_decode_4to3(indices[index:index + 4]))
        index += 4
    return result


def base64_encode(values: list[int]) -> str:
    return _base64_encode_core(values, BASE64_ALPHABET, BASE64_PADDING)


def base64_encode_private(values: list[int]) -> str:
    return _base64_encode_core(values, PRIVATE_B64_ALPHABET, PRIVATE_B64_PADDING)


def base64_decode(value: str) -> list[int]:
    return _base64_decode_core(value, BASE64_ALPHABET, BASE64_PADDING)


def base64_decode_private(value: str) -> list[int]:
    return _base64_decode_core(value, PRIVATE_B64_ALPHABET, PRIVATE_B64_PADDING)


# ---------------------------------------------------------------- crc / 轮密钥

_CRC32_TABLE = []
for _index in range(256):
    _crc = _index
    for _ in range(8):
        _crc = (_crc >> 1) ^ 0xEDB88320 if _crc & 1 else _crc >> 1
    _CRC32_TABLE.append(_crc)


def gen_crc32(values: list[int]) -> str:
    """返回 8 位十六进制字符串。"""
    crc = 0xFFFFFFFF
    for value in values:
        crc = (crc >> 8) ^ _CRC32_TABLE[(crc ^ (value & 0xFF)) & 0xFF]
    return _bytes_to_hex(_int_to_bytes((crc ^ 0xFFFFFFFF) & 0xFFFFFFFF))


_SBOX_BYTES = [_to_byte(int(__SBOX__[index:index + 2], 16)) for index in range(0, len(__SBOX__), 2)]


def _sub_bytes(block: list[int]) -> list[int]:
    return [_to_byte(_SBOX_BYTES[16 * ((value >> 4) & 0xF) + (value & 0xF)]) for value in block]


def _apply_round_key(block: list[int]) -> list[int]:
    round_key = __ROUND_KEY__
    index = 0
    while index < len(round_key):
        operation = _hex_to_byte(round_key[index:index + 2])
        argument = _hex_to_byte(round_key[index + 2:index + 4])
        if operation == 1:
            block = [_xor_byte(value, argument) for value in block] if block else []
        elif operation == 2:
            block = [_shift_add(value, argument) for value in block] if block else []
        elif operation in (3, 4, 5, 6):
            updated: list[int] = []
            for value in block:
                if operation == 3:
                    updated.append(_xor_byte(value, argument))
                    argument = _to_byte(argument + 1)
                elif operation == 4:
                    updated.append(_shift_add(value, argument))
                    argument = _to_byte(argument + 1)
                elif operation == 5:
                    updated.append(_xor_byte(value, argument))
                    argument = _to_byte(argument - 1)
                else:
                    updated.append(_shift_add(value, argument))
                    argument = _to_byte(argument - 1)
            block = updated
        index += 4
    return block


def _pad_pkcs7(data: list[int]) -> list[int]:
    if not data:
        return _padding_zero(_B64_GROUP)
    data_length = len(data)
    remainder = data_length % _B64_GROUP
    padding_length = _B64_GROUP - remainder - 4 if remainder <= 60 else 128 - remainder - 4
    padded = [0] * (data_length + padding_length + 4)
    _copy_to(data, 0, padded, 0, data_length)
    _copy_to(_int_to_bytes(data_length), 0, padded, data_length + padding_length, 4)
    return padded


def _blocks_from_bytes(values: list[int]) -> list[list[int]]:
    if len(values) % _B64_GROUP != 0:
        return []
    count = len(values) // _B64_GROUP
    return [values[index * _B64_GROUP:(index + 1) * _B64_GROUP] for index in range(count)]


def _generate_iv() -> tuple[list[int], list[int]]:
    seed_bytes = _expand_key(_string_to_bytes(__SEED_KEY__))
    random_bytes = [_to_byte(random.randint(0, 255)) for _ in range(4)]
    seed_bytes = _xors(seed_bytes, _expand_key(random_bytes))
    return _expand_key(seed_bytes), random_bytes


def _aes_core(text: str, *, with_crc: bool) -> str:
    data_bytes = _string_to_bytes(text)
    iv, raw_iv = _generate_iv()
    combined = data_bytes + _string_to_bytes(gen_crc32(data_bytes)) if with_crc else data_bytes
    blocks = _blocks_from_bytes(_pad_pkcs7(combined))
    result = raw_iv[:] + [0] * (len(blocks) * _B64_GROUP)
    previous = iv[:]
    for index, block in enumerate(blocks):
        block = _xors(_apply_round_key(block), iv)
        block = _shifts(block, previous)
        block = _xors(block, previous)
        previous = _sub_bytes(_sub_bytes(block))
        _copy_to(previous, 0, result, _B64_GROUP * index + 4, _B64_GROUP)
    return base64_encode_private(result)


def aes(text: str) -> str:
    """滑块使用的加密：明文后拼接 crc32。"""
    return _aes_core(text, with_crc=True)


def aes_click(text: str) -> str:
    """点选使用的加密：不拼接 crc32（长度字段即纯明文长度）。"""
    return _aes_core(text, with_crc=False)


# ---------------------------------------------------------------- 组合封装


def xor_encode(key: str, text: str) -> str:
    """异或后用标准 base64 字母表编码。"""
    return base64_encode(_xors(_string_to_bytes(text), _string_to_bytes(key)))


def generate_uuid(length: int = 32) -> str:
    return "".join(random.choice(_UUID_CHARS) for _ in range(length))


def generate_cb() -> str:
    """生成请求参数 ``cb``（客户端签名串）。"""
    characters = list(generate_uuid(32))
    for index, position in enumerate(_CB_POS):
        if position < len(characters):
            characters[position] = _CB_CODE[index]
    return aes("".join(characters))


def with_crc(text: str) -> str:
    """在 ``xor_encode`` 结果后追加 8 位 crc32，点选的 p / ext 需要。"""
    return text + gen_crc32(_string_to_bytes(text))


__all__ = [
    "BASE64_ALPHABET",
    "BASE64_PADDING",
    "PRIVATE_B64_ALPHABET",
    "PRIVATE_B64_PADDING",
    "aes",
    "aes_click",
    "base64_decode",
    "base64_decode_private",
    "base64_encode",
    "base64_encode_private",
    "gen_crc32",
    "generate_cb",
    "generate_uuid",
    "with_crc",
    "xor_encode",
]
