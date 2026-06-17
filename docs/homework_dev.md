# 知到作业功能开发计划

> Branch: `feat/zhidao_homework`
> 参考: `.temp/feat_homework.md` (功能规格), `.temp/homework_api.md` (API 文档)

---

## 概述

为知到课程实现作业自动答题功能。核心流程：扫描作业 → 做作业 → 提交后检查 → 错题分析 → 重做。

---

## 关键概念

### max_submit 语义

- `backNum`：API 返回的**剩余重做次数**（首次做不算重做）
- `achieveCount`：API 返回的**已做次数**（首次做 + 已重做次数）
- **总可做次数 = 1（首次做）+ backNum（剩余重做次数）**
- `max_submit`：config 配置的**总提交次数上限**，用于限制总可做次数
  - 如 max_submit=3，表示最多做 3 次（1 次首次 + 2 次重做）
  - 若 API 允许 1+backNum=5 次，但 max_submit=3，则实际最多做 3 次
- **筛选逻辑**：`achieve_count >= max_submit` → 跳过（已达配置上限）

### eid vs id

- `doHomework` 返回 `eid`（加密字符串），`id` 为 null
- `lookHomework` 返回 `id`（数字型），`eid` 为 null
- **`eid` 用于 `saveStudentAnswer`** — 做作业时保存答案
- **`id` 用于 `getStuAnswerInfo` 和 AI 解析 `run`** — 查看答案和 AI 解析

### API 域名与加密

- 作业 API：`studentexam-api.zhihuishu.com`，AES-128-CBC 加密（exam_key），`secretStr` 字段，**无 dateFormate**
- AI 解析 API：`ai-course-assistant-api.zhihuishu.com`，明文 JSON，SSE 流式响应

### 题型与答案格式

| 题型 | questionType | answer 格式 | 示例 |
|------|-------------|------------|------|
| 单选题 | 1 | 单个 optionId（int） | `440703134` |
| 多选题 | 2 | 多个 optionId 逗号分隔（string） | `"440703126,440703127"` |
| 填空题 | 3 | 填空文本（string） | `"答案文本"` |
| 判断题 | 14 | optionId（int） | `440703143` |

---

## 文件结构

```
src/zhs/zhidao/homework/
    __init__.py          # 导出
    models.py            # 作业数据模型（pydantic）✅
    cache.py             # 本地缓存管理（JSON 读写）✅
    scanner.py           # 作业扫描（getStudentHomework API）✅
    worker.py            # 做作业逻辑（Phase 2）
    analyzer.py          # 错题分析 + AI 解析（Phase 3+4）

tests/zhidao/homework/
    __init__.py
    test_models.py       ✅
    test_cache.py        ✅
    test_scanner.py      ✅
    test_worker.py       (Phase 2)
    test_analyzer.py     (Phase 3+4)
```

---

## Phase 1: 扫描作业 ✅ 已完成

### Task 1: models.py ✅

9 个 pydantic 模型 + IntEnum，支持 API 字段别名和 questionType dict→int 解析。

### Task 2: cache.py ✅

`HomeworkCache` 类，惰性加载，JSON 文件存储，正确/错误选项互斥。

### Task 3: scanner.py ✅

`HomeworkScanner` 类，CAS SSO 自动认证，扫描未提交+已提交作业，筛选待处理作业。

---

## Phase 2: 做作业（worker.py）

### Task 4: session 新增作业 API 方法

在 `session.py` 中新增以下方法（均使用 `homework_query`，exam_key 加密，无 dateFormate）：

