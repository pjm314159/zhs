"""验证码模块单测：不依赖网络、OpenCV 与模型服务。"""

import pytest

from zhs.captcha import click, codec, fp, yidun
from zhs.captcha.service import CaptchaService, CaptchaTrigger
from zhs.captcha.vision import _parse
from zhs.config import AppConfig

_INV_SBOX = [0] * 256
for _index, _value in enumerate(codec._SBOX_BYTES):  # noqa: SLF001
    _INV_SBOX[_value & 0xFF] = _index

_OPS = []
_pos = 0
while _pos < len(codec.__ROUND_KEY__):  # noqa: SLF001
    _OPS.append(
        (
            int(codec.__ROUND_KEY__[_pos : _pos + 2], 16),  # noqa: SLF001
            int(codec.__ROUND_KEY__[_pos + 2 : _pos + 4], 16),  # noqa: SLF001
        )
    )
    _pos += 4


def _inv_round_key(block: list[int]) -> list[int]:
    for op, arg in reversed(_OPS):
        out: list[int] = []
        cur = arg
        for value in block:
            if op in (1, 3, 5):
                out.append((value ^ cur) & 0xFF)
            elif op in (2, 4, 6):
                out.append((value - cur) & 0xFF)
            else:
                out.append(value)
            if op in (3, 4):
                cur = (cur + 1) & 0xFF
            elif op in (5, 6):
                cur = (cur - 1) & 0xFF
        block = out
    return block


def decrypt(value: str) -> bytes:
    """测试用逆运算：还原 aes / aes_click 的明文。"""
    raw = [item & 0xFF for item in codec.base64_decode_private(value)]
    seed = codec._expand_key(codec._string_to_bytes(codec.__SEED_KEY__))  # noqa: SLF001
    iv = [item & 0xFF for item in codec._expand_key(codec._xors(seed, codec._expand_key(raw[:4])))]

    previous = iv[:]
    out = bytearray()
    pos = 4
    while pos + 64 <= len(raw):
        chunk = raw[pos : pos + 64]
        stage = [_INV_SBOX[item & 0xFF] for item in chunk]
        stage = [_INV_SBOX[item & 0xFF] for item in stage]
        mixed = [(stage[i] ^ previous[i]) & 0xFF for i in range(64)]
        unshifted = [(mixed[i] - previous[i]) & 0xFF for i in range(64)]
        out.extend(_inv_round_key([(unshifted[i] ^ iv[i]) & 0xFF for i in range(64)]))
        previous = chunk
        pos += 64
    return bytes(out[: int.from_bytes(out[-4:], "big")])


def test_parse_jsonp() -> None:
    payload = '{"error":0,"data":{"token":"t"}}'
    assert yidun.parse_jsonp(f"__JSONP_abc_1({payload})")["data"]["token"] == "t"
    with pytest.raises(ValueError):
        yidun.parse_jsonp("not jsonp")


def test_compose_validate_shape() -> None:
    raw = "a" * 172  # 真实裸 validate 长度
    fp_value = "b" * 190  # 真实 fp 长度
    composed = yidun.compose_validate(raw, fp_value)
    assert len(composed) == 531
    assert composed.startswith("CN31_")
    assert composed.endswith("_v_i_1")


def test_aes_includes_crc() -> None:
    plain = "00000000"
    expected = plain.encode() + codec.gen_crc32(codec._string_to_bytes(plain)).encode()  # noqa: SLF001
    assert decrypt(codec.aes(plain)) == expected
    assert len(codec.aes(plain)) == 92


def test_aes_click_has_no_crc() -> None:
    plain = "iAWvniEj0AZ32836f5a5"
    assert decrypt(codec.aes_click(plain)) == plain.encode()
    assert len(codec.aes_click(plain)) == 92


def test_click_data_matches_captured_sample() -> None:
    token = "19cd4e391ce349d29903d3b5367ce095"
    data = click.build_data(token, 226, 99)
    assert data["d"] == ""
    assert len(data["m"]) == 92 and len(data["p"]) == 92 and len(data["ext"]) == 92
    assert decrypt(data["m"]) == b"00000000"
    assert decrypt(data["p"]) == b"iAWvniEj0AZ32836f5a5"
    assert decrypt(data["ext"]) == b"i/vP4675e9cc"


def test_click_to_css() -> None:
    assert click.to_css(339, 148, 480) == (226, 99)
    assert click.to_css(480, 240, 480) == (320, 160)


def test_fp_format() -> None:
    assert fp.validate_fp_format("") == ["fp 为空"]
    assert fp.validate_fp_format("abc")
    good = "x" * 175 + ":1795408610061"
    assert fp.validate_fp_format(good) == []
    assert fp.validate_fp_format(good + "%2F")


def test_vision_parse() -> None:
    assert _parse('{"x": 12, "y": 34}') == (12.0, 34.0)
    assert _parse('分析如下 {"x": 5.5, "y": 6}') == (5.5, 6.0)
    assert _parse("x=7, y=8") == (7.0, 8.0)
    assert _parse("看不出") is None


def test_service_disabled_returns_none() -> None:
    config = AppConfig()
    service = CaptchaService(config)
    assert service.solve(CaptchaTrigger(kind="click", referer="https://example.com")) is None


def test_service_requires_fp() -> None:
    config = AppConfig()
    config.captcha.enabled = True
    service = CaptchaService(config)
    assert service.enabled() is False
    assert service.solve(CaptchaTrigger(kind="click", referer="https://example.com")) is None


def test_service_without_vision_key() -> None:
    config = AppConfig()
    config.captcha.enabled = True
    config.captcha.fp = "x" * 175 + ":1795408610061"
    service = CaptchaService(config)
    assert service.enabled() is True
    assert service.solve(CaptchaTrigger(kind="click", referer="https://example.com")) is None


def test_trigger_metadata() -> None:
    click_trigger = CaptchaTrigger(kind="click", referer="r")
    slide_trigger = CaptchaTrigger(kind="slide", referer="r")
    assert (click_trigger.width, click_trigger.type_code) == (320, 11)
    assert (slide_trigger.width, slide_trigger.type_code) == (400, 2)
    assert click_trigger.captcha_id == yidun.CAPTCHA_CLICK
    assert slide_trigger.captcha_id == yidun.CAPTCHA_SLIDE
