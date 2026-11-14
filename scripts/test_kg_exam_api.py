#!/usr/bin/env python3
"""测试知识图谱课章节测验 API

验证新实现的 ZhidaoKgExamApi 是否能正常调用。
需要先登录并设置 cookie。

用法:
    python scripts/test_kg_exam_api.py
"""

import json
import sys
from pathlib import Path

# 添加 src 到 sys.path
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "src"))

from zhs.config import AppConfig
from zhs.session import ZhsSession


def main() -> None:
    """测试知识图谱课章节测验 API"""
    config = AppConfig()
    session = ZhsSession(config)

    # 从 config.toml 或环境变量读取 cookie
    cookie_file = repo_root / "config.toml"
    if not cookie_file.exists():
        print("错误：未找到 config.toml，请先登录并保存 cookie")
        sys.exit(1)

    # 这里需要手动设置 cookie 或从配置文件读取
    # 示例：从录制文件中提取的 recruitId 和 examId
    recruit_id = "431490"
    exam_id = 286515617
    knowledge_id = "jKLkdgvMDGHoWld7"

    print(f"测试知识点: {knowledge_id}")
    print(f"考试 ID: {exam_id}")
    print()

    try:
        # 1. 开始答题
        print("1. 调用 kg_exam_start...")
        exam_data = session.kg_exam_start(recruit_id, exam_id, knowledge_id)
        print(f"   获取到 {len(exam_data.get('questions', []))} 道题目")
        print(f"   examId: {exam_data.get('examId')}")
        print(f"   knowledgeId: {exam_data.get('knowledgeId')}")
        print()

        # 2. 构造答案（这里只是示例，实际需要题库或 AI）
        questions = exam_data.get("questions", [])
        if not questions:
            print("   警告：未获取到题目")
            return

        print("2. 构造答案...")
        answers = []
        for q in questions:
            question_id = q["questionId"]
            question_type = q["questionType"]
            options = q.get("optionVos", [])

            if not options:
                continue

            # 简单策略：单选/判断选第一个，多选选所有
            if question_type in [1, 14]:  # 单选或判断
                answer = options[0]["id"]
            elif question_type == 2:  # 多选
                answer = ",".join(str(opt["id"]) for opt in options)
            else:
                continue

            answers.append({"questionId": question_id, "answer": answer})

        print(f"   构造了 {len(answers)} 个答案")
        print()

        # 3. 提交答案
        print("3. 调用 kg_exam_submit...")
        submit_result = session.kg_exam_submit(recruit_id, exam_id, knowledge_id, answers)
        print(f"   提交结果: {submit_result}")
        print()

        # 4. 获取掌握度信息
        print("4. 调用 kg_exam_get_mastery_info...")
        mastery_info = session.kg_exam_get_mastery_info(recruit_id, exam_id, knowledge_id)
        print(f"   题目总数: {mastery_info.get('questionNum')}")
        print(f"   答对题数: {mastery_info.get('correctNum')}")
        print(f"   正确率: {mastery_info.get('rate')}%")
        print(f"   提升率: {mastery_info.get('upgradedRate')}%")
        print()

        print("✅ 测试完成！")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
