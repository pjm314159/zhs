# ZHS 使用教程

## 1. 安装

### 前置要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) 包管理器

### 安装步骤

```bash
# 克隆仓库
git clone <repo-url>
cd ZHS

# 安装依赖
uv sync --dev
```

## 2. 配置

### 2.1 创建配置文件

```bash
cp config.toml.example config.toml
```

### 2.2 配置说明

#### 基础设置

| 字段                 | 默认值      | 说明                            |
| ------------------ | -------- | ----------------------------- |
| `save_cookies`     | `true`   | 保存 Cookie，避免重复登录              |
| `speed`            | `1.0`    | 播放速度（1.0-2.0）                 |
| `log_level`        | `"INFO"` | 日志级别：DEBUG/INFO/WARNING/ERROR |
| `tree_view`        | `true`   | 显示课程资源树                       |
| `progressbar_view` | `true`   | 显示进度条                         |
| `limit`            | `0`      | 刷课时间限制（分钟），0 = 不限制            |
| `threshold`        | `0.91`   | 视频完成阈值（0.0-1.0），进度超过此值视为完成    |

#### AI 配置

| 字段                    | 默认值                           | 说明                                |
| --------------------- | ----------------------------- | --------------------------------- |
| `ai.use_zhidao_ai`    | `true`                        | 使用智慧树内置 AI（无需 API Key）            |
| `ai.api_key`          | `""`                          | OpenAI 兼容 API Key（自定义 AI 时需要）     |
| `ai.base_url`         | `"https://api.openai.com/v1"` | API 地址                            |
| `ai.model`            | `"gpt-4o-mini"`               | 模型名称                              |
| `ai.moonshot_api_key` | `""`                          | MoonShot API Key（AI 课程 PPT 转文本需要） |

> **默认使用智慧树内置 AI**，无需配置任何 API Key 即可使用 AI 答题功能。
> 如需使用自定义 LLM（如 DeepSeek、MoonShot），将 `use_zhidao_ai` 设为 `false` 并填写 `api_key`。

#### 代理设置

```toml
[proxies]
http = "http://127.0.0.1:7890"
https = "http://127.0.0.1:7890"
```

或通过命令行 `--proxy` 参数指定。

#### 加密密钥与 API URL

一般无需修改，已预填默认值。

## 3. 登录

ZHS 仅支持**扫码登录**，首次运行时自动弹出二维码：

```bash
uv run zhs
```

程序会：

1. 生成二维码图片并保存到临时目录
2. 用默认图片查看器打开
3. 等待手机智慧树 APP 扫码确认

登录成功后，Cookie 会自动保存，下次运行无需重复登录。

### 终端显示二维码

如果无法打开图片查看器，可在终端直接显示：

```bash
uv run zhs --show-in-terminal
```

### 指定二维码保存路径

```bash
uv run zhs --image-path /path/to/qrcode.png
```

## 4. 使用方式

### 4.1 获取课程列表

```bash
uv run zhs -f
```

课程列表会保存到 `~/.zhs/execution.json`，包含课程名称和 ID。

### 4.2 刷知到课程

知到课程 ID 通常包含字母（如 `ABC123`）：

```bash
uv run zhs -c ABC123
```

### 4.3 刷 Hike 课程

Hike 课程 ID 通常为纯数字（如 `12345`）：

```bash
uv run zhs -c 12345
```

### 4.4 刷 AI 课程

AI 课程需要提供课程 ID 和班级 ID：

```bash
uv run zhs -ai 1001 2001
```

禁用 AI 考试（只看视频不答题）：

```bash
uv run zhs -ai 1001 2001 --noexam
```

### 4.5 全刷模式

不指定课程 ID 时，自动刷所有课程（先知到后 Hike）：

```bash
uv run zhs
```

### 4.6 指定视频

只刷特定视频：

```bash
uv run zhs -c ABC123 -v 1001 -v 1002
```

### 4.7 强制指定课程类型

当自动检测不准确时，可手动指定：

