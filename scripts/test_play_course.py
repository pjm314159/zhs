"""实际刷课测试：使用修正后的 ccCourseId"""
import sys
import time as _time
from pathlib import Path

from zhs.config import ConfigManager
from zhs.logger import setup_logging
from zhs.login import LoginManager
from zhs.session import ZhsSession
from zhs.zhidao.course import ZhidaoCourseManager
from zhs.zhidao.video import ZhidaoVideoPlayer


def main() -> None:
    config = ConfigManager().load()
    setup_logging(config)
    session = ZhsSession(config)

    # 1. 恢复 Cookie
    cookies_path = Path(".zhs/cookies.json")
    login_mgr = LoginManager(session, config)
    if not login_mgr.try_restore_cookies(cookies_path) or not session.uuid:
        print("Cookie 恢复失败")
        sys.exit(1)
    print(f"Cookie 恢复成功，UUID: {session.uuid}")

    # 2. 获取课程列表
    course_mgr = ZhidaoCourseManager(session)
    courses = course_mgr.get_course_list()
    print(f"\n共 {len(courses)} 门课程:")
    for i, c in enumerate(courses):
        print(f"  [{i}] {c.course_name}")

    # 3. 选择第一门课程
    course = courses[0]
    rac_id = course.secret
    print(f"\n--- 课程: {course.course_name} ---")

    # 4. 构建上下文
    ctx = course_mgr.get_context(rac_id)
    print(f"course_id: {ctx.course_id}, recruit_id: {ctx.course.recruit_id}")
    print(f"章节: {len(ctx.chapters)}, 视频: {len(ctx.videos)}")

    # 5. 列出视频状态
    unwatched = []
    for ch in ctx.chapters:
        for lesson in ch.video_lessons:
            for v in lesson.video_small_lessons:
                if v.watch_state != 1 and v.video_sec > 0:
                    unwatched.append(v)
                    status = f"⏳ {v.study_total_time}s/{v.video_sec}s"
                    print(f"  {ch.name[:15]} > {v.name[:25]} {status}")

    if not unwatched:
        print("所有视频已看完！")
        session.close()
        return

    # 6. 选择第一个未看完的视频，播放约 60 秒
    target = unwatched[0]
    print(f"\n--- 播放: {target.name} ---")
    print(f"  videoId={target.video_id}, 时长={target.video_sec}s, 已看={target.study_total_time}s")
    print(f"  course_id={ctx.course_id}")

    player = ZhidaoVideoPlayer(session, speed=1.0, end_threshold=0.91)
    target_time = min(target.study_total_time + 60, target.video_sec)
    player.end_threshold = min(target_time / max(target.video_sec, 1), 0.99)
    print(f"  将播放到: {target_time}s (threshold={player.end_threshold:.3f})")

    before_time = target.study_total_time
    start = _time.time()
    try:
        print("  开始播放...")
        player.play_video(rac_id, target.video_id, ctx)
        elapsed = _time.time() - start
        print(f"\n播放完成！耗时 {elapsed:.1f}s")
    except Exception as e:
        elapsed = _time.time() - start
        print(f"\n播放失败（{elapsed:.1f}s）: {e}")

    # 7. 验证进度
    _time.sleep(3)
    try:
        ctx2 = course_mgr.get_context(rac_id, force=True)
        v2 = ctx2.videos.get(target.video_id)
        if v2:
            print(f"\n播放前: studyTotalTime={before_time}s, watchState={target.watch_state}")
            print(f"播放后: studyTotalTime={v2.study_total_time}s, watchState={v2.watch_state}")
            if v2.study_total_time > before_time:
                print(f"✅ 进度上报成功！增加了 {v2.study_total_time - before_time}s")
            else:
                print("❌ 进度未更新")
        else:
            print("❌ 找不到视频")
    except Exception as e:
        print(f"验证失败: {e}")

    session.close()
    print("\n测试完成！")


if __name__ == "__main__":
    main()