| 方法 | API 端点 | 用途 |
|------|---------|------|
| `homework_do` | `/studentExam/gateway/t/v1/student/doHomework` | 开始做作业，获取题目详情（含 eid） |
| `homework_save_answer` | `/studentExam/gateway/t/v1/answer/saveStudentAnswer` | 逐题保存答案 |
| `homework_submit` | `/studentExam/gateway/t/v1/answer/submit` | 提交作业 |
| `homework_has_answer` | `/studentExam/gateway/t/v1/answer/hasAnswer` | 检查是否有已保存答案 |
| `homework_get_answer_new` | `/studentExam/gateway/t/v1/answer/getStuAnswerInfoNew` | 获取已保存答案详情（eid 为键） |
| `homework_look` | `/studentExam/gateway/t/v1/student/lookHomework` | 查看已提交作业（数字型 id） |
| `homework_get_answer` | `/studentExam/gateway/t/v1/answer/getStuAnswerInfo` | 获取学生答案信息（数字型 id 为键） |

### Task 5: worker.py — 做作业核心逻辑

```python
class HomeworkWorker:
    """知到作业做题器"""

    def __init__(self, session: ZhsSession, config: AppConfig, cache: HomeworkCache) -> None:
        self._session = session
        self._config = config
        self._cache = cache

    def do_homework(self, item: HomeworkItem, recruit_id: str, school_id: str) -> float:
        """做单个作业，返回得分率（0-100）

        流程:
        1. doHomework 获取题目
        2. 逐题生成答案（缓存 → LLM）
        3. saveStudentAnswer 逐题保存
        4. submit 提交
        """

    def _generate_answer(self, question: HomeworkQuestion, item: HomeworkItem) -> int | str:
        """为单题生成答案

        优先级:
        1. 本地缓存有正确选项 → 直接使用
        2. 本地缓存有错误选项 → 排除后随机选择
        3. LLM 生成答案
        """

    def _save_answer(self, question: HomeworkQuestion, answer: int | str,
                     item: HomeworkItem, recruit_id: str, school_id: str) -> None:
        """保存单题答案（saveStudentAnswer）"""

    def _submit(self, item: HomeworkItem, recruit_id: str, answer_count: int) -> float:
        """提交作业，返回得分率"""
```

#### doHomework 请求参数

```python
data = {
    "recruitId": recruit_id,
    "examId": item.exam_id,
    "studentExamId": item.id,
    "schoolId": school_id,
    "courseId": str(item.course_id),
}
```

#### saveStudentAnswer 请求参数

```python
answer_item = {
    "examId": item.exam_id,
    "recruitId": recruit_id,
    "stuExamId": item.id,
    "eid": question.eid,
    "schoolId": school_id,
    "deviceId": "",
    "examType": "",
    "fromType": 3,
    "answer": answer,  # int 或 string
    "dataIds": "",
    "questionType": question.question_type_id,
}
data = {
    "stuExamAnswer": json.dumps([answer_item]),
    "recruitId": recruit_id,
}
```

#### submit 请求参数

```python
data = {
    "recruitId": recruit_id,
    "examId": item.exam_id,
    "stuExamId": item.id,
    "achieveCount": str(answer_count),
}
```

#### 答案生成逻辑

```
对每道题:
1. 查本地缓存 → 有正确选项 → 直接使用
2. 查本地缓存 → 有错误选项 → 排除错误选项后随机选择
3. 无缓存 → LLM 生成答案
4. 保存选项信息到缓存（首次做时）
5. 每题保存后随机休息 1-2 秒
```

---

## Phase 3: 提交后检查 + 错题分析（analyzer.py）

### Task 6: analyzer.py — 提交后检查

```python
class HomeworkAnalyzer:
    """知到作业错题分析器"""

    def __init__(self, session: ZhsSession, config: AppConfig, cache: HomeworkCache) -> None:

    def check_result(self, item: HomeworkItem, recruit_id: str, school_id: str) -> dict[str, HomeworkAnswerInfo]:
        """检查提交结果

        流程:
        1. lookHomework 获取题目详情（数字型 id）
        2. getStuAnswerInfo 获取每题对错信息
        3. 返回 {question_id: answer_info}
        """

    def save_to_cache(self, item: HomeworkItem, questions: list[HomeworkQuestion],
                      answers: dict[str, HomeworkAnswerInfo]) -> None:
        """保存对错信息到本地缓存

        - 正确的题: mark_correct
        - 错误的题: mark_wrong
        """

    def should_redo(self, item: HomeworkItem, score_rate: float) -> bool:
        """判断是否需要重做

        条件:
        - score_rate < homework_threshold
        - backNum > 0
        - achieve_count < max_submit
        """
```

