"""检查视频列表 API 原始数据，诊断 videoSec=0"""
import json
import sys
from pathlib import Path

from zhs.config import ConfigManager
from zhs.login import LoginManager
from zhs.logger import setup_logging
from zhs.session import ZhsSession

config = ConfigManager().load()
setup_logging(config)
session = ZhsSession(config)

# 恢复 Cookie
cookies_path = Path(".zhs/cookies.json")
login_mgr = LoginManager(session, config)
if not login_mgr.try_restore_cookies(cookies_path) or not session.uuid:
    print("Cookie 恢复失败")
    sys.exit(1)

# 获取课程列表
from zhs.zhidao.course import ZhidaoCourseManager
course_mgr = ZhidaoCourseManager(session)
courses = course_mgr.get_course_list()
rac_id = courses[0].secret

# 获取原始视频列表数据
url = f"{session.urls.study}/gateway/t/v1/learning/videolist"
result = session.zhidao_query(url, {"recruitAndCourseId": rac_id})
data = result["data"]

# 找 videoSec=0 或没有 videoSec 的视频
for ch in data.get("videoChapterDtos", []):
    for lesson in ch.get("videoLessons", []):
        # 单视频课时
        if "videoId" in lesson and not lesson.get("videoSmallLessons"):
            vs = lesson.get("videoSec", "MISSING")
            print(f"[单视频] {lesson.get('name')} videoId={lesson.get('videoId')} videoSec={vs}")
            if vs == 0 or vs == "MISSING":
                print(json.dumps(lesson, indent=2, ensure_ascii=False))
                print("---")
        # 子视频
        for v in lesson.get("videoSmallLessons", []):
            vs = v.get("videoSec", "MISSING")
            if vs == 0 or vs == "MISSING":
                print(f"[子视频videoSec=0/MISSING] {v.get('name')} videoId={v.get('videoId')}")
                print(json.dumps(v, indent=2, ensure_ascii=False))
                print("---")

# 也检查 queryStudyInfo 返回数据
print("\n=== queryStudyInfo 数据 ===")
course_data = session.zhidao_query(
    f"{session.urls.study}/gateway/t/v1/learning/queryCourse",
    {"recruitAndCourseId": rac_id},
)
recruit_id = course_data["data"].get("recruitId", 0)

# 收集所有 lesson 和 video IDs
lesson_ids = []
video_ids = []
for ch in data.get("videoChapterDtos", []):
    for lesson in ch.get("videoLessons", []):
        lesson_ids.append(lesson["id"])
        for v in lesson.get("videoSmallLessons", []):
            if v.get("id"):
                video_ids.append(v["id"])

states = session.zhidao_query(
    f"{session.urls.study}/gateway/t/v1/learning/queryStuyInfo",
    {"lessonIds": lesson_ids, "lessonVideoIds": video_ids, "recruitId": recruit_id},
)
states_data = states["data"]
# 打印 lv 中 videoSec=0 对应的视频状态
print("lv states (sample):")
for k, v in list(states_data.get("lv", {}).items())[:3]:
    print(f"  {k}: {json.dumps(v, indent=2, ensure_ascii=False)}")
print("lesson states (sample):")
for k, v in list(states_data.get("lesson", {}).items())[:3]:
    print(f"  {k}: {json.dumps(v, indent=2, ensure_ascii=False)}")

session.close()
