# API 文档

本目录是 ZHS 抓包接口的 OpenAPI 3.1 描述，构建后生成单页 HTML（Redoc CE 3）。

## 目录结构

```
docs/api/
├── openapi.yaml            # 入口：info / tags / paths 路由 / components
├── operations/             # 每个接口一个文件，按域分目录
│   ├── login/
│   └── zhidao-video/
└── build/                  # 产物，不入库
    ├── openapi.bundled.yaml
    └── api.html
```

`openapi.yaml` 只保留路由表，接口细节都在 `operations/` 下，新增接口时不需要改动入口以外的文件。

## 构建

前置：Node 20+（`npx @redocly/cli`）、`uv sync --dev`（pyyaml）。

```bash
# CDN 版：~290 KB，双击可看，JS 从 cdn.redocly.com 加载
uv run python scripts/api_docs/build.py

# 离线单文件：~2.6 MB，零外部请求
uv run python scripts/api_docs/build.py --offline

# 只生成 bundled spec（调试用，不调 Node）
uv run python scripts/api_docs/build.py --no-build
```

### 版本与产物

- `openapi.yaml` 的 `info.version` 由构建脚本从 `pyproject.toml` 注入，始终与 zhs 版本一致，**不要手改**。
- `docs/api/build/` 里全部是自动生成的产物（`openapi.bundled.yaml`、`api.html`），**禁止手工修改**，每次构建都会整份覆盖。
- 要改页面内容，只能改 `openapi.yaml`、`operations/` 或 `build.py`。

产物在 `docs/api/build/`，已加入 `.gitignore`。

离线构建需要先把 ReDoc bundle 放到 `docs/api/vendor/redoc.standalone.js`：

```bash
curl -o docs/api/vendor/redoc.standalone.js \
  https://cdn.redocly.com/redoc/v3.1.0/bundles/redoc.standalone.js
```

## 新增接口

1. 在 `openapi.yaml` 的 `paths` 加一条路由，`$ref` 指向 operation 文件：

   ```yaml
   /gateway/t/v1/learning/queryCourse:
     post:
       $ref: './operations/zhidao-video/query-course.yaml'
   ```

2. 新建 operation 文件，至少写 `tags`、`summary`、`operationId`、`x-zhs-service`、`x-zhs-status`、`responses`。
3. 有抓包记录时补 `x-zhs-crypto`（解密后的业务参数 + 原始密文示例）和 `x-zhs-evidence`。
4. 跑 `build.py`，检查页面排版。

## 字段说明

| 字段 | 必填 | 作用 |
| --- | --- | --- |
| `tags` | 是 | 侧边栏分组，必须在 `openapi.yaml` 的 `tags` 里声明 |
| `x-zhs-service` | 是 | 域名代号（`study` / `homework` / `ai` ...），构建时映射成「完整 URL」 |
| `x-zhs-status` | 是 | 抓包置信度，见下表 |
| `x-zhs-evidence.capturedAt` | 否 | 抓包日期，渲染成「更新时间」 |
| `x-zhs-crypto` | 否 | AES 相关：`key` / `iv` / `cipherField` / `plainSchema` / `example` / `rawExample` |
| `x-zhs-notes` | 否 | 实现备注，原样追加到 description |
| `responses` | 是 | 至少一个 `200` |

`x-zhs-crypto` 会被构建脚本编译成：

- `security`：引用 `components.securitySchemes` 里的 `AES-128-CBC (<key>)`，页面显示 Security 区块
- `requestBody`：`plainSchema` 作为 `application/json` 的字段表，`example` 作为 Payload
- `### 原始报文（加密后）`：`rawExample` 原样放进 description 的代码块

所以 operation 文件里**不要**手写 `requestBody` 和 `security`，只写 `x-zhs-crypto`。

## 状态取值

| 值 | 页面显示 | 含义 |
| --- | --- | --- |
| `confirmed` | 已确认 | 已抓包并复现 |
| `observed` | 已观测 | 抓到了，语义未验证 |
| `pending` | 待复核 | 有记录但未复核 |
| `code-only` | 仅代码 | 代码里有、无抓包证据 |
| `doc-only` | 仅文档 | 抓包文档里有、代码未实现 |

## 当前覆盖

| 域 | 已迁 |
| --- | --- |
| 登录 | 6（`/login/gologin` 的 base / study 两个域合并为一条） |
| 知到-视频 | 12 |
| 其余 | 待迁：知到-作业 7、知到-考试 5、AI 课程/任务/考试/解析 22、Hike 4、课程列表 1 |

接口清单与抓包文档的核对结果见 `.temp/api-inventory.md`（本地文件，不入库）。

## 已知限制

- **不写 `servers`**：项目有 15 个域名，写全局会误导；域名只出现在「完整 URL」行。
- **Redoc 不渲染 Path Item 级 `servers`**，所以多域名只能靠 description。
- **深链接**：带 tag 的 hash 首次加载会被重置到 `#/`，点导航后正常。
- **UI 文案是英文**（Search / Download / Request samples），接口内容中文。
- **无 try-it**：开源版不能发请求，不会拿真实 Cookie 误操作。