```bash
# 强制按知到课程处理
uv run zhs -c 12345 --type zhidao

# 强制按 Hike 课程处理
uv run zhs -c ABC123 --type hike

# 强制按 AI 课程处理
uv run zhs -c 1001 --type ai
```

课程类型自动检测规则：

- ID 含字母 → 知到
- ID 纯数字 → Hike
- `--type` 参数优先级最高

## 5. 常用参数

| 参数                   | 缩写     | 说明                  |
| -------------------- | ------ | ------------------- |
| `--course`           | `-c`   | 课程 ID（可多次指定）        |
| `--type`             | <br /> | 课程类型：zhidao/hike/ai |
| `--videos`           | `-v`   | 视频 ID（可多次指定）        |
| `--speed`            | `-s`   | 播放速度（覆盖配置文件）        |
| `--threshold`        | `-t`   | 完成阈值（覆盖配置文件）        |
| `--limit`            | `-l`   | 时间限制/分钟（覆盖配置文件）     |
| `--fetch`            | `-f`   | 获取课程列表              |
| `--aicourse`         | `-ai`  | AI 课程 ID + 班级 ID    |
| `--noexam`           | <br /> | 禁用 AI 考试            |
| `--proxy`            | <br /> | 代理地址                |
| `--debug`            | `-d`   | 调试模式                |
| `--show-in-terminal` | <br /> | 终端显示二维码             |
| `--image-path`       | <br /> | 二维码保存路径             |
| `--tree-view`        | <br /> | 显示资源树（覆盖配置）         |
| `--progressbar-view` | <br /> | 显示进度条（覆盖配置）         |

## 6. 使用示例

```bash
# 首次使用：获取课程列表
uv run zhs -f

# 刷单个知到课程，1.5 倍速
uv run zhs -c ABC123 -s 1.5

# 刷单个 Hike 课程，限制 30 分钟
uv run zhs -c 12345 -l 30

# 刷 AI 课程（需 moonshot_api_key）
uv run zhs -ai 1001 2001

# 使用代理
uv run zhs --proxy socks5://127.0.0.1:1080

# 调试模式
uv run zhs -c ABC123 -d

# 全刷所有课程
uv run zhs
```

## 7. 代理支持

支持以下代理协议：

```bash
# HTTP/HTTPS 代理
uv run zhs --proxy http://127.0.0.1:7890

# SOCKS5 代理
uv run zhs --proxy socks5://127.0.0.1:1080

# 全协议代理
uv run zhs --proxy all://127.0.0.1:7890
```

也可在 `config.toml` 中配置：

```toml
[proxies]
http = "http://127.0.0.1:7890"
https = "http://127.0.0.1:7890"
```

## 8. 数据目录

程序数据默认保存在 `~/.zhs/` 目录：

| 文件               | 说明            |
| ---------------- | ------------- |
| `config.toml`    | 配置文件          |
| `cookies.json`   | 登录 Cookie     |
| `execution.json` | 课程列表（`-f` 生成） |

## 9. 常见问题

### Q: 登录二维码扫不了？

尝试 `--show-in-terminal` 在终端直接显示二维码，或指定 `--image-path` 保存到自定义路径。

### Q: 课程类型检测错误？

使用 `--type` 参数手动指定：`--type zhidao`、`--type hike` 或 `--type ai`。

### Q: AI 答题报错？

默认使用智慧树内置 AI，无需额外配置。如需自定义 LLM，在 `config.toml` 中设置 `use_zhidao_ai = false` 并填写 `api_key` 和 `base_url`。

### Q: 视频播放卡住？

- 检查网络连接
- 尝试使用代理：`--proxy`
- 开启调试模式查看详细日志：`-d`

### Q: Cookie 过期？

删除 `~/.zhs/cookies.json`，重新登录即可。

### Q: 如何只刷视频不答题？

AI 课程使 用 `--noexam` 参数：

```bash
uv run zhs -ai 1001 2001 --noexam
```

