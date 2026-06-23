"""实际扫码登录集成测试

使用真实 API 进行扫码登录测试。
运行方式: uv run python scripts/test_login_qr.py
"""

import sys
from pathlib import Path

from zhs.config import ConfigManager
from zhs.logger import setup_logging
from zhs.login import LoginManager
from zhs.session import ZhsSession


def show_qr_image(img_bytes: bytes) -> None:
    """保存二维码为图片文件"""
    path = Path(".temp/qr_login.png")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(img_bytes)
    print(f"二维码已保存至 {path.absolute()}，请打开扫描")


if __name__ == "__main__":
    config = ConfigManager().load()
    setup_logging(config)
    session = ZhsSession(config)
    manager = LoginManager(session, config)

    print("=" * 50)
    print("智慧树扫码登录集成测试")
    print("=" * 50)

    # 先尝试恢复已保存的 cookies
    cookies_path = Path.home() / ".zhs" / "cookies.json"
    if cookies_path.exists():
        print("发现已保存的 cookies，尝试恢复...")
        if manager.try_restore_cookies(cookies_path) and session.uuid:
            print(f"Cookies 恢复成功！UUID: {session.uuid}")
            print("跳过扫码登录")
        else:
            print("Cookies 恢复失败或无效，进行扫码登录")
    else:
        print("未发现已保存的 cookies，进行扫码登录")

    if not session.uuid:
        try:
            result = manager.login_with_qr(
                qr_callback=show_qr_image,
                on_scanned=lambda: print(">>> 已扫描，请在手机上确认登录"),
                image_path=str(Path(".temp")),
                _max_retries=10,
            )

            if result.success:
                print(f"\n登录成功！UUID: {result.uuid}")
                print(f"Cookies 数量: {len(session.cookies)}")

                # 保存 cookies
                manager.save_cookies(cookies_path)
                print(f"Cookies 已保存至 {cookies_path}")
            else:
                print("登录失败")
        except Exception as e:
            print(f"登录异常: {e}")
            sys.exit(1)

    # 验证 cookies 有效性：尝试获取课程列表
    print("\n验证 cookies 有效性...")
    try:
        data = session.zhidao_query(
            f"{config.urls.base}/gateway/t/v1/student/course/share/queryShareCourseInfo",
            data={"status": "0", "pageNo": "1", "pageSize": "5"},
            key=config.crypto.key_bytes("home_key"),
            ok_code=200,
        )
        print(f"API 返回 code: {data.get('code')}")
        if data.get("code") == 200:
            print("Cookies 有效！")
            courses = data.get("result", {}).get("courseOpenDtos", [])
            print(f"课程数量: {len(courses)}")
            for c in courses[:5]:
                print(f"  - {c.get('courseName', '未知')}")
        else:
            print(f"Cookies 可能已过期: {data.get('message', '')}")
    except Exception as e:
        print(f"验证失败: {e}")

    session.close()
    print("\n测试完成！")
