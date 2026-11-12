"""知到课程管理

ZhidaoCourseManager 提供课程列表获取、上下文构建等功能。
所有 URL 从 UrlConfig 获取，密钥从 CryptoConfig 获取。
"""

import contextlib
import math
from typing import Any

from loguru import logger

from zhs.exceptions import ApiError
from zhs.session import ZhsSession
from zhs.zhidao.models import (
    CourseInfo,
    MapChapter,
    MapLesson,
    MapResource,
    VideoChapter,
    VideoSmallLesson,
    ZhidaoContext,
    ZhidaoCourse,
    extract_course_id,
)


def _format_learn_time(seconds: int) -> str:
    """秒数 → 学习时长字符串（HH:MM:SS）"""
    total = max(int(seconds), 0)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class ZhidaoCourseManager:
    """知到课程管理"""

    def __init__(self, session: ZhsSession) -> None:
        self._session = session
        self._context_cache: dict[str, ZhidaoContext] = {}
        self._courses: list[ZhidaoCourse] | None = None

    def get_course_list(self, force: bool = False) -> list[ZhidaoCourse]:
        """获取知到共享课程列表（分页）

        Args:
            force: 强制刷新，忽略实例内缓存
        """
        if self._courses is not None and not force:
            return self._courses

        url = f"{self._session.urls.base}/gateway/t/v1/student/course/share/queryShareCourseInfo"
        page = 1
        page_size = 5
        data: dict[str, Any] = {"status": 0, "pageNo": page, "pageSize": page_size}
        result = self._session.zhidao_query(url, data, key=self._session.crypto.key_bytes("home_key"), ok_code=200)
        total = result.get("result", {}).get("totalCount", 0)
        courses_data = result.get("result", {}).get("courseOpenDtos") or []
        courses = [ZhidaoCourse.model_validate(c) for c in courses_data]

        # 分页获取剩余课程
        total_pages = math.ceil(total / page_size)
        for p in range(2, total_pages + 1):
            data["pageNo"] = p
            result = self._session.zhidao_query(url, data, key=self._session.crypto.key_bytes("home_key"), ok_code=200)
            more = result.get("result", {}).get("courseOpenDtos") or []
            courses.extend(ZhidaoCourse.model_validate(c) for c in more)

        self._courses = courses
        return courses

    def find_course(self, course_id: int, *, require_recruit_id: bool = False) -> ZhidaoCourse | None:
        """按数字 courseId 查找课程（复用 get_course_list 缓存）

        Args:
            course_id: 数字 courseId，<= 0 时直接返回 None
            require_recruit_id: 为 True 时跳过没有 recruitId 的课程（作业/考试需要）

        Returns:
            匹配到的课程；未找到返回 None
        """
        if course_id <= 0:
            return None
        for c in self.get_course_list():
            if require_recruit_id and not c.recruit_id:
                continue
            # extract_course_id 返回 0 表示该课程取不到有效 ID，不参与匹配
            if extract_course_id(c) == course_id:
                return c
        return None

    def get_context(self, rac_id: str, force: bool = False) -> ZhidaoContext:
        """获取知到课程上下文

        Args:
            rac_id: recruitAndCourseId
            force: 强制更新缓存
        """
        if rac_id in self._context_cache and not force:
            return self._context_cache[rac_id]

        logger.info(f"Getting context for {rac_id}")

        # 1. 跨站登录
        self.gologin(rac_id)

        # 2. 获取课程信息
        course_data = self.query_course(rac_id)
        recruit_id: int = course_data.get("recruitId", 0)
        course_info_data = course_data.get("courseInfo", {})
        course_info = CourseInfo.model_validate(course_info_data) if course_info_data else None

        # 2.5 新版共享课（知识图谱）：树和视频资源走 aistudy / share-course-map
        map_ctx = self._build_map_context(rac_id, course_info, recruit_id)
        if map_ctx is not None:
            self._context_cache[rac_id] = map_ctx
            return map_ctx

        # 3. 获取章节/视频列表
        chapters_data = self.video_list(rac_id)
        course_id: int = chapters_data.get("courseId", 0)

        # 4. 处理章节树，构建视频字典
        chapters: list[VideoChapter] = []
        videos: dict[int, VideoSmallLesson] = {}
        lesson_ids: list[int] = []

        for ch_data in chapters_data.get("videoChapterDtos", []):
            chapter = VideoChapter.model_validate(ch_data)
            chapters.append(chapter)

            for lesson in chapter.video_lessons:
                lesson_ids.append(lesson.id)

                # 单视频课时：有 videoId 但没有 videoSmallLessons
                # 非视频课时（文档/测验等）接口返回 videoId=-1，不能当作视频
                if lesson.video_id > 0 and not lesson.video_small_lessons:
                    small = VideoSmallLesson(
                        video_id=lesson.video_id,
                        id=0,
                        name=lesson.name,
                        lesson_id=lesson.id,
                        chapter_id=chapter.id,
                        video_sec=lesson.video_sec,
                    )
                    lesson.video_small_lessons = [small]

                skipped = [v for v in lesson.video_small_lessons if v.video_id <= 0]
                if skipped:
                    logger.debug(f"Skip non-video entries in lesson {lesson.id}: {[v.name for v in skipped]}")
                lesson.video_small_lessons = [v for v in lesson.video_small_lessons if v.video_id > 0]
                for v in lesson.video_small_lessons:
                    v.chapter_id = chapter.id
                    videos[v.video_id] = v

        logger.info(f"{len(lesson_ids)} lessons, {len(videos)} videos")

        # 5. 获取学习状态
        video_ids = [v.id for v in videos.values() if v.id]
        if lesson_ids or video_ids:
            states = self.query_study_info(lesson_ids, video_ids, recruit_id)
            lv_states = states.get("lv", {})
            lesson_states = states.get("lesson", {})
            for v in videos.values():
                state = lv_states.get(str(v.id)) or lesson_states.get(str(v.lesson_id))
                if state:
                    v.watch_state = state.get("watchState", 0)
                    v.study_total_time = state.get("studyTotalTime", 0)

        # 6. 获取最近观看视频（非必须）
        self.query_user_recruit_id_last_video_id(recruit_id)

        # 7. 构建上下文
        course = ZhidaoCourse(
            secret=rac_id,
            course_name=course_info.name if course_info else "",
            course_info=course_info,
            recruit_id=recruit_id,
            has_habbit_score=course_data.get("hasHabbitScore"),
        )
        ctx = ZhidaoContext(
            course=course,
            chapters=chapters,
            videos=videos,
            course_id=course_id,
        )
        self._context_cache[rac_id] = ctx
        return ctx

    def _build_map_context(
        self,
        rac_id: str,
        course_info: CourseInfo | None,
        recruit_id: int,
    ) -> ZhidaoContext | None:
        """构建新版知识图谱课程上下文；旧版 videolist 课返回 None

        版本判断只看 queryCourse.courseInfo.courseMode（2 = 图谱课）。
        queryCourseMapInfo 对旧版课同样返回 mapStr，不能拿来判断；
        旧版课再调 kgCourseTreeInfoList 会得到 500「章节结构查询出错」。
        """
        if course_info is None or course_info.course_id <= 0 or recruit_id <= 0:
            return None
        if not course_info.is_map_course:
            logger.debug(f"课程 {course_info.course_id} courseMode={course_info.course_mode}，走旧版 videolist")
            return None

        map_info = self.query_course_map(course_info.course_id, recruit_id)
        map_str = str(map_info.get("mapStr") or "")
        map_hash = str(map_info.get("mapHashStr") or "")
        if not map_str or not map_hash:
            raise ApiError(-1, f"知识图谱课未返回 mapStr/mapHashStr: courseId={course_info.course_id}")

        # 已确认是图谱课：树取不到时回退旧流程只会得到 videoId=-1 的空目录，直接报错
        chapters = self.kg_course_tree(course_info.course_id, recruit_id)
        if not chapters:
            raise ApiError(-1, f"知识图谱课程树为空: courseId={course_info.course_id}")

        course = ZhidaoCourse(
            secret=rac_id,
            course_name=course_info.name,
            course_info=course_info,
            recruit_id=recruit_id,
            course_id=course_info.course_id,
        )
        node_count = sum(len(chapter.leaf_nodes()) for chapter in chapters)
        logger.info(f"知识图谱课程: {len(chapters)} chapters, {node_count} nodes")
        return ZhidaoContext(
            course=course,
            chapters=[],
            videos={},
            course_id=course_info.course_id,
            mode="map",
            map_chapters=chapters,
            map_str=map_str,
            map_hash=map_hash,
        )

    def query_course_map(self, course_id: int, recruit_id: int) -> dict[str, Any]:
        """课程图谱信息（aistudy），返回 data（含 mapStr/mapHashStr/coruseType）"""
        url = f"{self._session.urls.aistudy}/gateway/t/v1/learning/queryCourseMapInfo"
        result = self._session.aistudy_query(url, {"courseId": course_id, "recruitId": recruit_id})
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    def kg_course_tree(self, course_id: int, recruit_id: int) -> list[MapChapter]:
        """知识图谱课程树（aistudy）"""
        url = f"{self._session.urls.aistudy}/gateway/t/v1/learning/kgCourseTreeInfoList"
        result = self._session.aistudy_query(url, {"courseId": course_id, "recruitId": recruit_id})
        raw = result.get("data") or []
        if not isinstance(raw, list):
            return []

        chapters: list[MapChapter] = []
        failed = 0
        for item in raw:
            try:
                chapters.append(MapChapter.model_validate(item))
            except Exception as e:
                failed += 1
                logger.warning(f"跳过无法解析的知识图谱章节: {e}")
        if raw and not chapters:
            raise ApiError(-1, f"知识图谱章节全部无法解析: courseId={course_id}, count={failed}")
        return chapters

    def query_node_resources(self, lesson: MapLesson) -> list[MapResource]:
        """节点下的资源列表（share-course-map，明文 JSON）"""
        url = f"{self._session.urls.share_map}/gateway/t/node/queryNodeDescription"
        result = self._session.map_post(url, {"idHash": lesson.id_hash, "idStr": lesson.id_str})
        data = result.get("data") or {}
        raw = data.get("nodeRespResourceVos") or []
        return [MapResource.model_validate(item) for item in raw]

    def pre_learning_load(
        self,
        *,
        course_id: int,
        recruit_id: int,
        chapter_hash: str,
        lesson_hash: str,
        data_id: str,
        lesson_video_id: str = "",
    ) -> bool:
        """开始学习前置调用（aistudy）

        必须在首次 saveUserStudyProcess 之前调用，否则服务端没有学习记录，
        会返回 NPE 或 2021「多端观看异常」。
        课件要带上知识点节点的 lessonVideoId，否则学习记录对不上节点。
        """
        url = f"{self._session.urls.aistudy}/gateway/t/v1/learning/preLearningLoad"
        payload: dict[str, Any] = {
            "courseId": course_id,
            "recruitId": recruit_id,
            "chapterId": chapter_hash,
            "lessonId": lesson_hash,
            "dataId": data_id,
        }
        if lesson_video_id:
            payload["lessonVideoId"] = lesson_video_id
        result = self._session.aistudy_query(url, payload)
        return bool(result.get("data"))

    def query_user_study_info(
        self,
        *,
        course_id: int,
        recruit_id: int,
        lesson_hash: str,
        data_id: str,
        lesson_video_id: str = "",
    ) -> dict[str, Any]:
        """查询某节点、某资源的学习记录（aistudy）

        进度是按「节点 + dataId」分别记录的；同一资源挂在多个节点下时，
        每个节点有独立的 learnTime/state。课件查询要带 lessonVideoId。

        Returns:
            data: {knowledgeHashId, knowledgeStrId, dataId, state, learnTime}
                  state: 1=学习中, 2=已完成
        """
        url = f"{self._session.urls.aistudy}/gateway/t/v1/learning/queryUserStudyInfo"
        payload: dict[str, Any] = {
            "courseId": course_id,
            "recruitId": recruit_id,
            "lessonId": lesson_hash,
            "dataId": data_id,
        }
        if lesson_video_id:
            payload["lessonVideoId"] = lesson_video_id
        # 不吞 ApiError：业务码拒绝不能当成“没学过”，否则会从 0 重播已完成视频。
        # 响应成功但 data 为空，才表示该节点尚未学习。
        result = self._session.aistudy_query(url, payload)
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    def query_last_knowledge(self, course_id: int, recruit_id: int) -> dict[str, Any]:
        """上次学习到的节点（用于续播），失败时返回空字典"""
        if course_id <= 0 or recruit_id <= 0:
            return {}
        url = f"{self._session.urls.aistudy}/gateway/t/v1/learning/queryUserRecruitIdLastKnowledgeInfo"
        try:
            result = self._session.aistudy_query(url, {"courseId": course_id, "recruitId": recruit_id})
        except ApiError as e:
            logger.debug(f"上次学习节点获取失败: {e}")
            return {}
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    def save_study_process(
        self,
        *,
        recruit_id: int,
        chapter_hash: str,
        lesson_hash: str,
        data_id: str,
        play_times: int,
        total_time: int,
        learn_time: int,
        data_type: int = 1,
        lesson_video_id: str = "",
    ) -> dict[str, Any]:
        """上报学习进度（aistudy，明文 JSON）

        Args:
            play_times: 本次上报的学习秒数。服务端以此累计 learnTime
                （实测 playTimes=30 则 learnTime +30），必须传本次新增秒数，
                不能只传自增计数。视频传本次新增秒；课件传 0。
            data_type: 1=视频，2=PPT/课件。课件必须传 2，否则不会标完成。
            lesson_video_id: 网页抓包里是知识点节点 hash（nodeUidHash）。
                视频心跳传空也能累计；课件完成必须带上，否则记不到对应节点。

        Returns:
            data: {state, submitSuccess, learnTime, totalTime}
        """
        url = f"{self._session.urls.aistudy}/gateway/t/v1/learning/saveUserStudyProcess"
        payload: dict[str, Any] = {
            "recruitId": recruit_id,
            "chapterId": chapter_hash,
            "lessonId": lesson_hash,
            "lessonVideoId": lesson_video_id,
            "dataId": data_id,
            "dataType": data_type,
            "playTimes": play_times,
            "studyTotalTime": "" if data_type == 2 else str(total_time),
            "learnTime": "" if data_type == 2 else _format_learn_time(learn_time),
            "sourceType": 1,
        }
        result = self._session.map_post(url, payload)
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    def gologin(self, rac_id: str) -> None:
        """跨站登录（返回 HTML，不解析 JSON）"""
        url = f"{self._session.urls.study}/login/gologin"
        params = {"fromurl": f"https://studyh5.zhihuishu.com/videoStudy.html#/studyVideo?recruitAndCourseId={rac_id}"}
        client = self._session._get_client()
        client.get(url, params=params)

    def query_course(self, rac_id: str) -> dict[str, Any]:
        """查询课程信息，返回原始 data（含 recruitId、courseInfo 等）"""
        url = f"{self._session.urls.study}/gateway/t/v1/learning/queryCourse"
        result = self._session.zhidao_query(url, {"recruitAndCourseId": rac_id})
        data: dict[str, Any] = result["data"]
        return data

    def video_list(self, rac_id: str) -> dict[str, Any]:
        """获取章节/视频列表"""
        url = f"{self._session.urls.study}/gateway/t/v1/learning/videolist"
        result = self._session.zhidao_query(url, {"recruitAndCourseId": rac_id})
        data: dict[str, Any] = result["data"]
        return data

    def query_study_info(self, lesson_ids: list[int], video_ids: list[int], recruit_id: int) -> dict[str, Any]:
        """查询学习状态"""
        url = f"{self._session.urls.study}/gateway/t/v1/learning/queryStuyInfo"
        data = {"lessonIds": lesson_ids, "lessonVideoIds": video_ids, "recruitId": recruit_id}
        result = self._session.zhidao_query(url, data)
        resp: dict[str, Any] = result["data"]
        return resp

    def query_user_recruit_id_last_video_id(self, recruit_id: int) -> None:
        """获取最近观看视频"""
        url = f"{self._session.urls.study}/gateway/t/v1/learning/queryUserRecruitIdLastVideoId"
        with contextlib.suppress(Exception):
            self._session.zhidao_query(url, {"recruitId": recruit_id})
