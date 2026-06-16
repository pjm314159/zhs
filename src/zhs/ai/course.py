"""AI 课程管理"""

import asyncio
import time
from random import randint
from typing import Any

from loguru import logger

from zhs.ai.models import AiCourseInfo, ExamInfo, Resource
from zhs.ai.video import AiVideoPlayer
from zhs.config import AIConfig
from zhs.session import ZhsSession
from zhs.utils.display import course_tag, msg_done, msg_skip, tree_print


class AiCourseManager:
    """AI 课程管理

    管理 AI 课程的知识点学习、资源完成、视频播放和作业。
    """

    def __init__(self, session: ZhsSession) -> None:
        self._session = session

    def _ai_query(self, url: str, data: dict[str, Any], content_type: str = "json") -> dict[str, Any]:
        """AI 课程 API 查询（使用 ai_key，默认 JSON）"""
        return self._session.zhidao_query(
            url, data, key=self._session.crypto.key_bytes("ai_key"), ok_code=200, content_type=content_type
        )

    def get_ai_course_list(self) -> list[dict[str, Any]]:
        """获取 AI 课程列表"""
        url = f"{self._session.urls.base}/gateway/t/v1/student/queryStudentAICourseList"
        data = {"status": 3}
        try:
            result = self._session.zhidao_query(url, data, key=self._session.crypto.key_bytes("home_key"), ok_code=0)
            rt = result.get("rt", [])
            return rt if isinstance(rt, list) else []
        except Exception as e:
            logger.error(f"获取 AI 课程列表失败: {e}")
            return []

    def get_knowledge_points(self, course_id: int, class_id: int) -> AiCourseInfo:
        """获取知识点列表"""
        url = f"{self._session.urls.ai}/run/gateway/t/stu/knowledge-study/course-basic"
        data = {"courseId": course_id, "classId": class_id}
        result = self._ai_query(url, data)
        return AiCourseInfo.model_validate(result["data"])

    def list_knowledge_resources(self, course_id: int, class_id: int, knowledge_id: int) -> list[Resource]:
        """获取知识点资源列表"""
        url = f"{self._session.urls.ai}/run/gateway/t/stu/resources/list-knowledge-resource"
        data = {"courseId": course_id, "classId": class_id, "knowledgeId": knowledge_id}
        result = self._ai_query(url, data)
        raw_list = result["data"].get("resourceList", [])
        return [Resource.model_validate(r) for r in raw_list]

    def complete_resource(self, course_id: int, class_id: int, knowledge_id: int, resources_uid: int) -> None:
        """完成资源"""
        url = f"{self._session.urls.ai}/run/gateway/t/stu/studyRecord/completed"
        data = {
            "courseId": course_id,
            "classId": class_id,
            "knowledgeId": knowledge_id,
            "resourcesUid": resources_uid,
            "watchUId": 1,
        }
        self._ai_query(url, data)

    def query_homework(self, course_id: int, class_id: int, knowledge_id: int) -> ExamInfo | None:
        """查询作业信息"""
        url = f"{self._session.urls.ai}/run/gateway/t/stu/exam/questions-paper"
        data = {
            "scMapId": course_id,
            "courseId": class_id,
            "classId": class_id,
            "knowledgeId": knowledge_id,
        }
        try:
            result = self._ai_query(url, data)
            return ExamInfo.model_validate(result["data"])
        except Exception as e:
            logger.error(f"查询作业信息失败: {e}")
            return None

    def _process_resource(
        self,
        course_id: int,
        class_id: int,
        knowledge_id: int,
        resource: Resource,
        video_player: AiVideoPlayer,
        ppts: list[dict[str, str]] | None = None,
    ) -> None:
        """处理单个资源"""
        ppts = ppts if ppts is not None else []
        detail = resource.resources_detail
        r_type = detail.resources_type
        r_dist = detail.resources_distribute_type

        # 已完成的资源
        if resource.study_status == 1:
            # 已完成的 PPT 仍收集 URL
            if r_type == 1 and r_dist == 4 and detail.resources_url:
                ppts.append({"name": detail.resources_name, "url": detail.resources_url})
            return

        # 随机延迟（模拟人类行为）
        time.sleep(randint(1, 10) * 0.2)

        # 未完成的资源
        if r_type == 2 and r_dist == 1:
            # 文本
            self.complete_resource(course_id, class_id, knowledge_id, detail.resources_uid)
        elif r_type == 1 and r_dist == 4:
            # PPT
            self.complete_resource(course_id, class_id, knowledge_id, detail.resources_uid)
            if detail.resources_url:
                ppts.append({"name": detail.resources_name, "url": detail.resources_url})
        elif r_type == 1 and r_dist == 3:
            # 视频
            video_player.play_video(course_id, class_id, detail.resources_file_id, knowledge_id)
        elif r_type == 2 and r_dist == 2:
            # 课程视频
            video_player.play_video(course_id, class_id, detail.resources_file_id, knowledge_id)
        else:
            # 其他类型
            self.complete_resource(course_id, class_id, knowledge_id, detail.resources_uid)

    def _should_do_homework(self, exam: ExamInfo, tried: int, no_homework: bool) -> bool:
        """判断是否应做作业"""
        if no_homework:
            return False
        if exam.mastery_score > 90:
            return False
        return not (exam.mastery_score < 30 and tried > 4)

    def run_course(
        self,
        course_id: int,
        class_id: int,
        ai_config: AIConfig,
        no_homework: bool = False,
        speed: float = 1.5,
    ) -> None:
        """执行完整 AI 课程学习流程"""
        from zhs.ai.homework import HomeworkCtx
        from zhs.ai.ppt import PptConverter

        # 获取知识点
        course_info = self.get_knowledge_points(course_id, class_id)
        logger.info(f"开始学习 AI 课程: {course_info.course_name}")
        tree_print(f"{course_tag('ai')} 课程: {course_info.course_name}", enabled=True)

        # 创建视频播放器
        video_player = AiVideoPlayer(self._session, speed=speed)

        ppt_conf = getattr(ai_config, "ppt_processing", {})
        moonshot_key = getattr(ai_config, "moonshot_api_key", "")

        for theme in course_info.cake_theme_list:
            logger.info(f"主题: {theme.theme_name}")
            tree_print(f"主题: {theme.theme_name}", depth=1, enabled=True)

            for knowledge in theme.knowledge_list:
                ppts: list[dict[str, str]] = []

                if knowledge.study_progress < 100:
                    tree_print(f"知识点: {knowledge.knowledge_name}", depth=2, enabled=True)
                    # 未完成的知识点
                    try:
                        resources = self.list_knowledge_resources(course_id, class_id, knowledge.knowledge_id)
                    except Exception as e:
                        logger.error(f"获取资源列表失败: {e}")
                        continue

                    for resource in resources:
                        try:
                            self._process_resource(
                                course_id, class_id, knowledge.knowledge_id, resource, video_player, ppts
                            )
                        except Exception as e:
                            logger.error(f"处理资源失败: {e}")

                    logger.info(f"知识点完成: {knowledge.knowledge_name}")
                    tree_print(msg_done(f"完成: {knowledge.knowledge_name}"), depth=3, enabled=True)
                else:
                    # 已完成的知识点，仍收集 PPT
                    tree_print(msg_skip(f"跳过(已完成): {knowledge.knowledge_name}"), depth=2, enabled=True)
                    if ppt_conf and moonshot_key:
                        try:
                            resources = self.list_knowledge_resources(course_id, class_id, knowledge.knowledge_id)
                            for resource in resources:
                                detail = resource.resources_detail
                                if (
                                    detail.resources_type == 1
                                    and detail.resources_distribute_type == 4
                                    and detail.resources_url
                                ):
                                    ppts.append(
                                        {
                                            "name": detail.resources_name,
                                            "url": detail.resources_url,
                                        }
                                    )
                        except Exception as e:
                            logger.error(f"获取已完成知识点资源失败: {e}")
                    logger.info(f"知识点已完成: {knowledge.knowledge_name}")

                # 作业循环
                tried = 0
                while True:
                    exam = self.query_homework(course_id, class_id, knowledge.knowledge_id)
                    if exam is None or not exam.paper_id:
                        break

                    if not self._should_do_homework(exam, tried, no_homework):
                        break

                    tried += 1

                    # PPT 转文本
                    reference_materials: list[dict[str, str]] = []
                    if ppts:
                        converter = PptConverter(
                            api_key=moonshot_key,
                            base_url=getattr(ai_config, "base_url", "https://api.moonshot.cn/v1"),
                        )
                        for ppt in ppts:
                            try:
                                content = converter.convert(ppt["url"])
                                if content:
                                    ppt["content"] = content
                                    reference_materials.append(
                                        {
                                            "name": ppt["name"],
                                            "url": ppt["url"],
                                            "content": content,
                                        }
                                    )
                            except Exception as e:
                                logger.error(f"PPT 转换失败: {e}")

                    # 执行作业
                    homework_ctx = HomeworkCtx(
                        session=self._session,
                        course_id=course_id,
                        knowledge_id=knowledge.knowledge_id,
                        exam_test_id=exam.exam_test_id,
                        exam_paper_id=exam.paper_id,
                        ai_config=ai_config,
                        op_extra={
                            "courseName": course_info.course_name,
                            "theme": theme.theme_name,
                            "knowledgePoint": knowledge.knowledge_name,
                        },
                    )

                    try:
                        is_success, correct, total = asyncio.run(
                            homework_ctx.start(reference_materials=reference_materials)
                        )
                        logger.info(f"作业结果: {correct}/{total}")
                    except Exception as e:
                        logger.error(f"作业失败: {e}")

                    time.sleep(2)

            # 主题间随机延迟
            time.sleep(randint(1, 2))
