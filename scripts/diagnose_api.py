"""诊断 -8 错误：对比 prelearningNote 返回的 studyTotalTime 和视频列表中的"""
import json
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

    # 第二门课程
    course = courses[1]
    rac_id = course.secret
    ctx = course_mgr.get_context(rac_id)

    # 找第一个未看视频
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

    print(f"视频: {target.name}")
    print(f"  视频列表中 studyTotalTime={target.study_total_time}s")

    # 调用 prelearningNote
    url = f"{session.urls.study}/gateway/t/v1/learning/prelearningNote"
    data = {
        "ccCourseId": ctx.course_id,
        "chapterId": target.chapter_id,
        "isApply": 1,
        "lessonId": target.lesson_id,
        "lessonVideoId": target.id,
        "recruitId": ctx.course.recruit_id or 0,
        "videoId": target.video_id,
    }
    result = session.zhidao_query(url, data)
    dto = result.get("data", {}).get("studiedLessonDto", {})
    server_time = dto.get("studyTotalTime", "N/A")
    print(f"  prelearningNote 返回 studyTotalTime={server_time}s")
    print(f"  差异: {server_time - target.study_total_time if isinstance(server_time, int) else 'N/A'}s")

    # 完整返回
    print(f"\n  prelearningNote 完整 studiedLessonDto:")
    print(json.dumps(dto, indent=2, ensure_ascii=False))

    session.close()


if __name__ == "__main__":
    main()
