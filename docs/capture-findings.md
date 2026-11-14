# 知到共享课网页端抓包记录

记录知到共享课网页端的接口行为实测结果，作为 `zhidao/course.py`、`zhidao/video.py`、`zhidao/schedule.py` 的实现依据。

> **注意**：本文件是 **2026-11-12 的实测快照**，接口行为可能随平台更新变化。规格以 [spec.md](./spec.md) 为准，实现以源码为准。

---

## 1. 录制方式

| 项目 | 说明 |
|------|------|
| 录制脚本 | `scripts/capture/cdp_capture.mjs`（Chrome DevTools Protocol） |
| 汇总脚本 | `scripts/capture/summarize.py` |
| 浏览器 | Google Chrome 157，独立 profile |
| 样本课程 | 军事理论-综合版（旧版课）、国家安全教育（知识图谱课） |

- 仓库内 `chrome-win`（Chromium 开源快照）不含 H.264/AAC 解码器，播放器报「代码:03 视频无法播放」，播放相关请求须用 Google Chrome 录制
- 录制产物（cookie、原始请求）放在 `.capture/`，已在 `.gitignore` 中忽略，不提交

---

## 2. 新旧版本判定

| 字段 | 旧版课 | 知识图谱课 |
|------|--------|-----------|
| `queryShareCourseInfo` → `courseType` | 1 | 8 |
| `queryShareCourseInfo` → `mapCourse` | null | 8 |
| `queryCourse` → `courseInfo.courseMode` | **1** | **2** |
| `queryCourse` → `hasHabbitScore` | true | false |
| `queryCourseMapInfo` → `mapStr` | **有值** | 有值 |
| `kgCourseTreeInfoList` | 500「章节结构查询出错」 | 正常 |

**结论**：

- `queryCourseMapInfo` 是否返回 `mapStr` **不能**作为判定依据，旧版课同样返回；按它判定会把旧版课误判为图谱课，随后 `kgCourseTreeInfoList` 报 500，整门课无法播放
- 判定依据为 `queryCourse.courseInfo.courseMode`：`2` 为知识图谱课，其余为旧版 `videolist` 课

---

## 3. 旧版课心跳（`ableVideoPlayer6.0`，1.0 倍速）

### 3.1 上报序列

| 时刻 | 接口 | 本段秒 | 累计秒 | 播放位置 |
|------|------|--------|--------|----------|
| +181s | `saveCacheIntervalTimeV2` | 180 | 863 | `00:03:00` |
| +301s | `saveDatabaseIntervalTimeV2` | 120 | 983 | `00:05:00` |
| +361s | `saveCacheIntervalTimeV2` | 60 | 1043 | `00:06:00` |
| +430s | `saveDatabaseIntervalTimeV2` | 65 | 1108 | `00:07:15`（弹题触发） |

### 3.2 结论

- `saveDatabaseIntervalTimeV2` 约每 **300 秒**一次，`saveCacheIntervalTimeV2` 约每 **180 秒**一次，两者各自计时
- 两种上报**共用一条增量链**：本段秒 = 距上一次**任意**上报的位置差，服务端把两者都累加进 `studyTotalTime`（上表 863 → 983 → 1043 → 1108）
- 两者各自计算增量会被服务端重复累加，下一次上报返回 `-8 学习总时长下降了`
- 1.0 倍速下本段秒等于真实经过的秒数
- 弹题出现时立即补一次 Database 上报
- 上报后 `ewssw` 观看轨迹点重置为 `[0,1]`，再从当前位置续写

### 3.3 ev 字段顺序

```text
Cache:    recruitId;chapterId;courseId;lessonId;HH:MM:SS;累计秒;videoId;lessonVideoId;本段秒;uuid+"zhs"
Database: recruitId;lessonId;lessonVideoId;videoId;chapterId;"0";本段秒;累计秒;HH:MM:SS;uuid+"zhs"
```

### 3.4 三个时间字段

| 字段 | 来源 | 含义 |
|------|------|------|
| 播放位置 `HH:MM:SS` | `prelearningNote` → `studiedLessonDto.learnTimeSec` | 续播起点，不超过视频时长 |
| 累计秒 | `studyTotalTime` 往上加 | 重看会持续增长，**可大于视频时长**（实测 452 秒的视频累计 798） |
| 本段秒 | 距上次上报的位置差 | 服务端据此累加 |

- 把 `studyTotalTime` 当作播放位置会让重看过的视频起点越过结尾，一次心跳即结束

---

## 4. 学习时长限制与学习习惯分

