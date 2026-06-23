"""考试编排服务

从原 __main__.py 抽离的考试相关 _run_* 函数。
"""

from loguru import logger

from zhs.config import AppConfig
from zhs.session import ZhsSession


def run_ai_exam(
    session: ZhsSession,
    config: AppConfig,
    ai_course: int | None,
    ai_class: int | None,
    submit: bool = False,
) -> None:
    """AI 课程考试

    流程：
    1. 获取 AI 课程列表（或使用指定的 courseId/classId）
    2. 对每门课程调用 taskList 获取未完成考试
    3. 对每个考试创建 ExamCtx 执行答题
    4. 若 submit=True，提交后通过 openExamDetail 判断是否可查看答案，可查看则保存缓存
    """
    from zhs.ai.course import AiCourseManager
    from zhs.ai.exam import ExamCtx
    from zhs.utils.display import course_tag, msg_done, msg_info, msg_warn

    mgr = AiCourseManager(session)

    # 获取课程列表
    if ai_course and ai_class:
        courses = [{"courseId": str(ai_course), "classId": str(ai_class), "courseName": ""}]
    else:
        courses = mgr.get_ai_course_list()

    print(f"\n{course_tag('ai')} 发现 {len(courses)} 门课程")

    total_exams = 0
    for ac in courses:
        course_id = str(ac.get("courseId", ""))
        class_id = str(ac.get("classId", ""))
        course_name = ac.get("courseName", "")
        if not course_id:
            logger.warning(f"AI 课程 {course_name} 缺少 courseId")
            continue

        try:
            # 获取未完成考试任务列表
            tasks = mgr.get_exam_tasks(course_id)
            if not tasks:
                print(f"  {course_name}: 无未完成考试")
                continue

            print(f"  {course_name}: 发现 {len(tasks)} 个未完成考试")
            for task in tasks:
                exam_test_id = str(task.get("examTestId", ""))
                exam_paper_id = str(task.get("examPaperId", ""))
                task_name = task.get("taskName", "")
                task_id = str(task.get("id", ""))
                student_id = int(task.get("userId", 0))
                if not exam_test_id or not exam_paper_id:
                    logger.warning(f"考试任务 {task_name} 缺少 examTestId 或 examPaperId")
                    continue

                submit_tag = " (提交)" if submit else " (不提交)"
                print(f"    开始考试: {task_name} (examTestId={exam_test_id}){submit_tag}")
                try:
                    ctx = ExamCtx(
                        session=session,
                        course_id=course_id,
                        class_id=class_id,
                        exam_test_id=exam_test_id,
                        exam_paper_id=exam_paper_id,
                        ai_config=config.ai,
                        exam_config=config.exam,
                        op_extra={"courseName": course_name},
                        student_id=student_id,
                        task_id=task_id,
                    )
                    all_correct, correct, total = ctx.start(submit=submit)
                    if submit:
                        if all_correct:
                            print(f"    {msg_done(f'考试完成: {correct}/{total} 全对')}")
                        elif correct == 0:
                            print(f"    {msg_info('考试已提交，无法查看答案')}")
                        else:
                            print(f"    {msg_warn(f'考试完成: {correct}/{total} 正确')}")
                    else:
                        print(f"    {msg_info(f'答题完成（未提交）: {total} 题，可以使用--submit提交')}")
                    total_exams += 1
                except Exception as e:
                    logger.error(f"考试 {task_name} 处理失败: {e}")
                    print(f"    考试 {task_name} 处理失败: {e}")
        except Exception as e:
            logger.error(f"AI 课程 {course_name} 考试处理失败: {e}")
            print(f"  AI 课程 {course_name} 考试处理失败: {e}")

    print(f"\n共完成 {total_exams} 个考试")


__all__ = ["run_ai_exam"]
