# KG 掌握度测验

KG 播放器在每个知识点的资源处理后检查测验，即使资源已完成也不会跳过。`homework.enable_kg_exam = false` 时不调用测验、题库或 LLM。启用时需要已有自定义 LLM 配置；没有有效答案会报失败，不提交默认选项，也不把失败计为完成课程。

## 抓包契约

根据本地录制离线解密核对（不记录凭证或实际 ID）：

- GET `/gateway/t/v1/exam/start`：`recruitId`、`courseId`、`knowledeId`，不传占位 `examId=0`。
- POST `/gateway/t/v1/exam/submit`：`recruitId`、`examId`、`knowledgeId`、`answerVos`、`dateFormate`。
- GET `/gateway/t/v1/exam/getAnswerMasteryInfo`：`recruitId`、`examId`、`knowledeId`。
- GET `/gateway/t/v1/exam/getErrorQuestionRecommend`：`recruitId`、`knowledeId`。

注意 GET 的 `knowledeId` 是服务端实际拼写，与 POST 不同。低于阈值重试时重新 start，重新取题和 examId。没有已证实的“无测验”错误码，因此 404/500、空题目和异常掌握度均明确失败。

题库沿用现有 `QuestionBankClient.query` → `format_hint` → LLM 提示的模式。需要在 `question_bank.scopes` 显式添加 `zhidao_kg_exam`；默认范围不变。选项清理 HTML 后交给现有 LLM choice 接口，仅接受本题合法选项 ID；整套题均有合法答案才提交。LLM 正确性仍无法由本地校验保证。

## 安全检查

```bash
uv run python scripts/check_kg_exam.py
uv run python scripts/test_kg_exam_api.py
uv run pytest tests/test_kg_exam.py tests/zhidao/test_map.py -q
```

两个脚本均为离线检查，不读取 cookies、不执行真实提交。真实课程 API、收费题库和 AI 验证需另行授权；离线测试不证明线上已完成。

## 使用

实际配置文件为 `.zhs/config.toml`。保留已有 `[ai]` 的 key、base_url 和 model，确认 `enabled = true`。KG 开关默认开启：

```toml
[homework]
enable_kg_exam = true
kg_exam_threshold = 100
kg_exam_max_retries = 3
```

可先仅用 AI。若要启用题库提示，在已有 `[question_bank]` 段中将 `enabled` 改为 `true`，保留 token，并在现有 `scopes` 数组中追加 `"zhidao_kg_exam"`。仅填写 token 不会自动开启题库；启用后实际答题会使用查询次数和 AI 额度。不要重复创建同名 TOML 段。

```bash
uv run python scripts/check_kg_exam.py
uv run zhs play -c 1100000680 --type zhidao --console-log
```

不必重新播放已完成视频。程序显示获取题目、逐题解答、提交、掌握度结果；请勿将运行管道截断到 `head`，否则可能提前终止任务。当天视频计划预算已耗尽时，仅检查掌握度，不播放或上报资源。失败会打印原因并计入汇总，不再静默认为完成。

本次验证使用模拟 HTTP 与模型补全，未向真实课程提交答案，未调用收费 AI/题库。线上结果仍需实际运行确认；AI 答案也不保证全对。
