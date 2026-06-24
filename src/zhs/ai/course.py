"""AI 课程管理"""

import time
from random import randint
from typing import Any

from loguru import logger

from zhs.ai.models import AiCourseInfo, ExamInfo, Resource
from zhs.ai.video import AiVideoPlayer
from zhs.config import AIConfig, HomeworkConfig, VideoConfig
from zhs.reporter import ConsoleReporter, ProgressReporter
from zhs.session import ZhsSession
from zhs.utils.display import (
    _C,
    course_tag,
    msg_done,
    msg_error,
    msg_info,
    msg_skip,
    progress_bar,
    styled,
)


class AiCourseManager:
    """AI 课程管理

    管理 AI 课程的知识点学习、资源完成、视频播放和作业。
    """

    def __init__(self, session: ZhsSession, reporter: ProgressReporter | None = None) -> None:
        self._session = session
        self._reporter = reporter or ConsoleReporter()

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

    def get_exam_tasks(self, course_id: str) -> list[dict[str, Any]]:
        """获取课程考试任务列表（taskList，ai_key 加密）

        只返回 taskType=1 的任务（请求参数 status=0 已筛选未完成）。
        """
        url = f"{self._session.urls.ai_task}/student/gateway/t/task/taskList"
        data = {
            "courseId": course_id,
            "taskType": 1,
            "taskName": "",
            "status": 0,
        }
        try:
            result = self._session.ai_task_query(url, data)
            tasks = result.get("data", [])
            if not isinstance(tasks, list):
                return []
            # 只返回 taskType=1 的任务（请求参数 status=0 已筛选未完成）
            return [t for t in tasks if t.get("taskType") == 1]
        except Exception as e:
            logger.error(f"获取考试任务列表失败: {e}")
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
        learn_optional: bool = False,
        threshold: int = 100,
    ) -> None:
        """处理单个资源

        Args:
            learn_optional: 是否处理选学资源（resourcesSyncType != 1）
            threshold: 视频完成阈值（0-100）
        """
        ppts = ppts if ppts is not None else []
        detail = resource.resources_detail
        r_type = detail.resources_type
        r_dist = detail.resources_distribute_type

        # 选学资源过滤（已完成的 PPT 仍收集 URL 作为参考资料）
        is_optional = detail.resources_sync_type != 1
        if is_optional and not learn_optional:
            if resource.study_status == 1 and r_type == 1 and r_dist == 4 and detail.resources_url:
                ppts.append({"name": detail.resources_name, "url": detail.resources_url})
                logger.debug(f"append ppt {detail.resources_name}")
            return

        # 已完成的资源
        if resource.study_status == 1:
            # 已完成的 PPT 仍收集 URL
            if r_type == 1 and r_dist == 4 and detail.resources_url:
                ppts.append({"name": detail.resources_name, "url": detail.resources_url})
                logger.debug(f"append ppt {detail.resources_name}")
            return

        # 随机延迟（模拟人类行为）
        time.sleep(randint(1, 10) * 0.2)

        # 未完成的资源
        if r_type == 2 and r_dist == 1:
            # 文本
            self._reporter.tree_print(f"完成文本: {detail.resources_name}", depth=3, enabled=True)
            self.complete_resource(course_id, class_id, knowledge_id, detail.resources_uid)
        elif r_type == 1 and r_dist == 4:
            # PPT
            self._reporter.tree_print(f"完成PPT: {detail.resources_name}", depth=3, enabled=True)
            self.complete_resource(course_id, class_id, knowledge_id, detail.resources_uid)
            if detail.resources_url:
                ppts.append({"name": detail.resources_name, "url": detail.resources_url})
        elif r_type == 1 and r_dist == 3:
            # 视频
            self._reporter.tree_print(f"播放视频: {detail.resources_name}", depth=3, enabled=True)
            video_player.play_video(
                course_id,
                class_id,
                detail.resources_file_id,
                knowledge_id,
                schedule=resource.schedule,
                threshold=threshold,
            )
        elif r_type == 2 and r_dist == 2:
            # 课程视频
            self._reporter.tree_print(f"播放课程视频: {detail.resources_name}", depth=3, enabled=True)
            video_player.play_video(
                course_id,
                class_id,
                detail.resources_file_id,
                knowledge_id,
                schedule=resource.schedule,
                threshold=threshold,
            )
        else:
            # 其他类型
            self._reporter.tree_print(f"完成资源: {detail.resources_name}", depth=3, enabled=True)
            self.complete_resource(course_id, class_id, knowledge_id, detail.resources_uid)

    def _should_do_homework(
        self, exam: ExamInfo, tried: int, no_homework: bool, homework_config: HomeworkConfig
    ) -> bool:
        """判断是否应做作业"""
        if no_homework:
            return False
        if exam.mastery_score > homework_config.ai_homework_threshold:
            return False
        return not (exam.mastery_score < 30 and tried > 4)

    def _collect_completed_ppts(
        self, course_id: int, class_id: int, knowledge_id: int, ppts: list[dict[str, str]]
    ) -> None:
        """收集已完成 PPT 的 URL 作为作业参考资料"""
        try:
            resources = self.list_knowledge_resources(course_id, class_id, knowledge_id)
            for resource in resources:
                if resource.study_status == 1:
                    detail = resource.resources_detail
                    if detail.resources_type == 1 and detail.resources_distribute_type == 4 and detail.resources_url:
                        ppts.append({"name": detail.resources_name, "url": detail.resources_url})
        except Exception as e:
            logger.error(f"获取资源列表失败: {e}")

    def run_course(
        self,
        course_id: int,
        class_id: int,
        ai_config: AIConfig,
        homework_config: HomeworkConfig,
        video_config: VideoConfig | None = None,
        no_homework: bool = False,
        speed: float = 1.5,
        learn_optional: bool = False,
    ) -> None:
        """执行 AI 课程学习流程

        Args:
            video_config: 视频配置（含 ai_threshold）
            no_homework: 仅刷知识点，不做作业（play 模式）；否则只做作业（homework 模式）
            learn_optional: 是否学习选学资源（resourcesSyncType != 1）
        """
        # 获取知识点
        course_info = self.get_knowledge_points(course_id, class_id)
        logger.info(f"开始学习 AI 课程: {course_info.course_name}")
        self._reporter.print()
        self._reporter.print(styled("=" * 60, _C.DIM))
        self._reporter.print(f"{course_tag('ai')} 课程: {styled(course_info.course_name, _C.BOLD, _C.BRIGHT_MAGENTA)}")
        self._reporter.print(styled("=" * 60, _C.DIM))

        video_player = AiVideoPlayer(self._session, speed=speed)

        _vc = video_config or VideoConfig()
        threshold = _vc.ai_threshold

        for theme in course_info.cake_theme_list:
            logger.info(f"主题: {theme.theme_name}")
            self._reporter.print()
            self._reporter.tree_print(f"主题: {styled(theme.theme_name, _C.CYAN)}", depth=1, enabled=True)

            for knowledge in theme.knowledge_list:
                if no_homework:
                    # play 模式：只刷知识点，不查询作业
                    self._run_play_only(course_id, class_id, knowledge, video_player, learn_optional, threshold)
                else:
                    # homework 模式：只做作业，不刷视频
                    self._run_homework_only(
                        course_id,
                        class_id,
                        knowledge,
                        theme,
                        course_info,
                        ai_config,
                        homework_config,
                    )

            # 主题间随机延迟
            time.sleep(randint(1, 2))

        self._reporter.print()
        self._reporter.print(msg_done(f"课程完成: {course_info.course_name}"))
        self._reporter.print(styled("=" * 60, _C.DIM))

    def _run_play_only(
        self,
        course_id: int,
        class_id: int,
        knowledge: Any,
        video_player: AiVideoPlayer,
        learn_optional: bool,
        threshold: int = 100,
    ) -> None:
        """play 模式：只刷知识点，不查询作业"""
        knowledge_done = knowledge.study_progress >= 101
        if knowledge_done:
            self._reporter.tree_print(
                msg_skip(f"跳过(已完成): {knowledge.knowledge_name} (进度={knowledge.study_progress}%)"),
                depth=2,
                enabled=True,
            )
            return

        self._reporter.tree_print(f"知识点: {styled(knowledge.knowledge_name, _C.WHITE)}", depth=2, enabled=True)
        self._reporter.tree_print(f"进度: {styled(f'{knowledge.study_progress}%', _C.YELLOW)}", depth=3, enabled=True)

        ppts: list[dict[str, str]] = []
        try:
            resources = self.list_knowledge_resources(course_id, class_id, knowledge.knowledge_id)
            self._reporter.print(f"    {msg_info(f'共 {len(resources)} 个资源')}")
        except Exception as e:
            logger.error(f"获取资源列表失败: {e}")
            return

        total = len(resources)
        for idx, resource in enumerate(resources, 1):
            bar_str = progress_bar(idx - 1, total, width=30)
            self._reporter.progress(f"    {bar_str} 处理资源 {idx}/{total}... ")
            try:
                self._process_resource(
                    course_id, class_id, knowledge.knowledge_id, resource, video_player, ppts, learn_optional, threshold
                )
            except Exception as e:
                logger.error(f"处理资源失败: {e}")
            # 显示当前资源完成后的进度
            bar_str = progress_bar(idx, total, width=30)
            self._reporter.progress(f"    {bar_str} 处理资源 {idx}/{total}... ")
        self._reporter.wipe_line()

        logger.info(f"知识点完成: {knowledge.knowledge_name}")
        self._reporter.tree_print(msg_done(f"知识点完成: {knowledge.knowledge_name}"), depth=3, enabled=True)

    def _run_homework_only(
        self,
        course_id: int,
        class_id: int,
        knowledge: Any,
        theme: Any,
        course_info: Any,
        ai_config: AIConfig,
        homework_config: HomeworkConfig,
    ) -> None:
        """homework 模式：只做作业，不刷视频"""
        from zhs.ai.homework import HomeworkCtx
        from zhs.ai.ppt import PptConverter

        exam = self.query_homework(course_id, class_id, knowledge.knowledge_id)
        homework_done = exam is None or not exam.paper_id or exam.mastery_score >= homework_config.ai_homework_threshold
        if homework_done:
            self._reporter.tree_print(
                msg_skip(
                    f"跳过(作业已达标): {knowledge.knowledge_name} (作业={exam.mastery_score if exam else '无'}分)"
                ),
                depth=2,
                enabled=True,
            )
            return

        self._reporter.tree_print(f"知识点: {styled(knowledge.knowledge_name, _C.WHITE)}", depth=2, enabled=True)

        # 收集已完成 PPT 作为参考资料
        ppts: list[dict[str, str]] = []
        self._collect_completed_ppts(course_id, class_id, knowledge.knowledge_id, ppts)

        # PPT 预转换：每个知识点只转换一次，缓存在内存，达标后释放
        reference_materials: list[dict[str, str]] = []
        if ppts:
            self._reporter.tree_print(msg_info(f"转换 {len(ppts)} 个PPT为参考资料..."), depth=3, enabled=True)
            converter = PptConverter()
            for ppt in ppts:
                try:
                    content = converter.convert(ppt["url"])
                    if content:
                        reference_materials.append({"name": ppt["name"], "url": ppt["url"], "content": content})
                except Exception as e:
                    logger.error(f"PPT 转换失败: {e}")

        # 作业循环
        tried = 0
        while True:
            if tried > 0:
                exam = self.query_homework(course_id, class_id, knowledge.knowledge_id)

            if exam is None or not exam.paper_id:
                self._reporter.tree_print(msg_skip("无作业"), depth=3, enabled=True)
                break

            if not self._should_do_homework(exam, tried, False, homework_config):
                self._reporter.tree_print(
                    msg_done(f"作业已达标: {exam.mastery_score}分 (阈值={homework_config.ai_homework_threshold})"),
                    depth=3,
                    enabled=True,
                )
                break

            tried += 1
            self._reporter.print()
            self._reporter.print(styled("-" * 40, _C.DIM))
            self._reporter.tree_print(
                f"作业: {styled(f'第{tried}次尝试', _C.BRIGHT_MAGENTA)}, 当前={exam.mastery_score}分",
                depth=3,
                enabled=True,
            )

            # 执行作业（使用缓存的 PPT 参考资料）
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
                is_success, correct, total = homework_ctx.start(reference_materials=reference_materials)
                score_pct = (correct / total * 100) if total > 0 else 0
                score_color = _C.GREEN if is_success else _C.YELLOW
                self._reporter.tree_print(
                    f"作业结果: {styled(f'{correct}/{total}', score_color)} "
                    f"({styled(f'{score_pct:.0f}%', score_color)})",
                    depth=4,
                    enabled=True,
                )
                logger.info(f"作业结果: {correct}/{total} ({score_pct:.0f}%)")
            except Exception as e:
                self._reporter.tree_print(msg_error(f"作业失败: {e}"), depth=4, enabled=True)
                logger.error(f"作业失败: {e}")

            time.sleep(2)

        # 知识点作业结束，释放 PPT 内存缓存
        reference_materials.clear()
