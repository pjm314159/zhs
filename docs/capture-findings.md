# 抓包结论（2026-11-12，Google Chrome 157 网页端）

录制工具：`scripts/capture/cdp_capture.mjs`（CDP），解码：`.capture/dump.py`。
账号：长春工业大学学生；课程：军事理论-综合版（旧版）、国家安全教育（新版图谱）。

## 版本判断

`chrome-win`（Chromium 160 开源快照）不带 H.264/AAC 解码器，网页播放器报
“代码:03 视频无法播放”，播放部分改用系统 Google Chrome（独立 profile）录制。

| 字段 | 军事理论（旧） | 国家安全（新） |
|---|---|---|
| `queryShareCourseInfo` → `courseType` | 1 | 8 |
| `queryShareCourseInfo` → `mapCourse` | null | 8 |
| `queryCourse` → `courseInfo.courseMode` | **1** | **2** |
| `queryCourse` → `hasHabbitScore` | true | false |
| `queryCourseMapInfo` → `mapStr` | **有值** | 有值 |
| `kgCourseTreeInfoList` | **500 章节结构查询出错** | 正常 |

**结论：`queryCourseMapInfo` 返回 `mapStr` 不能作为版本判断依据**，旧版课也会返回。
之前按 `mapStr` 判断，旧版课会被误判为图谱课，随后 `kgCourseTreeInfoList` 报 500，整门课无法播放。
判断依据改为 `queryCourse.courseInfo.courseMode`：`2` 为图谱课，其余为旧版 videolist。

## 旧版 videolist 心跳（1x 实测，`ableVideoPlayer6.0`）

网页端上报两种请求，与 zhs 现有实现一致的是接口与 `ev` 字段顺序，**不一致的是节奏**：

| 时刻 | 接口 | ev 关键字段 |
|---|---|---|
| +181s | `saveCacheIntervalTimeV2` | 播放位置 `00:03:00`，累计 `863`，**本段 `180`** |
| +301s | `saveDatabaseIntervalTimeV2` | 本段 **`120`**，累计 `983`，位置 `00:05:00` |
| +361s | `saveCacheIntervalTimeV2` | 本段 **`60`**，累计 `1043`，位置 `00:06:00` |
| +430s | `saveDatabaseIntervalTimeV2` | 本段 `65`，累计 `1108`，位置 `00:07:15`（弹题触发） |

- Database 心跳间隔约 **300 秒**（5 分钟），zhs 旧实现是 30±5 秒。
- Cache 心跳约每 180 秒一次，触发时机与 Database 各自计时。
- **两种上报共用一条增量链**：本段秒 = 距上一次*任意*上报的位置差，服务端把两者都累加进
  `studyTotalTime`（上表 180 → +120 → +60 → +65，累计 863 → 983 → 1043 → 1108）。
  若各自算增量，服务端会重复累加，下一次就报 `-8 学习总时长下降了`（zhs 实测复现过）。
- 每次上报的本段秒等于真实经过的秒数（1x）。弹题出现时会立即补一次 Database 上报。

## 三个时间字段（实测）

| 字段 | 来源 | 含义 |
|---|---|---|
| 播放位置 `HH:MM:SS` | `prelearningNote.studiedLessonDto.learnTimeSec` | 续播起点，≤ 视频时长 |
| 累计秒 | `studyTotalTime` 往上加 | 重看会一直涨，**可以大于视频时长**（452 秒的视频累计 798） |
| 本段秒 | 距上次上报的位置差 | 服务端据此累加 |

zhs 旧实现把 `studyTotalTime` 当播放位置用：重看过的视频起点直接越过结尾，一次心跳就结束。
- Cache ev 字段顺序：`recruitId;chapterId;courseId;lessonId;HH:MM:SS;累计;videoId;lessonVideoId;本段;uuid+"zhs"`
- Database ev 字段顺序：`recruitId;lessonId;lessonVideoId;videoId;chapterId;"0";本段;累计;HH:MM:SS;uuid+"zhs"`
- `ewssw` 观看轨迹点在上报后重置为 `[0,1]` 再从当前位置续写。

## 学习时长限制

- `queryStudiedTimeLimitInfo`（GET，`video_key` 加密）返回
  `studyTimeDto.canBeStudyNow` 和 `studyTimeDetials[{startTimeStr, offTimeStr}]`。
  本课程为 `00:00:00–23:59:59`，即全天可学，**没有每日 25 分钟这类硬上限**。
- 学前必读：平时成绩(30) = 学习进度(10) + **学习习惯(10)** + 互动(10)。
  习惯分规则文案只有“合理规划学习行为”，没有给出具体分钟数，也没有对应的拒收接口，属于后台事后统计。
  因此“每天学一段、分多天学完”需要客户端自己控制，服务端不会用 `-9` 帮你截断。

## zhs 实测（新实现，1.0x）

- 视频 70796843（1213 秒，从 0 开始）跑 400 秒：Cache 在 ~183 秒上报，弹题时 Database 补报剩余 88 秒，
  服务端回读 `studyTotalTime=400`、`learnTimeSec=400`（`00:06:40`），**没有 `-8`**，与实际观看秒数完全一致。
- 共用增量链之前（各自算增量）实测会多算：同一视频跑 330 秒，服务端累计 660 并报 `-8`。

## 尚未取得

- 1.5 倍速下网页端心跳（录制浏览器中途关闭，未录到）。
- 新版图谱课 PPT 的完成上报。
