"""题库 models：查询结果、信息、题型映射"""

from pydantic import BaseModel

# 题库题型 ID → enncy type 字符串映射
# 与项目内 QuestionType (SINGLE=1, MULTI=2, FILL=3, JUDGE=14) 对应
_QUESTION_TYPE_MAP: dict[int, str] = {
    1: "single",
    2: "multiple",
    3: "completion",
    14: "judgement",
}


def map_question_type(qtype_id: int) -> str:
    """将项目内部题型 ID 映射为 enncy 题库 type 参数。

    未知题型返回 "unknown"（题库 type 字段可选）。
    """
    return _QUESTION_TYPE_MAP.get(qtype_id, "unknown")


class QuestionBankResult(BaseModel):
    """题库查询结果（code=1 时的 data 字段）"""

    question: str = ""
    answer: str = ""
    times: int = 0
    ai: bool = False

    def format_hint(self) -> str:
        """渲染为 extra["题库参考"] 的值；无可用答案返回空串。

        注意：返回值不带前缀，由 prompt 构建器包成 ``【题库参考】\\n{value}``。
        """
        answers = self._parse_answer()
        if not answers:
            return ""
        source = "题库AI生成" if self.ai else "题库数据库"
        header = f"以下为题库查询到的标准答案（来源: {source}），请直接根据此答案分解并给出标准回答形式，无需自行推断："
        if len(answers) == 1:
            return f"{header}\n```\n{answers[0]}\n```\n"
        items = "\n".join(f"- {a}" for a in answers)
        return f"{header}\n```\n{items}\n```\n"

    def _parse_answer(self) -> list[str]:
        """解析 answer 字段。

        多答案以 ``\\n`` 分隔；``#`` 是题库污染字符，按行切后去除尾部 ``#``。
        """
        if not self.answer:
            return []
        cleaned: list[str] = []
        for line in self.answer.split("\n"):
            line = line.strip()
            if line.endswith("#"):
                line = line[:-1].strip()
            if line:
                cleaned.append(line)
        return cleaned


class QuestionBankInfo(BaseModel):
    """题库信息接口（/info）返回数据"""

    times: int = 0
    user_times: int = 0
    success_times: int = 0
