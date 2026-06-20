"""Task 1.1 — exceptions.py 测试"""

import pytest

from zhs.exceptions import ApiError, CaptchaRequired, LoginFailed, TimeLimitExceeded, ZhsError


class TestZhsError:
    def test_is_exception(self) -> None:
        assert issubclass(ZhsError, Exception)

    def test_can_be_caught(self) -> None:
        with pytest.raises(ZhsError):
            raise ZhsError("test error")

    def test_message(self) -> None:
        err = ZhsError("something went wrong")
        assert "something went wrong" in str(err)


class TestApiError:
    def test_inherits_zhs_error(self) -> None:
        assert issubclass(ApiError, ZhsError)

    def test_carries_code_and_message(self) -> None:
        err = ApiError(code=-12, message="需要验证码")
        assert err.code == -12
        assert err.message == "需要验证码"

    def test_str_contains_code(self) -> None:
        err = ApiError(code=-12, message="需要验证码")
        assert "-12" in str(err)

    def test_caught_as_zhs_error(self) -> None:
        with pytest.raises(ZhsError):
            raise ApiError(code=-1, message="fail")


class TestCaptchaRequired:
    def test_inherits_zhs_error(self) -> None:
        assert issubclass(CaptchaRequired, ZhsError)

    def test_can_be_caught_specific(self) -> None:
        with pytest.raises(CaptchaRequired):
            raise CaptchaRequired("需要验证码")

    def test_can_be_caught_as_base(self) -> None:
        with pytest.raises(ZhsError):
            raise CaptchaRequired("需要验证码")


class TestLoginFailed:
    def test_inherits_zhs_error(self) -> None:
        assert issubclass(LoginFailed, ZhsError)

    def test_message(self) -> None:
        err = LoginFailed("账号或密码错误")
        assert "账号或密码错误" in str(err)


class TestTimeLimitExceeded:
    def test_inherits_zhs_error(self) -> None:
        assert issubclass(TimeLimitExceeded, ZhsError)
