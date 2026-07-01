"""知到作业缓存 — SQLite 双键存储

数据库: {cache_dir}/questions_bank.db
表: zhidao_questions

双键设计:
- eid: doHomework 阶段保存（先于 id）
- question_id: lookHomework 阶段保存（后于 eid），保存时桥接关联到 eid 记录

查询时无需桥接，O(1) 索引查询。
桥接只在 save_options_by_id 时执行（低频）。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from zhs.utils.path import get_data_dir
from zhs.zhidao.homework.models import HomeworkCacheEntry, HomeworkCacheOption, WrongOption


def _now_str() -> str:
    """当前时间 ISO 格式字符串"""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _compute_option_ids_hash(options: list[HomeworkCacheOption]) -> str:
    """计算选项 ID 的 hash（排序后逗号拼接）"""
    if not options:
        return ""
    return ",".join(str(opt.id) for opt in sorted(options, key=lambda o: o.id))


class ZhidaoHomeworkCache:
    """知到作业答案本地缓存（SQLite）"""

    def __init__(self, cache_dir: Path | None = None) -> None:
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
                CREATE TABLE IF NOT EXISTS zhidao_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    course_id INTEGER NOT NULL,
                    course_name TEXT NOT NULL DEFAULT '',
                    exam_id TEXT NOT NULL,
                    eid TEXT,
                    question_id TEXT,
                    question_type INTEGER NOT NULL DEFAULT -1,
                    content TEXT NOT NULL DEFAULT '',
                    options TEXT NOT NULL DEFAULT '[]',
                    option_ids_hash TEXT NOT NULL DEFAULT '',
                    correct_options TEXT NOT NULL DEFAULT '[]',
                    wrong_options TEXT NOT NULL DEFAULT '[]',
                    ai_analysis TEXT,
                    last_updated TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_zhidao_eid
                    ON zhidao_questions(course_id, exam_id, eid)
                    WHERE eid IS NOT NULL;

                CREATE UNIQUE INDEX IF NOT EXISTS idx_zhidao_qid
                    ON zhidao_questions(course_id, exam_id, question_id)
                    WHERE question_id IS NOT NULL;

                CREATE INDEX IF NOT EXISTS idx_zhidao_course_opt_hash
                    ON zhidao_questions(course_id, option_ids_hash)
                    WHERE option_ids_hash != '';

                CREATE INDEX IF NOT EXISTS idx_zhidao_course_content
                    ON zhidao_questions(course_id, content)
                    WHERE content != '';
                """
            )

    # --- 内部序列化 ---

    def _row_to_entry(self, row: sqlite3.Row) -> HomeworkCacheEntry:
        """数据库行 → HomeworkCacheEntry"""
        options_data = json.loads(row["options"])
        options = [HomeworkCacheOption(**opt) for opt in options_data]
        return HomeworkCacheEntry(
            questionType=row["question_type"],
            content=row["content"],
            options=options,
            correctOptions=json.loads(row["correct_options"]),
            wrongOptions=json.loads(row["wrong_options"]),
            aiAnalysis=row["ai_analysis"],
            lastUpdated=row["last_updated"],
        )

    def _row_to_key(self, row: sqlite3.Row) -> str:
        """数据库行 → question key（优先 question_id，其次 eid）"""
        qid = row["question_id"]
        if qid is not None:
            return str(qid)
        return str(row["eid"] or "")

    def _entry_to_json(self, entry: HomeworkCacheEntry) -> dict[str, Any]:
        """entry → JSON 可序列化 dict（导出用）"""
        return {
            "eid": None,
            "question_id": None,
            "questionType": entry.question_type,
            "content": entry.content,
            "options": [{"id": opt.id, "content": opt.content} for opt in entry.options],
            "correctOptions": entry.correct_options,
            "wrongOptions": entry.wrong_options,
            "aiAnalysis": entry.ai_analysis,
            "lastUpdated": entry.last_updated,
        }

    # --- 查询 ---

    def get(self, course_id: int, exam_id: str, question_key: str) -> HomeworkCacheEntry | None:
        """获取缓存条目

        key 是纯数字 → WHERE question_id = ?
        否则          → WHERE eid = ?
        """
        with self._get_conn() as conn:
            if question_key.isdigit():
                row = conn.execute(
                    "SELECT * FROM zhidao_questions WHERE course_id=? AND exam_id=? AND question_id=?",
                    (course_id, exam_id, question_key),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM zhidao_questions WHERE course_id=? AND exam_id=? AND eid=?",
                    (course_id, exam_id, question_key),
                ).fetchone()
            if row is None:
                return None
            return self._row_to_entry(row)

    def get_correct_options(self, course_id: int, exam_id: str, question_key: str) -> list[int]:
        """获取已知正确选项"""
        entry = self.get(course_id, exam_id, question_key)
        return entry.correct_options if entry else []

    def get_wrong_options(self, course_id: int, exam_id: str, question_key: str) -> list[WrongOption]:
        """获取已知错误选择方式列表"""
        entry = self.get(course_id, exam_id, question_key)
        return entry.wrong_options if entry else []

    # --- 保存 ---

    def save_options_by_eid(
        self,
        course_id: int,
        exam_id: str,
        eid: str,
        question_type: int,
        options: list[HomeworkCacheOption],
        content: str = "",
        course_name: str = "",
    ) -> None:
        """doHomework 阶段保存（eid 先于 id）

        已有记录 → 跳过（选项内容一致）
        没有 → INSERT 新记录 (eid=值, question_id=NULL)
        """
        opt_hash = _compute_option_ids_hash(options)
        options_json = json.dumps([{"id": o.id, "content": o.content} for o in options])
        with self._get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM zhidao_questions WHERE course_id=? AND exam_id=? AND eid=?",
                (course_id, exam_id, eid),
            ).fetchone()
            if existing is not None:
                # 已有记录，跳过
                return
            conn.execute(
                """
                INSERT INTO zhidao_questions
                    (course_id, course_name, exam_id, eid, question_id,
                     question_type, content, options, option_ids_hash,
                     correct_options, wrong_options, ai_analysis, last_updated)
                VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, '[]', '[]', NULL, ?)
                """,
                (course_id, course_name, exam_id, eid, question_type, content, options_json, opt_hash, _now_str()),
            )

    def save_options_by_id(
        self,
        course_id: int,
        exam_id: str,
        question_id: str,
        question_type: int,
        options: list[HomeworkCacheOption],
        content: str = "",
        course_name: str = "",
    ) -> None:
        """lookHomework 阶段保存（id 后于 eid），含桥接

        1. SELECT WHERE question_id=? → 已有 → UPDATE
        2. 桥接查找（当前 exam，eid IS NOT NULL）
           a. 有选项 → option_ids_hash 匹配
           b. 无选项 → content 匹配
           → 找到 → UPDATE（补上 question_id）
        3. 桥接没找到 → INSERT (eid=NULL, question_id=值)
        """
        opt_hash = _compute_option_ids_hash(options)
        options_json = json.dumps([{"id": o.id, "content": o.content} for o in options])
        now = _now_str()
        with self._get_conn() as conn:
            # 1. 已有 question_id 记录 → UPDATE
            existing = conn.execute(
                "SELECT id FROM zhidao_questions WHERE course_id=? AND exam_id=? AND question_id=?",
                (course_id, exam_id, question_id),
            ).fetchone()
            if existing is not None:
                conn.execute(
                    """UPDATE zhidao_questions SET
                       question_type=?, content=?, options=?, option_ids_hash=?,
                       course_name=CASE WHEN course_name='' AND ?!='' THEN ? ELSE course_name END,
                       last_updated=?
                       WHERE id=?""",
                    (question_type, content, options_json, opt_hash, course_name, course_name, now, existing["id"]),
                )
                return

            # 2. 桥接查找
            bridged_row: sqlite3.Row | None = None
            if opt_hash:
                bridged_row = conn.execute(
                    """SELECT id FROM zhidao_questions
                       WHERE course_id=? AND exam_id=? AND option_ids_hash=?
                       AND eid IS NOT NULL""",
                    (course_id, exam_id, opt_hash),
                ).fetchone()
            elif content:
                bridged_row = conn.execute(
                    """SELECT id FROM zhidao_questions
                       WHERE course_id=? AND exam_id=? AND content=? AND content!=''
                       AND eid IS NOT NULL""",
                    (course_id, exam_id, content),
                ).fetchone()

            if bridged_row is not None:
                # 找到 eid 记录 → UPDATE 补上 question_id
                conn.execute(
                    """UPDATE zhidao_questions SET
                       question_id=?, question_type=?, content=?, options=?,
                       option_ids_hash=?, last_updated=?
                       WHERE id=?""",
                    (question_id, question_type, content, options_json, opt_hash, now, bridged_row["id"]),
                )
                return

            # 3. 桥接没找到 → INSERT
            conn.execute(
                """
                INSERT INTO zhidao_questions
                    (course_id, course_name, exam_id, eid, question_id,
                     question_type, content, options, option_ids_hash,
                     correct_options, wrong_options, ai_analysis, last_updated)
                VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, '[]', '[]', NULL, ?)
                """,
                (course_id, course_name, exam_id, question_id, question_type, content, options_json, opt_hash, now),
            )

    def save_options(
        self,
        course_id: int,
        exam_id: str,
        question_key: str,
        question_type: int,
        options: list[HomeworkCacheOption],
        content: str = "",
        course_name: str = "",
    ) -> None:
        """保存题目选项信息（兼容旧接口，自动判断 eid/id）"""
        if question_key.isdigit():
            self.save_options_by_id(course_id, exam_id, question_key, question_type, options, content, course_name)
        else:
            self.save_options_by_eid(course_id, exam_id, question_key, question_type, options, content, course_name)

    def put(
        self,
        course_id: int,
        exam_id: str,
        question_key: str,
        entry: HomeworkCacheEntry,
    ) -> None:
        """写入缓存条目（兼容旧接口）"""
        if question_key.isdigit():
            self.save_options_by_id(
                course_id,
                exam_id,
                question_key,
                entry.question_type,
                entry.options,
                entry.content,
            )
        else:
            self.save_options_by_eid(
                course_id,
                exam_id,
                question_key,
                entry.question_type,
                entry.options,
                entry.content,
            )
        if entry.correct_options:
            self.mark_correct(course_id, exam_id, question_key, entry.correct_options)
        if entry.wrong_options:
            self.mark_wrong(course_id, exam_id, question_key, entry.wrong_options[0])
        if entry.ai_analysis:
            self.save_ai_analysis(course_id, exam_id, question_key, entry.ai_analysis)

    def mark_correct(
        self,
        course_id: int,
        exam_id: str,
        question_key: str,
        option_ids: list[int],
        course_name: str = "",
        auto_clear_wrong: bool = False,
    ) -> None:
        """标记正确选项（合并到 correct_options，去重）

        auto_clear_wrong=True 且已有 wrong_options（再次做对，之前做错）→
            清除所有 wrong_options 和 ai_analysis（已知正确答案后不再需要）。
        首次做对（无 wrong_options）→ 不清除，保证性能。
        """
        now = _now_str()
        with self._get_conn() as conn:
            row = self._find_row(conn, course_id, exam_id, question_key)
            if row is None:
                # 记录不存在 → INSERT 最小记录（按 key 类型选列）
                key_field = "question_id" if question_key.isdigit() else "eid"
                conn.execute(
                    f"""INSERT INTO zhidao_questions
                       (course_id, course_name, exam_id, {key_field}, question_type,
                        content, options, option_ids_hash, correct_options, wrong_options,
                        ai_analysis, last_updated)
                       VALUES (?, ?, ?, ?, -1, '', '[]', '', ?, '[]', NULL, ?)""",
                    (course_id, course_name, exam_id, question_key, json.dumps(sorted(set(option_ids))), now),
                )
                return
            existing = json.loads(row["correct_options"])
            correct = sorted(set(existing) | set(option_ids))
            existing_wrong = json.loads(row["wrong_options"])
            if auto_clear_wrong and existing_wrong:
                # 再次做对（之前做错）→ 清除所有 wrong_options 和 ai_analysis
                conn.execute(
                    "UPDATE zhidao_questions SET correct_options=?, wrong_options='[]', "
                    "ai_analysis=NULL, last_updated=? WHERE id=?",
                    (json.dumps(correct), now, row["id"]),
                )
            else:
                # 正常：仅移除与正确答案完全匹配的错误组合
                correct_set = set(option_ids)
                wrong = [
                    c
                    for c in existing_wrong
                    if not (isinstance(c, list) and c and isinstance(c[0], int) and set(c) == correct_set)
                ]
                conn.execute(
                    "UPDATE zhidao_questions SET correct_options=?, wrong_options=?, last_updated=? WHERE id=?",
                    (json.dumps(correct), json.dumps(wrong), now, row["id"]),
                )

    def mark_wrong(
        self,
        course_id: int,
        exam_id: str,
        question_key: str,
        answer: list[int] | list[str],
        course_name: str = "",
    ) -> None:
        """标记错误选择方式（追加去重）"""
        if not answer:
            return
        now = _now_str()
        with self._get_conn() as conn:
            row = self._find_row(conn, course_id, exam_id, question_key)
            if row is None:
                key_field = "eid" if not question_key.isdigit() else "question_id"
                conn.execute(
                    f"""INSERT INTO zhidao_questions
                        (course_id, course_name, exam_id, {key_field}, question_type,
                         content, options, option_ids_hash, correct_options, wrong_options,
                         ai_analysis, last_updated)
                        VALUES (?, ?, ?, ?, -1, '', '[]', '', '[]', ?, NULL, ?)""",
                    (course_id, course_name, exam_id, question_key, json.dumps([list(answer)]), now),
                )
                return
            wrong = json.loads(row["wrong_options"])
            if isinstance(answer[0], int):
                new_combo = sorted(answer)
                existing_int = [sorted(c) for c in wrong if isinstance(c, list) and c and isinstance(c[0], int)]
                if new_combo not in existing_int:
                    wrong.append(new_combo)
            else:
                if list(answer) not in [c for c in wrong if isinstance(c, list) and c and isinstance(c[0], str)]:
                    wrong.append(list(answer))
            conn.execute(
                "UPDATE zhidao_questions SET wrong_options=?, last_updated=? WHERE id=?",
                (json.dumps(wrong), now, row["id"]),
            )

    def save_ai_analysis(
        self,
        course_id: int,
        exam_id: str,
        question_key: str,
        ai_analysis: str,
    ) -> None:
        """保存 AI 解析内容"""
        now = _now_str()
        with self._get_conn() as conn:
            row = self._find_row(conn, course_id, exam_id, question_key)
            if row is None:
                key_field = "question_id" if question_key.isdigit() else "eid"
                conn.execute(
                    f"""INSERT INTO zhidao_questions
                       (course_id, course_name, exam_id, {key_field}, question_type,
                        content, options, option_ids_hash, correct_options, wrong_options,
                        ai_analysis, last_updated)
                       VALUES (?, '', ?, ?, -1, '', '[]', '', '[]', '[]', ?, ?)""",
                    (course_id, exam_id, question_key, ai_analysis, now),
                )
                return
            conn.execute(
                "UPDATE zhidao_questions SET ai_analysis=?, last_updated=? WHERE id=?",
                (ai_analysis, now, row["id"]),
            )

    # --- 桥接查找（当前 exam） ---

    def find_key_by_options(self, course_id: int, exam_id: str, option_ids: list[int]) -> str | None:
        """通过选项 ID 集合查找 question key（当前 exam）"""
        opt_hash = ",".join(str(i) for i in sorted(option_ids))
        with self._get_conn() as conn:
            row = conn.execute(
                """SELECT question_id, eid FROM zhidao_questions
                   WHERE course_id=? AND exam_id=? AND option_ids_hash=?
                   AND (question_id IS NOT NULL OR eid IS NOT NULL)""",
                (course_id, exam_id, opt_hash),
            ).fetchone()
            if row is None:
                return None
            return row["question_id"] or row["eid"] or None

    def find_key_by_content(self, course_id: int, exam_id: str, content: str) -> str | None:
        """通过题目纯文本内容查找 question key（当前 exam）"""
        if not content:
            return None
        with self._get_conn() as conn:
            row = conn.execute(
                """SELECT question_id, eid FROM zhidao_questions
                   WHERE course_id=? AND exam_id=? AND content=? AND content!=''
                   AND (question_id IS NOT NULL OR eid IS NOT NULL)""",
                (course_id, exam_id, content),
            ).fetchone()
            if row is None:
                return None
            return row["question_id"] or row["eid"] or None

    # --- 课程级查询（跨 exam，仅 exam 模块） ---

    def search_in_course(
        self,
        course_id: int,
        content: str = "",
        option_ids: list[int] | None = None,
    ) -> HomeworkCacheEntry | None:
        """在课程的所有 exam 中搜索匹配的已答题目

        优先级:
        1. 选项精确匹配（option_ids_hash）
        2. 题目文本匹配（content）

        只返回有答案的题目（correct_options 非空 或 ai_analysis 非空）。
        """
        with self._get_conn() as conn:
            # 1. 选项匹配
            if option_ids:
                opt_hash = ",".join(str(i) for i in sorted(option_ids))
                row = conn.execute(
                    """SELECT * FROM zhidao_questions
                       WHERE course_id=? AND option_ids_hash=? AND option_ids_hash!=''
                       AND (correct_options!='[]' OR ai_analysis IS NOT NULL)
                       ORDER BY last_updated DESC LIMIT 1""",
                    (course_id, opt_hash),
                ).fetchone()
                if row is not None:
                    return self._row_to_entry(row)
            # 2. 内容匹配
            if content:
                row = conn.execute(
                    """SELECT * FROM zhidao_questions
                       WHERE course_id=? AND content=? AND content!=''
                       AND (correct_options!='[]' OR ai_analysis IS NOT NULL)
                       ORDER BY last_updated DESC LIMIT 1""",
                    (course_id, content),
                ).fetchone()
                if row is not None:
                    return self._row_to_entry(row)
        return None

    def load_all_for_course(self, course_id: int) -> dict[str, HomeworkCacheEntry]:
        """加载课程下所有 exam 的缓存（合并，兼容旧接口）"""
        result: dict[str, HomeworkCacheEntry] = {}
        with self._get_conn() as conn:
            rows = conn.execute("SELECT * FROM zhidao_questions WHERE course_id=?", (course_id,)).fetchall()
            for row in rows:
                key = row["question_id"] or row["eid"]
                if key:
                    result[key] = self._row_to_entry(row)
        return result

    # --- 导出导入 ---

    def export_course(self, course_id: int) -> dict[str, Any]:
        """导出课程数据为 JSON dict

        优化：当 correctOptions 非空时，跳过 wrongOptions 和 aiAnalysis（节省内存）。
        已知正确答案后，错误记录和 AI 解析不再需要。
        """
        exams_map: dict[str, list[dict[str, Any]]] = {}
        course_name = ""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM zhidao_questions WHERE course_id=? ORDER BY exam_id, id",
                (course_id,),
            ).fetchall()
            for row in rows:
                if row["course_name"] and not course_name:
                    course_name = row["course_name"]
                exam_id = row["exam_id"]
                if exam_id not in exams_map:
                    exams_map[exam_id] = []
                q = self._entry_to_json(self._row_to_entry(row))
                q["eid"] = row["eid"]
                q["question_id"] = row["question_id"]
                # 优化：有正确选项时，跳过 wrong 和 ai（节省内存）
                if q["correctOptions"]:
                    q["wrongOptions"] = []
                    q["aiAnalysis"] = None
                exams_map[exam_id].append(q)
        return {
            "version": 2,
            "type": "zhidao",
            "course_id": course_id,
            "course_name": course_name,
            "exams": [{"exam_id": eid, "questions": qs} for eid, qs in exams_map.items()],
        }

    def import_course(self, data: dict[str, Any]) -> None:
        """导入课程数据

        - 当 eid 和 question_id 同时存在时，两者都保留（_link_eid 关联到同一行）
        - wrongOptions 会被导入（遍历每个错误组合调用 mark_wrong）
        """
        course_id = data["course_id"]
        course_name = data.get("course_name", "")
        for exam_data in data.get("exams", []):
            exam_id = exam_data["exam_id"]
            for q in exam_data.get("questions", []):
                eid = q.get("eid")
                question_id = q.get("question_id")
                options = [HomeworkCacheOption(**opt) for opt in q.get("options", [])]
                content = q.get("content", "")
                qtype = q.get("questionType", -1)
                correct_opts = q.get("correctOptions") or []
                wrong_opts = q.get("wrongOptions") or []
                ai_analysis = q.get("aiAnalysis")

                # 选择 key：优先 question_id，其次 eid
                if question_id:
                    key = question_id
                    self.save_options_by_id(course_id, exam_id, question_id, qtype, options, content, course_name)
                    # 同时有 eid → 关联到 question_id 行（保留双键）
                    if eid:
                        self._link_eid(course_id, exam_id, question_id, eid)
                elif eid:
                    key = eid
                    self.save_options_by_eid(course_id, exam_id, eid, qtype, options, content, course_name)
                else:
                    continue

                # 导入答案数据（correct → wrong → ai 顺序）
                if correct_opts:
                    self.mark_correct(course_id, exam_id, key, correct_opts)
                if wrong_opts:
                    for combo in wrong_opts:
                        if combo:  # 跳过空组合
                            self.mark_wrong(course_id, exam_id, key, combo, course_name=course_name)
                if ai_analysis:
                    self.save_ai_analysis(course_id, exam_id, key, ai_analysis)

    def _link_eid(
        self,
        course_id: int,
        exam_id: str,
        question_id: str,
        eid: str,
    ) -> None:
        """将 eid 关联到 question_id 行（导入用）

        场景：导入时同时有 eid 和 question_id，但 save_options_by_id 未桥接到 eid 行
        （选项/内容不匹配），导致 question_id 行的 eid 为 NULL。

        1. 找到 question_id 行
        2. 若该行已有相同 eid → 无需操作（桥接已关联）
        3. 若该行已有不同 eid → 不覆盖
        4. 若该行 eid 为 NULL：
           a. 查找同 course+exam+eid 的独立行
           b. 若存在 → 合并答案数据（correct 取并集，wrong/ai 取非空），删除 eid 行，UPDATE qid 行
           c. 若不存在 → UPDATE qid 行直接设 eid
        """
        now = _now_str()
        with self._get_conn() as conn:
            qid_row = conn.execute(
                "SELECT * FROM zhidao_questions WHERE course_id=? AND exam_id=? AND question_id=?",
                (course_id, exam_id, question_id),
            ).fetchone()
            if qid_row is None:
                return
            # 已关联相同 eid → 无需操作
            if qid_row["eid"] == eid:
                return
            # 已有不同 eid → 不覆盖
            if qid_row["eid"] is not None:
                return

            # 查找独立 eid 行
            eid_row = conn.execute(
                "SELECT * FROM zhidao_questions WHERE course_id=? AND exam_id=? AND eid=?",
                (course_id, exam_id, eid),
            ).fetchone()

            if eid_row is not None and eid_row["id"] != qid_row["id"]:
                # 合并：correct 取并集，wrong/ai 取非空值
                merged_correct = sorted(
                    set(json.loads(qid_row["correct_options"])) | set(json.loads(eid_row["correct_options"]))
                )
                qid_wrong = json.loads(qid_row["wrong_options"])
                eid_wrong = json.loads(eid_row["wrong_options"])
                merged_wrong = qid_wrong if qid_wrong else eid_wrong
                merged_ai = qid_row["ai_analysis"] or eid_row["ai_analysis"]
                # 删除 eid 行
                conn.execute("DELETE FROM zhidao_questions WHERE id=?", (eid_row["id"],))
                # UPDATE qid 行：设 eid + 合并答案数据
                conn.execute(
                    "UPDATE zhidao_questions SET eid=?, correct_options=?, wrong_options=?, "
                    "ai_analysis=?, last_updated=? WHERE id=?",
                    (
                        eid,
                        json.dumps(merged_correct),
                        json.dumps(merged_wrong),
                        merged_ai,
                        now,
                        qid_row["id"],
                    ),
                )
            elif eid_row is None:
                # 无独立 eid 行 → 直接设 eid
                conn.execute(
                    "UPDATE zhidao_questions SET eid=?, last_updated=? WHERE id=?",
                    (eid, now, qid_row["id"]),
                )

    # --- 内部辅助 ---

    def _find_row(
        self, conn: sqlite3.Connection, course_id: int, exam_id: str, question_key: str
    ) -> sqlite3.Row | None:
        """查找行（先 question_id 后 eid）"""
        if question_key.isdigit():
            return cast(
                sqlite3.Row | None,
                conn.execute(
                    "SELECT * FROM zhidao_questions WHERE course_id=? AND exam_id=? AND question_id=?",
                    (course_id, exam_id, question_key),
                ).fetchone(),
            )
        return cast(
            sqlite3.Row | None,
            conn.execute(
                "SELECT * FROM zhidao_questions WHERE course_id=? AND exam_id=? AND eid=?",
                (course_id, exam_id, question_key),
            ).fetchone(),
        )
