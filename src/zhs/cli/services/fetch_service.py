"""课程列表获取编排服务

从原 __main__.py 抽离的 _fetch_course_list 函数。
"""

import json
from typing import Any

from loguru import logger

from zhs.session import ZhsSession


def fetch_course_list(session: ZhsSession, fetch_type: str = "all") -> None:
    """获取课程列表"""
    from zhs.ai.course import AiCourseManager
    from zhs.hike.course import HikeCourseManager
    from zhs.utils.display import course_tag
    from zhs.utils.path import get_data_dir
    from zhs.zhidao.course import ZhidaoCourseManager

    zhidao_ids: list[dict[str, str]] = []
    hike_ids: list[dict[str, str]] = []
    ai_ids: list[dict[str, Any]] = []

    if fetch_type in ("all", "course"):
        zhidao_mgr = ZhidaoCourseManager(session)
        hike_mgr = HikeCourseManager(session)
        ai_mgr = AiCourseManager(session)

        zhidao_ids = [{"name": c.course_name, "id": c.secret} for c in zhidao_mgr.get_course_list()]
        hike_ids = [{"name": c.course_name, "id": str(c.course_id)} for c in hike_mgr.get_course_list()]
        ai_ids = [
            {
                "name": c.get("courseName", ""),
                "courseId": c.get("courseId"),
                "classId": c.get("classId"),
            }
            for c in ai_mgr.get_ai_course_list()
        ]

        print(f"{course_tag('zhidao')} {len(zhidao_ids)} 门课程")
        for c in zhidao_ids:
            print(f"  {c['name']} ({c['id']})")
        print(f"{course_tag('hike')} {len(hike_ids)} 门课程")
        for c in hike_ids:
            print(f"  {c['name']} ({c['id']})")
        print(f"{course_tag('ai')} {len(ai_ids)} 门课程")
        for c in ai_ids:
            print(f"  {c['name']} (courseId={c['courseId']}, classId={c['classId']})")

    exec_path = get_data_dir() / "execution.json"
    data = {"zhidao": zhidao_ids, "hike": hike_ids, "ai": ai_ids}
    with open(exec_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    logger.info(f"课程列表已保存到 {exec_path}")


__all__ = ["fetch_course_list"]
