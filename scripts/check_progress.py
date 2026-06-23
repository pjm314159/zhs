"""验证视频进度"""
import sys
from pathlib import Path

from zhs.config import ConfigManager
from zhs.login import LoginManager
from zhs.logger import setup_logging
from zhs.session import ZhsSession
from zhs.zhidao.course import ZhidaoCourseManager


def main() -> None:
    config = ConfigManager().load()
    setup_logging(config)
    session = ZhsSession(config)

    cookies_path = Path(".zhs/cookies.json")
    login_mgr = LoginManager(session, config)
    if not login_mgr.try_restore_cookies(cookies_path) or not session.uuid:
        print("Cookie 恢复失败")
        sys.exit(1)

    course_mgr = ZhidaoCourseManager(session)
    courses = course_mgr.get_course_list()

    for c in courses:
        print(f"\n=== {c.course_name} ===")
        ctx = course_mgr.get_context(c.secret, force=True)
        print(f"course_id={ctx.course_id}, recruit_id={ctx.course.recruit_id}")

        watched = 0
        total = 0
        for ch in ctx.chapters:
            for lesson in ch.video_lessons:
                for v in lesson.video_small_lessons:
                    if v.video_sec > 0:
                        total += 1
                        pct = v.study_total_time / v.video_sec * 100
                        status = "✅" if v.watch_state == 1 else f"{pct:.0f}%"
                        print(f"  {v.name[:30]:30s} {v.study_total_time:5d}s/{v.video_sec:5d}s {status}")
                        if v.watch_state == 1:
                            watched += 1

        print(f"  完成: {watched}/{total}")

    session.close()


if __name__ == "__main__":
    main()
