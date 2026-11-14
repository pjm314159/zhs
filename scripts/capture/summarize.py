"""汇总 cdp_capture.mjs 录下的 JSONL：按接口分组、去重，打印时间线与请求/响应样例。

用法：
    python scripts/capture/summarize.py .capture/xxx.jsonl            # 接口清单 + 调用次数
    python scripts/capture/summarize.py .capture/xxx.jsonl learning   # 只看 URL 含 learning 的时间线
"""

import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit


def _endpoint(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.hostname}{parts.path}"


def _load(path: Path) -> list[dict]:
    records: list[dict] = []
    seen: set[tuple] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        # 同一请求可能从页面和 iframe 两个会话各录一次：按 方法+URL+body 去重（时间相差 1s 内）
        key = (rec.get("t", 0) // 1000, rec.get("method"), rec.get("url"), rec.get("postData"))
        if key in seen:
            continue
        seen.add(key)
        records.append(rec)
    records.sort(key=lambda r: r.get("t", 0))
    return records


def main() -> None:
    path = Path(sys.argv[1])
    needle = sys.argv[2] if len(sys.argv) > 2 else None
    records = _load(path)

    if needle is None:
        counts = Counter((r["method"], _endpoint(r["url"])) for r in records)
        print(f"{len(records)} requests, {len(counts)} endpoints\n")
        for (method, ep), n in sorted(counts.items(), key=lambda kv: kv[0][1]):
            print(f"{n:4d}  {method:5s} {ep}")
        return

    start = records[0]["t"] if records else 0
    for r in records:
        if needle not in r["url"]:
            continue
        print(f"+{(r['t'] - start) / 1000:8.1f}s  {r['method']} {r.get('status')} {r['url'][:200]}")
        if r.get("postData"):
            print(f"           body: {r['postData'][:600]}")
        if r.get("response"):
            print(f"           resp: {r['response'][:600]}")


if __name__ == "__main__":
    main()
