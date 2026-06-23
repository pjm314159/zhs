"""快速刷课测试：播放 30 秒验证"""
import sys
import time as _time
from pathlib import Path

from zhs.config import ConfigManager
from zhs.login import LoginManager
from zhs.logger import setup_logging
from zhs.session import ZhsSession
from zhs.zhidao.course import ZhidaoCourseManager
from zhs.zhidao.video import ZhidaoVideoPlayer


def main() -> None:
    config = ConfigManager().load()
    setup_logging(config)
    session = ZhsSession(config)

    cookies_path = Path(".zhs/cookies.json")
    login_mgr = LoginManager(session, config)
    if not login_mgr.try_restore_cookies(cookies_path) or not session.uuid:
        print("Cookie 恢复失败")
        sys.exit(1)
    print(f"Cookie OK, UUID: {session.uuid}")

    course_mgr = ZhidaoCourseManager(session)
    courses = course_mgr.get_course_list()
    print(f"课程: {courses[0].course_name}")

    ctx = course_mgr.get_context(courses[0].secret)
    print(f"course_id={ctx.course_id}, recruit_id={ctx.course.recruit_id}")

    # 找一个未看完的视频
    target = None
    for ch in ctx.chapters:
        for lesson in ch.video_lessons:
            for v in lesson.video_small_lessons:
                if v.watch_state != 1 and v.video_sec > 0:
                    target = v
                    break
            if target:
                break
        if target:
            break

    if not target:
        print("所有视频已看完！")
        session.close()
        return

    print(f"\n播放: {target.name}")
    print(f"  videoId={target.video_id}, 时长={target.video_sec}s, 已看={target.study_total_time}s")

    player = ZhidaoVideoPlayer(session, speed=1.0, end_threshold=0.91)
    target_time = min(target.study_total_time + 35, target.video_sec)
    player.end_threshold = min(target_time / max(target.video_sec, 1), 0.99)
    print(f"  播放到: {target_time}s")

    before_time = target.study_total_time
    start = _time.time()
    try:
        player.play_video(courses[0].secret, target.video_id, ctx)
        print(f"\n播放完成！耗时 {_time.time() - start:.1f}s")
    except Exception as e:
        print(f"\n播放失败: {e}")

    # 验证进度
    _time.sleep(3)
    try:
        ctx2 = course_mgr.get_context(courses[0].secret, force=True)
        v2 = ctx2.videos.get(target.video_id)
        if v2:
            print(f"前: {before_time}s, 后: {v2.study_total_time}s, state={v2.watch_state}")
            if v2.study_total_time > before_time:
                print(f"✅ 成功！增加 {v2.study_total_time - before_time}s")
            else:
                print("❌ 进度未更新")
    except Exception as e:
        print(f"验证失败: {e}")

    session.close()


if __name__ == "__main__":
    main()
