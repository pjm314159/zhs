"""测试 openExamDetail 和 getAnswerSheetInformation 真实 API 调用

使用方法：
    uv run python scripts/test_exam_api.py

需要先登录（cookies.json 存在且有效）。
"""

import json
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from zhs.config import ConfigManager
from zhs.session import ZhsSession
from zhs.utils.cookie import list_to_cookies
from zhs.utils.path import get_data_dir


def load_session() -> ZhsSession | None:
    """从 cookies.json 恢复已登录会话"""
    config = ConfigManager().load()
    session = ZhsSession(config)

    cookies_path = get_data_dir() / "cookies.json"
    if not cookies_path.exists():
        print("错误: 未找到 cookies.json，请先登录")
        return None

    with open(cookies_path, encoding="utf-8") as f:
        raw = json.load(f)
    session.cookies = list_to_cookies(raw)
    print(f"Cookie 已加载, uuid={session.uuid}")
    return session


def test_open_exam_detail(session: ZhsSession) -> None:
    """测试 openExamDetail API"""
    print("\n" + "=" * 60)
    print("测试 openExamDetail — 获取考试详情（含成绩）")
    print("=" * 60)

    # 需要提供真实的考试参数
    # 从 taskList 获取
    from zhs.ai.course import AiCourseManager

    mgr = AiCourseManager(session)
    courses = mgr.get_ai_course_list()
    if not courses:
        print("未找到 AI 课程")
        return

    print(f"\n找到 {len(courses)} 门 AI 课程:")
    for i, c in enumerate(courses):
        print(f"  [{i}] {c.get('courseName', '')} (courseId={c.get('courseId')}, classId={c.get('classId')})")

    # 遍历课程查找考试任务
    all_tasks: list[dict] = []
    for c in courses:
        course_id = str(c.get("courseId", ""))
        class_id = str(c.get("classId", ""))
        course_name = c.get("courseName", "")
        if not course_id:
            continue
        try:
            tasks = mgr.get_exam_tasks(course_id)
            for t in tasks:
                t["_course_id"] = course_id
                t["_class_id"] = class_id
                t["_course_name"] = course_name
                all_tasks.append(t)
        except Exception as e:
            print(f"  获取 {course_name} 考试任务失败: {e}")

    if not all_tasks:
        print("\n未找到考试任务")
        return

    print(f"\n找到 {len(all_tasks)} 个考试任务:")
    for i, t in enumerate(all_tasks):
        print(
            f"  [{i}] {t.get('taskName', '')} "
            f"(examTestId={t.get('examTestId')}, examPaperId={t.get('examPaperId')}, "
            f"status={t.get('status')}, userId={t.get('userId')}, id={t.get('id')})"
        )

    # 选择一个任务测试 openExamDetail
    print("\n请输入要测试的任务编号（直接回车选第 0 个）: ", end="")
    choice = input().strip()
    idx = int(choice) if choice else 0
    if idx < 0 or idx >= len(all_tasks):
        print("无效编号")
        return

    task = all_tasks[idx]
    course_id = task["_course_id"]
    class_id = task["_class_id"]
    exam_test_id = str(task.get("examTestId", ""))
    exam_paper_id = str(task.get("examPaperId", ""))
    student_id = int(task.get("userId", 0))
    task_id = str(task.get("id", ""))

    print(f"\n--- 调用 openExamDetail ---")
    print(f"  classId={class_id}")
    print(f"  courseId={course_id}")
    print(f"  examTestId={exam_test_id}")
    print(f"  examPaperId={exam_paper_id}")
    print(f"  studentId={student_id}")
    print(f"  taskId={task_id}")

    url = f"{session.urls.ai}/run/gateway/t/task/exam/openExamDetail"
    data = {
        "classId": class_id,
        "courseId": course_id,
        "examTestId": exam_test_id,
        "examPaperId": exam_paper_id,
        "examId": exam_paper_id,
        "studentId": student_id,
        "taskId": task_id,
        "taskType": None,
    }

    try:
        result = session.ai_task_query(url, data)
        detail = result.get("data", {})
        print(f"\nopenExamDetail 响应:")
        print(json.dumps(detail, ensure_ascii=False, indent=2))

        # 关键字段
        is_look = detail.get("isLookAnswer")
        is_allow = detail.get("isAllowShowDetail")
        score = detail.get("score")
        print(f"\n关键字段:")
        print(f"  isLookAnswer = {is_look} ({'可查看答案' if is_look == 1 else '不可查看'})")
        print(f"  isAllowShowDetail = {is_allow} ({'可查看详情' if is_allow == 1 else '不可查看'})")
        print(f"  score = {score}")
    except Exception as e:
        print(f"\nopenExamDetail 失败: {e}")


def test_get_answer_sheet(session: ZhsSession) -> None:
    """测试 getAnswerSheetInformation API（提交后校验答案）"""
    print("\n" + "=" * 60)
    print("测试 getAnswerSheetInformation — 校验答案")
    print("=" * 60)

    # 手动输入参数（从 openExamDetail 或 taskList 获取）
    print("\n请输入 examTestId: ", end="")
    exam_test_id = input().strip()
    print("请输入 examPaperId: ", end="")
    exam_paper_id = input().strip()

    if not exam_test_id or not exam_paper_id:
        print("参数不能为空")
        return

    url = f"{session.urls.exam}/gateway/t/v1/exam/user/getAnswerSheetInformation"
    data = {
        "examTestId": exam_test_id,
        "examPaperId": exam_paper_id,
    }

    try:
        result = session.ai_exam_query(url, data, method="GET")
        sheet_data = result.get("data", {})
        print(f"\ngetAnswerSheetInformation 响应:")
        print(json.dumps(sheet_data, ensure_ascii=False, indent=2))

        # 统计正确率
        parts = sheet_data.get("partSheetVos", [])
        total = 0
        correct = 0
        for part in parts:
            part_name = part.get("name", "")
            questions = part.get("questionSheetVos", [])
            part_correct = sum(1 for q in questions if q.get("correct") == 1)
            part_total = len(questions)
            total += part_total
            correct += part_correct
            print(f"\n  {part_name}: {part_correct}/{part_total} 正确")
            for q in questions:
                status = "✓" if q.get("correct") == 1 else "✗"
                print(
                    f"    {status} questionId={q.get('questionId')} "
                    f"type={q.get('questionType')} sort={q.get('sort')} "
                    f"score={q.get('score')} answerState={q.get('answerState')}"
                )

        print(f"\n总计: {correct}/{total} 正确")
    except Exception as e:
        print(f"\ngetAnswerSheetInformation 失败: {e}")


def main() -> None:
    session = load_session()
    if session is None:
        return

    print("\n选择测试:")
    print("  1. openExamDetail — 获取考试详情（含成绩）")
    print("  2. getAnswerSheetInformation — 校验答案")
    print("  3. 两个都测试")
    print("请输入编号: ", end="")

    choice = input().strip()

    if choice in ("1", "3"):
        test_open_exam_detail(session)

    if choice in ("2", "3"):
        test_get_answer_sheet(session)

    session.close()
    print("\n完成")


if __name__ == "__main__":
    main()
