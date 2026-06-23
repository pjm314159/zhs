"""缓存子包 — 统一缓存管理

提供 BaseQuestionCache 抽象基类与具体实现：
- ZhidaoHomeworkCache: 知到作业缓存
- AiExamCache: AI 作业/考试缓存

缓存路径: {cache_dir}/{course_type}/{course_id}/{exam_id}.json
"""
