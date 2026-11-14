#!/usr/bin/env python3
"""离线 API 契约冒烟检查。无需登录，不联网，不提交真实答案。"""

from types import SimpleNamespace
from typing import Any

from zhs.api.zhidao_kg_exam_api import ZhidaoKgExamApi


class OfflineQuery:
    def __init__(self) -> None:
        self._http = SimpleNamespace(urls=SimpleNamespace(aistudy="https://offline.invalid"))
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def query(self, strategy: str, url: str, data: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((strategy, url, data))
        return {"data": {}}


def main() -> None:
    query = OfflineQuery()
    api = ZhidaoKgExamApi(query)  # type: ignore[arg-type]
    api.start_exam("offline-recruit", 123, "offline-node")
    assert query.calls[-1][2] == {"recruitId": "offline-recruit", "courseId": 123, "knowledeId": "offline-node"}
    api.get_mastery_info("offline-recruit", 456, "offline-node")
    assert query.calls[-1][2] == {"recruitId": "offline-recruit", "examId": 456, "knowledeId": "offline-node"}
    print("PASS: 离线 start/mastery 参数契约；未进行真实网络验证或提交。")


if __name__ == "__main__":
    main()
