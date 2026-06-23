"""真实测试：完整播放第二门课程的一个视频"""
import sys
import traceback
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

    # 使用第二门课程
    course = courses[1]  # 思想道德与法治
    rac_id = course.secret
    print(f"课程: {course.course_name}")

    ctx = course_mgr.get_context(rac_id)
    print(f"course_id={ctx.course_id}, recruit_id={ctx.course.recruit_id}")

    # 选第一个视频
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
        print("没有合适的视频")
        session.close()
        return

    print(f"\n目标: {target.name} ({target.study_total_time}s/{target.video_sec}s)")
    print(f"  videoId={target.video_id}, lessonId={target.lesson_id}")

    # 使用 1.5x 速度 + 禁用进度条
    player = ZhidaoVideoPlayer(session, speed=1.5, end_threshold=1.0, progressbar_view=False)
    before = target.study_total_time

    start = _time.time()
    try:
        print("开始播放...")
        player.play_video(rac_id, target.video_id, ctx)
        elapsed = _time.time() - start
        print(f"播放完成！耗时 {elapsed:.1f}s")
    except Exception as e:
        elapsed = _time.time() - start
        print(f"播放失败（{elapsed:.1f}s）: {e}")
        traceback.print_exc()

    # 验证
    _time.sleep(5)
    try:
        ctx2 = course_mgr.get_context(rac_id, force=True)
        v2 = ctx2.videos.get(target.video_id)
        if v2:
            print(f"\n前: {before}s, watchState={target.watch_state}")
            print(f"后: {v2.study_total_time}s/{v2.video_sec}s, watchState={v2.watch_state}")
            if v2.watch_state == 1:
                print("✅ 视频已标记为完成！")
            elif v2.study_total_time > before:
                print(f"⚠️ 进度增加了 {v2.study_total_time - before}s，但未标记完成")
            else:
                print("❌ 进度未更新")
    except Exception as e:
        print(f"验证失败: {e}")
        traceback.print_exc()

    session.close()


if __name__ == "__main__":
    main()
