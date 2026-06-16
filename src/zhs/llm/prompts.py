"""LLM 答题 Prompt 模板与答案解析"""

import ast
import json
import re


def build_choice_prompt(
    question: str,
    choices: list[dict[str, object]],
    answer_type: str,
    reference_materials: list[dict[str, str]] | None = None,
    extra: dict[str, str] | None = None,
) -> str:
    """构建选择题/判断题 Prompt

    Args:
        question: 题目文本
        choices: 选项列表 [{"id": 1, "content": "A"}, ...]
        answer_type: 题目类型（"单选题" | "多选题" | "判断题"）
        reference_materials: 参考资料
        extra: 额外上下文（courseName, theme, knowledgePoint 等）
    """
    reference_materials = reference_materials or []
    extra = extra or {}

    parts: list[str] = []

    # 参考资料（markdown 代码块包裹，含文件名）
    if reference_materials:
        parts.append("参考资料：")
        for ref in reference_materials:
            name = ref.get("name", "")
            content = ref.get("content", "")
            parts.append(f"```{name}\n{content}\n```")

    # 上下文
    course_name = extra.get("courseName", "")
    theme = extra.get("theme", "")
    knowledge_point = extra.get("knowledgePoint", "")
    if course_name or theme or knowledge_point:
        ctx = f"假设你是一名学生，正在学习《{course_name}》。需要严格按照考试要求完成一道题目，否则无法及格。\n"
        if theme:
            ctx += f"现在，你学习到了{theme}。\n"
        if knowledge_point:
            ctx += f"本次考察知识点为{knowledge_point}。\n"
        parts.append(ctx)

    # 指令
    select_text = "所有正确的答案" if answer_type == "多选题" else "最合适的答案"
    instruction = (
        f"本题为{answer_type}，请从选项中选择{select_text}，回答放到markdown代码块中，例如：\n\n"
        "```answer\n"
        '[{"id": xxx, "content": xxx}]\n'
        "```\n"
        "答案必须为满足格式的json字符串(列表，单选也要是列表)，否则视为无效答案，不能得分。"
        "在这个markdown代码块（answer）外，你需要解释为什么你认为这个答案是正确的，"
        "并且标注出你选择这个答案的依据，这些依据必须有一定的权威性。（我提供给你的参考资料绝对权威可信）"
    )
    parts.append(instruction)

    # 题目
    parts.append(f"现在，请听题：\n\n{question}")

    # 选项
    parts.append(f"\n\n选项如下：```choices\n{json.dumps(choices, ensure_ascii=False, indent=4)}\n```")

    return "\n".join(parts)


def build_fill_blank_prompt(
    question: str,
    reference_materials: list[dict[str, str]] | None = None,
    extra: dict[str, str] | None = None,
) -> str:
    """构建填空题 Prompt

    Args:
        question: 题目文本
        reference_materials: 参考资料
        extra: 额外上下文
    """
    reference_materials = reference_materials or []
    extra = extra or {}

    parts: list[str] = []

    # 参考资料（markdown 代码块包裹，含文件名）
    if reference_materials:
        parts.append("参考资料：")
        for ref in reference_materials:
            name = ref.get("name", "")
            content = ref.get("content", "")
            parts.append(f"```{name}\n{content}\n```")

    # 上下文
    course_name = extra.get("courseName", "")
    theme = extra.get("theme", "")
    knowledge_point = extra.get("knowledgePoint", "")
    if course_name or theme or knowledge_point:
        ctx = f"假设你是一名学生，正在学习《{course_name}》。\n"
        if theme:
            ctx += f"现在，你学习到了{theme}。\n"
        if knowledge_point:
            ctx += f"本次考察知识点为{knowledge_point}。\n"
        parts.append(ctx)

    # 指令
    instruction = (
        "本题为填空题，请根据题目内容填写空白处的答案。如果有多个空，每个空的答案用换行分隔。"
        "回答放到markdown代码块中，例如：\n\n"
        "```answer\n"
        "第一个空的答案\n"
        "第二个空的答案\n"
        "```\n\n"
        "请只填写空白处应该填入的内容，不要重复题目。答案必须简洁准确，通常是词组或短句。"
        "在这个markdown代码块（answer）外，你需要解释为什么你认为这个答案是正确的。"
    )
    parts.append(instruction)

    # 题目
    parts.append(f"现在，请听题：\n\n{question}")

    return "\n".join(parts)


def parse_choice_answer(completion: str) -> list[int]:
    """从 LLM 输出提取选项 ID 列表

    解析 ```answer\\n[{"id": 1, "content": "A"}]\\n``` 格式的输出。
    支持 JSON 和 ast.literal_eval 两种解析方式。
    """
    match = re.search(r"```answer\s*\n(.*?)\n\s*```", completion, re.DOTALL)
    if not match:
        return []

    content = match.group(1).strip()
    if not content:
        return []

    # 先尝试 JSON
    try:
        items = json.loads(content)
        return [item["id"] for item in items]
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    # 兜底：ast.literal_eval
    try:
        items = ast.literal_eval(content)
        return [item["id"] for item in items]
    except (ValueError, SyntaxError, KeyError, TypeError):
        return []


def parse_fill_blank_answer(completion: str) -> list[str]:
    """从 LLM 输出提取填空答案

    解析 ```answer\\n答案1\\n答案2\\n``` 格式的输出，按行提取。
    """
    match = re.search(r"```answer\s*\n(.*?)\n\s*```", completion, re.DOTALL)
    if not match:
        return []

    content = match.group(1).strip()
    if not content:
        return []

    return [line.strip() for line in content.split("\n") if line.strip()]
