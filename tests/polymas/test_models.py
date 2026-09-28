"""polymas 树节点模型测试

fixture 结构按 probe_polymas.py walk 读取的键反推（PR #168），
hikeAiCourse 真实响应待 F10 校正。
"""

from typing import Any

import pytest

from zhs.polymas.models import PolymasNode, PolymasVideoNode


def _folder(
    node_id: Any,
    title: str,
    children: list[dict[str, Any]],
) -> dict[str, Any]:
    """章节 folder 节点"""
    return {
        "nodeId": node_id,
        "isFinished": None,
        "detail": {"classify": "folder", "title": title},
        "children": children,
    }


def _file(
    node_id: Any,
    title: str,
    oss_url: str | None = "https://oss.example.com/v.mp4",
    duration: Any = 600,
    is_finished: bool | None = False,
    percentage: Any = 0.0,
) -> dict[str, Any]:
    """视频 file 节点（ext 为 JSON 字符串，照 probe 解析方式）"""
    ext = f'{{"ossUrl": "{oss_url}", "duration": {duration}}}' if oss_url is not None else "{}"
    return {
        "nodeId": node_id,
        "isFinished": is_finished,
        "isRequire": True,
        "completePercentage": percentage,
        "detail": {"classify": "file", "title": title, "ext": ext},
        "children": None,
    }


class TestPolymasNode:
    def test_parses_tree_shape(self) -> None:
        """folder/file 混合树解析（children=None 容忍为空列表）"""
        tree = _folder(1, "第一章", [_file(2, "视频1")])
        node = PolymasNode.model_validate(tree)
        assert node.node_id == "1"
        assert node.classify == "folder"
        assert node.title == "第一章"
        assert node.children[0].classify == "file"
        assert node.children[0].children == []

    def test_node_id_str_coerce(self) -> None:
        """数字 nodeId 自动转 str（pydantic v2 不做 int→str 隐式转换）"""
        node = PolymasNode.model_validate(_file(2036787923612635136, "大ID视频"))
        assert node.node_id == "2036787923612635136"

    def test_percentage_and_finished(self) -> None:
        """completePercentage 数字串转 float，isFinished 透传"""
        node = PolymasNode.model_validate(_file(1, "v", percentage="55.5", is_finished=True))
        assert node.complete_percentage == 55.5
        assert node.is_finished is True

    def test_percentage_null(self) -> None:
        """completePercentage=null → None"""
        node = PolymasNode.model_validate(_file(1, "v", percentage=None))
        assert node.complete_percentage is None

    def test_detail_missing(self) -> None:
        """detail 缺失 → classify/title 空串"""
        node = PolymasNode.model_validate({"nodeId": 1})
        assert node.classify == ""
        assert node.title == ""


class TestFlattenVideos:
    def test_collects_files_with_chapter(self) -> None:
        """file 节点展平，chapter 继承最近的 folder title"""
        tree = [
            _folder(
                1,
                "第一章",
                [
                    _file(2, "视频1", duration=600),
                    _folder(3, "小节", [_file(4, "视频2", duration=300)]),
                ],
            ),
            _folder(5, "第二章", [_file(6, "视频3", duration=100)]),
        ]
        nodes = [PolymasNode.model_validate(n) for n in tree]
        videos = [v for n in nodes for v in n.flatten_videos()]
        assert [(v.resource_id, v.title, v.chapter) for v in videos] == [
            ("2", "视频1", "第一章"),
            ("4", "视频2", "小节"),
            ("6", "视频3", "第二章"),
        ]
        assert videos[0].oss_url == "https://oss.example.com/v.mp4"
        assert videos[0].duration == 600.0

    def test_ext_invalid_json(self) -> None:
        """ext 非 JSON → oss_url None / duration 0.0（不抛异常）"""
        node = PolymasNode.model_validate(
            {
                "nodeId": 1,
                "detail": {"classify": "file", "title": "坏ext", "ext": "not-json{"},
            }
        )
        videos = node.flatten_videos()
        assert len(videos) == 1
        assert videos[0].oss_url is None
        assert videos[0].duration == 0.0

    def test_ext_missing_fields(self) -> None:
        """ext JSON 缺 ossUrl/duration → 默认值"""
        node = PolymasNode.model_validate({"nodeId": 1, "detail": {"classify": "file", "title": "空ext", "ext": "{}"}})
        videos = node.flatten_videos()
        assert videos[0].oss_url is None
        assert videos[0].duration == 0.0

    def test_non_file_ignored(self) -> None:
        """classify 非 file（如 folder）不进视频列表"""
        node = PolymasNode.model_validate(_folder(1, "章节", []))
        assert node.flatten_videos() == []

    def test_top_level_file_no_chapter(self) -> None:
        """顶层 file（无 folder 包裹）chapter 为空串"""
        node = PolymasNode.model_validate(_file(9, "裸视频"))
        videos = node.flatten_videos()
        assert videos[0].chapter == ""


class TestPolymasVideoNode:
    def test_direct_construction(self) -> None:
        """播放用视频节点直接构造"""
        v = PolymasVideoNode(resource_id="123", title="t", duration=100.0)
        assert v.resource_id == "123"
        assert v.chapter == ""
        assert v.is_finished is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0, "0"),
        (123, "123"),
        ("abc", "abc"),
    ],
)
def test_node_id_variants(raw: Any, expected: str) -> None:
    """nodeId 数字/字符串统一 str 化"""
    node = PolymasNode.model_validate({"nodeId": raw})
    assert node.node_id == expected