#### lookHomework 请求参数

```python
data = {
    "recruitId": recruit_id,
    "studentExamId": item.id,
    "examId": item.exam_id,
    "schoolId": school_id,
    "courseId": str(item.course_id),
}
```

#### getStuAnswerInfo 请求参数

```python
data = {
    "recruitId": recruit_id,
    "stuExamId": item.id,
    "examId": item.exam_id,
    "schoolId": school_id,
    "courseId": str(item.course_id),
    "questionIds": ",".join(str(q.id) for q in questions if q.id),
}
```

---

## Phase 4: AI 解析（analyzer.py 扩展）

### Task 7: AI 解析集成

在 `analyzer.py` 中扩展 AI 解析功能：

```python
def analyze_wrong_question(self, question: HomeworkQuestion, item: HomeworkItem,
                           recruit_id: str) -> str | None:
    """AI 解析错题

    调用 ai-course-assistant-api 的 run 接口（SSE 流式）
    使用数字型 questionId（来自 lookHomework）
    """

def generate_answer_with_ai(self, question: HomeworkQuestion, analysis: str) -> int | str:
    """基于 AI 解析生成答案

    将 AI 解析结果 + 题目选项喂给 LLM，生成最终答案
    """
```

#### AI 解析 run 请求参数

```python
# 域名: ai-course-assistant-api.zhihuishu.com
# 明文 JSON，不加密
data = {
    "courseId": str(item.course_id),
    "recruitId": recruit_id,
    "userRole": "STUDENT",
    "userId": user_id,  # 从 session 获取
    "threadId": "",
    "questionId": question.id,  # 数字型
    "regenerate": False,
    "runId": None,
}
```

---

## Phase 5: CLI 集成

### Task 8: zhs homework --type zhidao

在 `__main__.py` 中集成作业命令：

```python
# zhs homework --type zhidao --course <id>
# 完整流程: scan → do → check → analyze → redo (循环)
```

---

## 完整流程图

```
Phase 1: 扫描 ✅
  getStudentHomework(flag=1) → 未提交列表
  getStudentHomework(flag=2) → 已提交列表
  ↓ 筛选需要处理的作业

Phase 2: 做作业
  doHomework → 题目详情（eid, options）
  ↓ 逐题生成答案（本地缓存 → LLM）
  saveStudentAnswer × N → 逐题保存
  submit → 提交

Phase 3: 检查
  submit 返回 score → 判断是否达标
  ├─ 达标 → 完成
  └─ 未达标 →
      lookHomework → 题目详情（数字型 id）
      getStuAnswerInfo → 对错信息（id 为键，isCurrent）
      保存到本地（正确/错误标记）
      → 回到 Phase 2 重做

Phase 4: AI 解析（Phase 3 错题时触发）
  run × 错题数 → AI 解析（SSE 流式）
  解析结果保存到本地
  → 回到 Phase 2 重做（此时有 AI 解析辅助）
```

---

## 依赖关系

```
Phase 1 (扫描) ✅
    ↓
Phase 2 (做作业: worker.py + session 新方法)
    ↓
Phase 3 (提交后检查: analyzer.py)
    ↓
Phase 4 (AI 解析: analyzer.py 扩展)
    ↓
Phase 5 (CLI 集成: __main__.py)
```

---

## config 字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `homework_threshold` | int | 100 | 满分阈值百分比（0-100），得分率达到此值视为完成 |
| `max_submit` | int | 3 | 总提交次数上限（首次做 + 重做），如 max_submit=3 表示最多做 3 次 |
