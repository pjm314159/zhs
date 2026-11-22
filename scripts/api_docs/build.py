"""构建 API 文档：内联 operations → 编译 x-zhs-* → 调 Redocly CLI → 可选离线化。

用法：
    uv run python scripts/api_docs/build.py                 # 生成 CDN 版 html
    uv run python scripts/api_docs/build.py --offline       # 生成离线单文件
    uv run python scripts/api_docs/build.py --no-build      # 只产出 bundled spec

依赖：Node 20+（`npx @redocly/cli`）、pyyaml（dev 依赖）。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
API_DIR = ROOT / "docs" / "api"
ENTRY = API_DIR / "openapi.yaml"
BUILD_DIR = API_DIR / "build"
BUNDLED = BUILD_DIR / "openapi.bundled.yaml"
HTML = BUILD_DIR / "api.html"
VENDOR_JS = API_DIR / "vendor" / "redoc.standalone.js"

REDOCLY = ["npx", "--yes", "@redocly/cli@2", "build-docs"]

DOMAINS: dict[str, str] = {
    "base": "https://onlineservice-api.zhihuishu.com",
    "study": "https://studyservice-api.zhihuishu.com",
    "homework": "https://studentexam-api.zhihuishu.com",
    "taurusexam": "https://taurusexam-api.zhihuishu.com",
    "exam": "https://studentexamtest.zhihuishu.com",
    "ai": "https://kg-ai-run.zhihuishu.com",
    "ai_task": "https://kg-run-student.zhihuishu.com",
    "ai_analysis": "https://ai-course-assistant-api.zhihuishu.com",
    "newbase": "https://newbase.zhihuishu.com",
    "passport": "https://passport.zhihuishu.com",
    "user": "https://user.zhihuishu.com",
    "hikeservice": "https://hikeservice.zhihuishu.com",
    "studyresources": "https://studyresources.zhihuishu.com",
    "hike_teaching": "https://hike-teaching.zhihuishu.com",
}

STATUS_TEXT: dict[str, str] = {
    "confirmed": "已确认",
    "observed": "已观测",
    "pending": "待复核",
    "code-only": "仅代码",
    "doc-only": "仅文档",
}

EXPORT_TAIL = "export{RedocStandalone,hydrate,init};"


def inline_operations(node: Any, base_dir: Path) -> Any:
    """把 './operations/**.yaml' 整文件引用替换为文件内容；保留 '#/...' 本地引用。"""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("./") and "#" not in ref:
            target = (base_dir / ref).resolve()
            try:
                data: Any = yaml.safe_load(target.read_text(encoding="utf-8"))
            except yaml.YAMLError as exc:
                raise SystemExit(f"{target.relative_to(ROOT)} 解析失败：\n{exc}") from exc
            return inline_operations(data, target.parent)
        return {key: inline_operations(value, base_dir) for key, value in node.items()}
    if isinstance(node, list):
        return [inline_operations(item, base_dir) for item in node]
    return node


def compile_operation(op: dict[str, Any], path: str, method: str) -> None:
    """把 x-zhs-* 编译成页面可见的 description / security / requestBody。"""
    meta: list[str] = []

    evidence = op.get("x-zhs-evidence") or {}
    captured = evidence.get("capturedAt")
    if captured:
        meta.append(f"- **更新时间**：{captured}")

    service = op.get("x-zhs-service")
    if service:
        domain = DOMAINS.get(service)
        if domain is None:
            raise SystemExit(f"{path} {method}: 未知的 x-zhs-service '{service}'")
        meta.append(f"- **完整 URL**：`{method.upper()} {domain}{path}`")

    parts: list[str] = []
    if meta:
        parts.append("\n".join(meta))

    description = (op.get("description") or "").strip()
    if description:
        parts.append(description)

    notes = (op.get("x-zhs-notes") or "").strip()
    if notes:
        parts.append(notes)

    crypto = op.get("x-zhs-crypto")
    if crypto:
        raw = (crypto.get("rawExample") or "").strip()
        if raw:
            parts.append("### 原始报文（加密后）\n\n```json\n" + raw + "\n```")
        apply_crypto(op, crypto)

    status = op.get("x-zhs-status")
    if status:
        parts.append(f"- **状态**：{STATUS_TEXT.get(status, status)}")

    op["description"] = "\n\n".join(parts)


def apply_crypto(op: dict[str, Any], crypto: dict[str, Any]) -> None:
    key = crypto.get("key")
    if not key:
        raise SystemExit("x-zhs-crypto 缺少 key")
    op["security"] = [{f"AES-128-CBC ({key})": []}]

    plain = crypto.get("plainSchema")
    if plain and "requestBody" not in op:
        media: dict[str, Any] = {"schema": plain}
        example = crypto.get("example")
        if example:
            media["examples"] = {"example": {"value": example}}
        op["requestBody"] = {"content": {"application/json": media}}
        op.setdefault("parameters", []).append(
            {
                "name": "Content-Type",
                "in": "header",
                "required": True,
                "description": "固定为 `application/json`",
                "schema": {"type": "string", "default": "application/json"},
            }
        )


def project_version() -> str:
    """从 pyproject.toml 读取项目版本，保证文档版本与 zhs 一致。"""
    data: dict[str, Any] = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version: str = data["project"]["version"]
    return version


def bundle() -> dict[str, Any]:
    spec: dict[str, Any] = yaml.safe_load(ENTRY.read_text(encoding="utf-8"))
    spec = inline_operations(spec, ENTRY.parent)
    spec["info"]["version"] = project_version()

    for path, item in spec.get("paths", {}).items():
        for method, op in item.items():
            if method in {"get", "post", "put", "patch", "delete", "head", "options"}:
                compile_operation(op, path, method)
    return spec


def write_bundled(spec: dict[str, Any]) -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    BUNDLED.write_text(
        yaml.safe_dump(spec, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    print(f"已生成 {BUNDLED.relative_to(ROOT)}")


def run_redocly() -> None:
    cmd = [*REDOCLY, str(BUNDLED), "-o", str(HTML)]
    if os.name == "nt":
        subprocess.run(subprocess.list2cmdline(cmd), check=True, shell=True)
    else:
        subprocess.run(cmd, check=True)
    print(f"已生成 {HTML.relative_to(ROOT)}")


def inline_js() -> None:
    if not VENDOR_JS.exists():
        raise SystemExit(
            f"缺少 {VENDOR_JS.relative_to(ROOT)}，先下载：\n"
            "  curl -o docs/api/vendor/redoc.standalone.js "
            "https://cdn.redocly.com/redoc/v3.1.0/bundles/redoc.standalone.js"
        )

    js = VENDOR_JS.read_text(encoding="utf-8")
    if not js.endswith(EXPORT_TAIL):
        raise SystemExit("vendor bundle 结尾不是预期 export，停止内联")
    body = js[: -len(EXPORT_TAIL)]

    html = HTML.read_text(encoding="utf-8")
    html = re.sub(r'\s*<link rel="modulepreload"[^>]*redoc\.standalone\.js[^>]*/>', "", html)
    html, count = re.subn(r'import \{ hydrate \} from "[^"]*redoc\.standalone\.js";', "", html)
    if count != 1:
        raise SystemExit(f"预期 1 处 import，实际 {count} 处")

    marker = '<script type="module">'
    index = html.find(marker)
    if index < 0:
        raise SystemExit("找不到 module script")
    html = html[: index + len(marker)] + body + html[index + len(marker) :]
    HTML.write_text(html, encoding="utf-8")

    size_kb = HTML.stat().st_size / 1024
    print(f"已内联 vendor JS，离线版 {HTML.relative_to(ROOT)}（{size_kb:.0f} KB）")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="构建智慧树 API 文档")
    parser.add_argument("--no-build", action="store_true", help="只产出 bundled spec")
    parser.add_argument("--offline", action="store_true", help="内联 ReDoc，生成离线单文件")
    args = parser.parse_args(argv)

    spec = bundle()
    write_bundled(spec)

    if args.no_build:
        return 0

    run_redocly()
    if args.offline:
        inline_js()
    return 0


if __name__ == "__main__":
    sys.exit(main())
