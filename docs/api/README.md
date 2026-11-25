# 智慧树接口文档

ZHS 使用的智慧树平台 HTTP 接口，依据实际抓包与代码实现整理，以 OpenAPI 3.1 描述，构建为单页 HTML（ReDoc CE 3）。

## 构建

前置：Node 24+（`npx @redocly/cli`）、Python 3.13（`uv sync --dev` 安装 `pyyaml`）。

```bash
uv run python scripts/api_docs/build.py           # 默认，约 400 KB，JS 从 CDN 加载
uv run python scripts/api_docs/build.py --offline  # 离线单文件，约 2.6 MB，无外部请求
uv run python scripts/api_docs/build.py --no-build # 只生成 bundled spec，不调 Node
```

产物在 `docs/api/build/`（`openapi.bundled.yaml`、`api.html`），已加入 `.gitignore`。

`info.version` 由构建脚本从 `pyproject.toml` 的 `project.version` 注入，始终与 zhs 版本一致，不要手改。`build/` 下的文件每次构建整份覆盖，禁止手工修改；要改内容只能改 `openapi.yaml`、`operations/` 或 `build.py`。

离线构建需要先准备 ReDoc bundle：

```bash
curl -o docs/api/vendor/redoc.standalone.js \
  https://cdn.redocly.com/redoc/v3.1.0/bundles/redoc.standalone.js
```

### 持续集成与部署

在线文档：**https://pjm314159.github.io/zhs/**

`.github/workflows/api-docs.yml` 在 `docs/api/**` 或 `scripts/api_docs/**` 变更时自动执行：

1. `uv sync --dev`
2. `build.py`（编译 `x-zhs-*` 并渲染 HTML）
3. `redocly lint`（spec 结构错误会让 CI 失败）
4. 上传 artifact `api-docs`，保留 14 天
5. push 到 `main` / `dev` 时，把 `api.html` 作为站点根页发布到 GitHub Pages

触发范围为 push / PR 到 `main`、`dev`，也可手动 `workflow_dispatch`。PR 只构建不部署，合并后自动更新线上文档。仓库的 Settings → Pages 中 Source 需设为 GitHub Actions（已配置）。

## 目录结构

```
docs/api/
├── openapi.yaml            # 入口：info / tags / paths 路由 / components
├── operations/             # 一个接口一个文件，按域分目录
│   ├── login/              # 登录
│   ├── course-list/        # 课程列表
│   ├── zhidao-video/       # 知到-视频
│   ├── zhidao-homework/    # 知到-作业
│   ├── zhidao-exam/        # 知到-考试
│   ├── ai-course/          # AI 智慧课程：课程与资源
│   ├── ai-exam/            # AI 智慧课程：考试与作业
│   ├── ai-analysis/        # AI 题目解析与对话
│   ├── yidun/              # 易盾验证码（c.dun.163.com）
│   └── hike/               # Hike 域
└── build/                  # 构建产物，不入库
```

`openapi.yaml` 只保留路由表，接口细节全在 `operations/`，新增接口不需要改动入口以外的文件。

## 文档约定

### `x-zhs-*` 扩展

OpenAPI 表达不了的信息用扩展记录，构建期编译成标准结构或描述文本。

| 字段 | 必填 | 作用 |
| --- | --- | --- |
| `tags` | 是 | 侧边栏分组，须在 `openapi.yaml` 的 `tags` 中声明 |
| `x-zhs-service` | 是 | 域名代号（`study` / `homework` / `ai` ...），构建时映射为「完整 URL」行 |
| `x-zhs-status` | 是 | 抓包置信度，取值见下 |
| `x-zhs-evidence.capturedAt` | 否 | 抓包日期，渲染为「更新时间」 |
| `x-zhs-crypto` | 否 | 加密参数：`key` / `iv` / `cipherField` / `plaintextIn` / `plainSchema` / `example` / `rawExample` |
| `x-zhs-notes` | 否 | 实现备注，原样追加到 description 末尾 |
| `responses` | 是 | 至少包含一个 `200` |

### 加密接口

`x-zhs-crypto` 由构建脚本编译为三段内容，operation 文件里不必手写 `requestBody` 和 `security`：

| 编译产物 | 来源 | 页面表现 |
| --- | --- | --- |
| `security` | `key` | 引用 `components.securitySchemes` 的 `AES-128-CBC (<key>)`，Security 区块可展开查看密钥、IV、密文字段 |
| `requestBody` | `plainSchema` + `example` | Body 字段表与 Payload 均为**解密后**的业务参数 |
| `### 原始报文（加密后）` | `rawExample` | description 里的 JSON 代码块，展示 `secretStr` 与时间戳字段 |

### 示例数据

所有示例值使用尖括号占位符（`<courseId>`、`<examId>`、`<eid>` ...），不写真实抓包值，也不使用仿真随机串。占位符是字符串，与 `integer` 类型可能不一致，仅作示意。

### 状态取值

| 值 | 页面显示 | 含义 |
| --- | --- | --- |
| `confirmed` | 已确认 | 已抓包并复现 |
| `observed` | 已观测 | 已抓到，语义未完全验证 |
| `pending` | 待复核 | 有记录但未复核 |
| `code-only` | 仅代码 | 代码中存在，无抓包证据 |
| `doc-only` | 仅文档 | 抓包文档中存在，代码未实现 |

## 新增接口

1. 在 `openapi.yaml` 的 `paths` 下新增路由，`$ref` 指向 operation 文件：

   ```yaml
   /gateway/t/v1/learning/queryCourse:
     post:
       $ref: './operations/zhidao-video/query-course.yaml'
   ```

2. 新建 operation 文件，至少包含 `tags`、`summary`、`operationId`、`x-zhs-service`、`x-zhs-status`、`responses`。
3. 有抓包记录时补 `x-zhs-crypto`（解密后的业务参数与原始密文示例）和 `x-zhs-evidence`。
4. 执行 `build.py`，检查页面排版与 `redocly lint` 结果。

## 覆盖范围

共 64 个接口，与 `src/zhs` 的调用点一一对应。

| 域 | 数量 | 说明 |
| --- | --- | --- |
| 登录 | 9 | 登录页、二维码、gologin、CAS、登录态、学校列表、学校搜索、登录页配置 |
| 课程列表 | 2 | 知到共享课、AI 课程列表 |
| 知到-视频 | 13 | 含弹窗三件套、Cache/Database 心跳、验证码上报 |
| 知到-作业 | 8 | 列表、重做、作答、查看、保存、提交、答案查询、验证码校验（`-12`） |
| 知到-考试 | 5 | 列表、doExam、提交、锁检查、学校信息 |
| AI-智慧课程 | 20 | 课程 3、考试与作业 10、解析 3、资源与进度 4 |
| Hike | 4 | 全部为 `仅代码`，字段待抓包 |
| 易盾验证码 | 3 | getconf / get / check，纯 HTTP 取题与提交 |
| **合计** | **64** | |

其中 8 个标 `仅代码`（AI 资源 4 个、Hike 4 个）尚无抓包证据，字段为占位骨架。

## 已知限制

- **不写 `servers`**：项目涉及 15 个域名，全局配置会产生误导；域名只出现在每个接口的「完整 URL」行。
- **Redoc 不展示 Path Item 级 `servers`**：多域名场景只能依靠 description。
- **深链接**：带 tag 的 hash 首次加载会重置到 `#/`，点击导航后正常。
- **界面文案为英文**：Search / Download / Request samples 等，接口内容为中文。
- **不支持 try-it**：开源版无法发送请求，避免误用真实 Cookie。
