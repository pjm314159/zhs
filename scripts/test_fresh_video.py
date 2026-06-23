"""测试全新视频的刷课（从未看过的视频）"""
import sys
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
    rac_id = courses[0].secret
    print(f"课程: {courses[0].course_name}")

    # 3. 构建上下文
    ctx = course_mgr.get_context(rac_id)

    # 4. 找一个从未看过的视频（studyTotalTime=0, videoSec>0）
    target_video = None
    for ch in ctx.chapters:
        for lesson in ch.video_lessons:
            for v in lesson.video_small_lessons:
                if v.watch_state != 1 and v.study_total_time == 0 and v.video_sec > 0:
                    target_video = v
                    break
            if target_video:
                break
        if target_video:
            break

    if not target_video:
        print("没有未看过的视频")
        session.close()
        return

    print(f"\n目标视频: {target_video.name}")
    print(f"  videoId={target_video.video_id}, 时长={target_video.video_sec}s, 已看={target_video.study_total_time}s")

    # 5. 播放约 90 秒
    player = ZhidaoVideoPlayer(session, speed=1.0, end_threshold=0.91)
    target_time = 90
    player.end_threshold = min(target_time / max(target_video.video_sec, 1), 0.99)
    print(f"  将播放到: {target_time}s (threshold={player.end_threshold:.3f})")

    before_time = target_video.study_total_time
    import time as _time_mod
    start = _time_mod.time()
    try:
        print("  开始播放...")
        player.play_video(rac_id, target_video.video_id, ctx)
        elapsed = _time_mod.time() - start
        print(f"\n视频播放完成！耗时 {elapsed:.1f}s")
    except Exception as e:
        elapsed = _time_mod.time() - start
        print(f"\n播放失败（{elapsed:.1f}s）: {e}")
        import traceback
        traceback.print_exc()

    # 6. 验证进度
    import time as _time
    _time.sleep(3)
    try:
        ctx2 = course_mgr.get_context(rac_id, force=True)
        v2 = ctx2.videos.get(target_video.video_id)
        if v2:
            print(f"\n播放前: studyTotalTime={before_time}s, watchState={target_video.watch_state}")
            print(f"播放后: studyTotalTime={v2.study_total_time}s, watchState={v2.watch_state}")
            if v2.study_total_time > before_time:
                print(f"✅ 进度上报成功！增加了 {v2.study_total_time - before_time}s")
            else:
                print("❌ 进度未更新")
    except Exception as e:
        print(f"验证失败: {e}")

    session.close()


if __name__ == "__main__":
    main()
