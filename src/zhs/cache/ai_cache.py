"""AI 作业/考试缓存 — SQLite 单键存储

数据库: {cache_dir}/questions_bank.db（与知到缓存共用同一数据库）
表: ai_questions

单键设计:
- question_id: 唯一键，UPSERT 语义

HomeworkCtx 与 ExamCtx 共用此缓存（通过 exam_id 区分）。
exam 模块可通过 search_in_course 跨 exam 搜索课程题库。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from zhs.utils.path import get_data_dir


def _now_str() -> str:
    """当前时间 ISO 格式字符串"""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


class AiExamCache:
    """AI 作业/考试缓存（SQLite）

    条目格式: {"question": str, "answer": str, "answer_content": str, "questionDict": dict}
    key 为 question_id 的字符串形式。
    """

    def __init__(self, cache_dir: Any | None = None) -> None:
        self._cache_dir = cache_dir or get_data_dir() / "cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._cache_dir / "questions_bank.db"
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接（每次创建，避免线程安全问题）"""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """初始化数据库表与索引"""
        with self._get_conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ai_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    course_id INTEGER NOT NULL,
                    course_name TEXT NOT NULL DEFAULT '',
                    exam_id TEXT NOT NULL,
                    question_id TEXT NOT NULL,
                    question TEXT NOT NULL DEFAULT '',
                    answer TEXT NOT NULL DEFAULT '',
                    answer_content TEXT NOT NULL DEFAULT '',
                    question_dict TEXT NOT NULL DEFAULT '{}',
                    last_updated TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_qid
                    ON ai_questions(course_id, exam_id, question_id);

                CREATE INDEX IF NOT EXISTS idx_ai_course_question
                    ON ai_questions(course_id, question)
                    WHERE question != '';
                """
            )

    # --- 内部序列化 ---

    def _row_to_entry(self, row: sqlite3.Row) -> dict[str, Any]:
        """数据库行 → entry dict"""
        return {
            "question": row["question"],
            "answer": row["answer"],
            "answer_content": row["answer_content"],
            "questionDict": json.loads(row["question_dict"]),
        }

    # --- 查询 ---

    def get(self, course_id: int | str, exam_id: int | str, question_id: int) -> dict[str, Any] | None:
        """获取缓存条目（单 exam 查询）"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM ai_questions WHERE course_id=? AND exam_id=? AND question_id=?",
                (course_id, str(exam_id), str(question_id)),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_entry(row)

    def load_all_for_course(self, course_id: int | str) -> dict[str, dict[str, Any]]:
        """加载课程下所有 exam 的缓存（合并，兼容旧接口）

        返回 {question_id_str: entry_dict, ...}
        """
        result: dict[str, dict[str, Any]] = {}
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM ai_questions WHERE course_id=?", (course_id,)).fetchall()
            for row in rows:
                qid = row["question_id"]
                result[qid] = self._row_to_entry(row)
        return result

    def load_exam(self, course_id: int | str, exam_id: int | str) -> dict[str, dict[str, Any]]:
        """加载单个 exam 的缓存（兼容旧接口 _load_exam）"""
        result: dict[str, dict[str, Any]] = {}
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM ai_questions WHERE course_id=? AND exam_id=?",
                (course_id, str(exam_id)),
            ).fetchall()
            for row in rows:
                qid = row["question_id"]
                result[qid] = self._row_to_entry(row)
        return result

    # --- 保存 ---

    def put(
        self,
        course_id: int | str,
        exam_id: int | str,
        question_id: int,
        entry: dict[str, Any],
        course_name: str = "",
    ) -> None:
        """写入缓存条目（UPSERT）"""
        now = _now_str()
        question = entry.get("question", "")
        answer = entry.get("answer", "")
        answer_content = entry.get("answer_content", "")
        question_dict = json.dumps(entry.get("questionDict", {}), ensure_ascii=False)
        qid_str = str(question_id)
        exam_str = str(exam_id)
        with self._get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM ai_questions WHERE course_id=? AND exam_id=? AND question_id=?",
                (course_id, exam_str, qid_str),
            ).fetchone()
            if existing is not None:
                conn.execute(
                    """UPDATE ai_questions SET
                       question=?, answer=?, answer_content=?, question_dict=?,
                       course_name=CASE WHEN course_name='' AND ?!='' THEN ? ELSE course_name END,
                       last_updated=?
                       WHERE id=?""",
                    (question, answer, answer_content, question_dict, course_name, course_name, now, existing["id"]),
                )
            else:
                conn.execute(
                    """INSERT INTO ai_questions
                       (course_id, course_name, exam_id, question_id,
                        question, answer, answer_content, question_dict, last_updated)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (course_id, course_name, exam_str, qid_str, question, answer, answer_content, question_dict, now),
                )

    # --- 课程级查询（仅 exam 模块使用） ---

    def search_in_course(
        self,
        course_id: int | str,
        question: str,
    ) -> dict[str, Any] | None:
        """在课程的所有 exam 中搜索匹配的已答题目（仅 exam 模块调用）

        按题目文本匹配，只返回有答案的题目（answer 非空）。
        """
        if not question:
            return None
        with self._get_conn() as conn:
            row = conn.execute(
                """SELECT * FROM ai_questions
                   WHERE course_id=? AND question=? AND question!=''
                   AND answer!=''
                   ORDER BY last_updated DESC LIMIT 1""",
                (course_id, question),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_entry(row)

    # --- 导出导入 ---

    def export_course(self, course_id: int | str) -> dict[str, Any]:
        """导出课程数据为 JSON dict"""
        exams_map: dict[str, list[dict[str, Any]]] = {}
        course_name = ""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM ai_questions WHERE course_id=? ORDER BY exam_id, id",
                (course_id,),
            ).fetchall()
            for row in rows:
                if row["course_name"] and not course_name:
                    course_name = row["course_name"]
                exam_id = row["exam_id"]
                if exam_id not in exams_map:
                    exams_map[exam_id] = []
                exams_map[exam_id].append(
                    {
                        "question_id": row["question_id"],
                        "question": row["question"],
                        "answer": row["answer"],
                        "answer_content": row["answer_content"],
                        "questionDict": json.loads(row["question_dict"]),
                        "lastUpdated": row["last_updated"],
                    }
                )
        return {
            "version": 2,
            "type": "ai",
            "course_id": course_id,
            "course_name": course_name,
            "exams": [{"exam_id": eid, "questions": qs} for eid, qs in exams_map.items()],
        }

    def import_course(self, data: dict[str, Any]) -> None:
        """导入课程数据"""
        course_id = data["course_id"]
        course_name = data.get("course_name", "")
        for exam_data in data.get("exams", []):
            exam_id = exam_data["exam_id"]
            for q in exam_data.get("questions", []):
                question_id = q["question_id"]
                entry = {
                    "question": q.get("question", ""),
                    "answer": q.get("answer", ""),
                    "answer_content": q.get("answer_content", ""),
                    "questionDict": q.get("questionDict", {}),
                }
                self.put(course_id, exam_id, question_id, entry, course_name)

    # --- 辅助 ---

    @staticmethod
    def parse_answer(answer_str: str) -> list[str] | None:
        """解析缓存中的 answer 字段

        - 含 #@# → 按 #@# 分隔（多选题选项 ID）
        - 不含 #@# → 返回单元素列表（单选/判断/填空题）
        填空题多个空用 / 合并存储，不拆分。
        """
        if not answer_str:
            return None
        if "#@#" in answer_str:
            return answer_str.split("#@#")
        return [answer_str]
