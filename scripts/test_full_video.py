"""完整播放测试：播放一个视频直到完成，结果写入文件"""
import time as _time
from pathlib import Path

from zhs.config import ConfigManager
from zhs.logger import setup_logging
from zhs.login import LoginManager
from zhs.session import ZhsSession
from zhs.zhidao.course import ZhidaoCourseManager
from zhs.zhidao.video import ZhidaoVideoPlayer


def main() -> None:
    result_file = Path(".zhs/test_result.txt")
    config = ConfigManager().load()
    setup_logging(config)
    session = ZhsSession(config)

    cookies_path = Path(".zhs/cookies.json")
    login_mgr = LoginManager(session, config)
    if not login_mgr.try_restore_cookies(cookies_path) or not session.uuid:
        result_file.write_text("FAIL: Cookie restore failed\n")
        return

    course_mgr = ZhidaoCourseManager(session)
    courses = course_mgr.get_course_list()
    course = courses[0]
    rac_id = course.secret

    ctx = course_mgr.get_context(rac_id)

    # 选 "统筹发展和安全" (403s)
    target_id = 86987539
    video = ctx.videos.get(target_id)
    if not video:
        result_file.write_text("FAIL: Video not found\n")
        session.close()
        return

    before = video.study_total_time
    before_state = video.watch_state

    player = ZhidaoVideoPlayer(session, speed=1.5, end_threshold=1.0, progressbar_view=False)

    start = _time.time()
    error = None
    try:
        player.play_video(rac_id, target_id, ctx)
    except Exception as e:
        error = str(e)

    elapsed = _time.time() - start

    # 验证
    _time.sleep(5)
    ctx2 = course_mgr.get_context(rac_id, force=True)
    v2 = ctx2.videos.get(target_id)

    result = []
    result.append(f"Video: {video.name}")
    result.append(f"Before: {before}s/{video.video_sec}s, state={before_state}")
    result.append(f"After: {v2.study_total_time}s/{v2.video_sec}s, state={v2.watch_state}" if v2 else "After: not found")
    result.append(f"Elapsed: {elapsed:.1f}s")
    result.append(f"Error: {error}" if error else "Error: None")
    if v2 and v2.watch_state == 1:
        result.append("RESULT: SUCCESS - Video completed!")
    elif v2 and v2.study_total_time > before:
        result.append(f"RESULT: PARTIAL - Progress +{v2.study_total_time - before}s but not completed")
    else:
        result.append("RESULT: FAIL - No progress")

    result_file.write_text("\n".join(result) + "\n")
    session.close()


if __name__ == "__main__":
    main()
