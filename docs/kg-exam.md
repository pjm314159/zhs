# 启动 KG 章节测验

登录后，用 `zhs kg-exam-start <recruitAndCourseId> <知识点ID>` 启动指定知识点的测验并输出试卷 JSON。第一个参数是课程列表中的 `recruitAndCourseId`，不是数字 `courseId`；第二个参数是图谱知识点的 ID，不是视频 ID。此命令不会播放视频、提交答案或查询掌握度。

命令从同一条课程记录取 `recruitId` 和正数 `courseId`（优先顶层，再看 `courseInfo.courseId`）。找不到课程或有效 ID 时会报错，不向测验端点发请求。启动请求为 `GET /gateway/t/v1/exam/start`，加密参数中的 `knowledeId` 为服务端实际拼写，不传占位 `examId`。

离线验证：`PYTHONPATH=$PWD/src python -m pytest tests/zhidao/test_kg_exam.py -q`。测试拦截 HTTP，不需要登录或真实课程。