- `queryStudiedTimeLimitInfo`（GET，`video_key` 加密）返回 `studyTimeDto.canBeStudyNow` 与 `studyTimeDetials[{startTimeStr, offTimeStr}]`；样本课程为 `00:00:00–23:59:59`，**无每日时长硬上限**
- 学前必读：平时成绩(30) = 学习进度(10) + 学习习惯(10) + 互动(10)
- 学习习惯分规则文案仅为「合理规划学习行为」，未给出具体分钟数，也没有对应的拒收接口，属后台事后统计
- 因此「分多天学完」需客户端自行控制，服务端不会以 `-9` 截断

---

## 5. 知识图谱课

### 5.1 课件（PPT）

- 资源类型：`dataType=1` 视频，`dataType=2` 课件
- 先调 `preLearningLoad`（同一 `dataId`），否则 `saveUserStudyProcess` 返回 NPE 或 `2021 多端观看异常`
- 课件上报：`dataType=2`、`playTimes=0`、`studyTotalTime=""`、`learnTime=""`，响应 `state=2`
- **上报一次即完成**，无需打开课件内容

### 5.2 视频心跳

- 接口同为 `saveUserStudyProcess`（明文 JSON）
- `playTimes` 是**本次新增学习秒数**：服务端按它累加 `learnTime`（实测 `playTimes=30` → `learnTime +30`），请求里的 `learnTime` 不被采用
- `studyTotalTime` 为视频总秒数，`learnTime` 为 `HH:MM:SS`
- 心跳间隔：样本仅 5 条，间隔不固定（同一秒 3 次、74 秒 1 次均有），节奏**尚未确认**

### 5.3 字段对照

| 字段 | 取值 |
|------|------|
| `dataId` | 资源的 `resourcesFileId`（视频与课件相同，不是资源自己的 `idHash`） |
| `chapterId` | 章节 `idHash` |
| `lessonId` | 课时 `idHash`；有子课时时为父课时 `idHash`（视频与课件样本一致） |
| `lessonVideoId` | 知识点节点 `nodeUidHash`（即叶子节点 `idHash`） |

- 样本：父课时 `kzLNoE0xA7h8dKV6` 下的叶子 `DjnEJ9O0qKSEjDb9`，视频的 `queryUserStudyInfo` / `preLearningLoad` / `saveUserStudyProcess` 均为 `lessonId=kzLNoE0xA7h8dKV6`、`lessonVideoId=DjnEJ9O0qKSEjDb9`

### 5.4 进度与资源

- 章节树 `sourceNum` / `finishNum` 即网页显示的进度（样本：11 章 110 节点、220 个资源）
- 进度按「节点 + `dataId`」独立记录：`queryUserStudyInfo` 返回 `{knowledgeHashId, knowledgeStrId, dataId, state, learnTime}`，`state=2` 为已完成
- 同一 `resourcesFileId` 可挂在多个节点下（样本：37 个视频覆盖 110 个节点），资源无起止时间
- `queryVideoSegment`（入参 `videoId=resourcesFileId` + `idHash/idStr`）对未配置分段的课程返回 `data: []`，整段视频即播放单位
- `resourcesSyncType=0` 为选学资源，上报返回 `2025 禁止选学资源提交进度`

### 5.5 章节测验

| 端点 | 方法 | 说明 |
|------|------|------|
| `/gateway/t/v1/student/exam/start` | GET | 开始答题，`secretStr` 加密，参数含 `courseId` / `recruitId` / `knowledeId` |
| `/gateway/t/v1/student/exam/submit` | POST | 提交答案，明文 JSON |

题目结构与旧版基本一致：`questionId`、`questionType`（1 单选 / 2 多选 / 3 判断）、`questionName`（HTML）、`optionVos[{id, name, isCorrect}]`（答题前 `isCorrect` 为 null）、`analysis`（HTML）。

提交格式（多选以逗号分隔）：

```json
{
  "recruitId": "431490",
  "examId": 286515617,
  "knowledgeId": "jKLkdgvMDGHoWld7",
  "answerVos": [
    {"questionId": 1100898079, "answer": 487745330},
    {"questionId": 1100898238, "answer": "487745824,487745830"}
  ]
}
```

与旧版差异：旧版用 `testId` / `paperId`，新版用 `examId` / `knowledgeId`；域名由 `studyvideoh5.zhihuishu.com` 改为 `aistudy.zhihuishu.com`。**zhs 尚未实现图谱课章节测验。**

---

## 6. zhs 实现回归（旧版课，1.0 倍速）

| 场景 | 结果 |
|------|------|
| 共用增量链，1213 秒视频从 0 播放 400 秒 | Cache 在约 183 秒上报，弹题时 Database 补报余下 88 秒；服务端回读 `studyTotalTime=400`、`learnTimeSec=400`，无 `-8` |
| 各自算增量（修复前），同一视频播放 330 秒 | 服务端累计 660 并返回 `-8` |

---

## 7. 待补充

- 1.5 倍速下网页端心跳（录制中断，未取得）
- 知识图谱课视频心跳的稳定节奏（当前 zhs 固定 30 秒，未与网页对照）
