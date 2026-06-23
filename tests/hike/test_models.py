"""Task 4.1 — hike/models.py TDD"""

from zhs.hike.models import FileInfo, HikeCourse, ResourceNode


class TestHikeCourse:
    """HikeCourse 从 API JSON 构建"""

    def test_from_api_json(self) -> None:
        data = {"courseId": 12345, "courseName": "Python 入门"}
        course = HikeCourse.model_validate(data)
        assert course.course_id == 12345
        assert course.course_name == "Python 入门"

    def test_alias_mapping(self) -> None:
        """字段使用 alias 映射 API 返回的驼峰命名"""
        course = HikeCourse.model_validate({"courseId": 1, "courseName": "test"})
        assert course.course_id == 1
        assert course.course_name == "test"


class TestResourceNode:
    """ResourceNode 递归资源树节点"""

    def test_basic_node(self) -> None:
        data = {"id": 100, "name": "第一章", "dataType": 3, "totalTime": 600}
        node = ResourceNode.model_validate(data)
        assert node.id == 100
        assert node.name == "第一章"
        assert node.data_type == 3
        assert node.total_time == 600

    def test_data_type_default_none(self) -> None:
        """data_type 默认为 None（测验等无类型节点）"""
        node = ResourceNode.model_validate({"id": 1, "name": "测验"})
        assert node.data_type is None

    def test_study_time_default_none(self) -> None:
        """study_time 可能为 None"""
        node = ResourceNode.model_validate({"id": 1, "name": "视频", "totalTime": 100})
        assert node.study_time is None

    def test_recursive_child_list(self) -> None:
        """child_list 递归子节点"""
        data = {
            "id": 1,
            "name": "根",
            "childList": [
                {"id": 2, "name": "子1"},
                {"id": 3, "name": "子2", "childList": [{"id": 4, "name": "孙1"}]},
            ],
        }
        node = ResourceNode.model_validate(data)
        assert node.child_list is not None
        assert len(node.child_list) == 2
        assert node.child_list[0].id == 2
        assert node.child_list[1].child_list is not None
        assert node.child_list[1].child_list[0].id == 4

    def test_child_list_default_none(self) -> None:
        """child_list 默认 None（叶子节点）"""
        node = ResourceNode.model_validate({"id": 1, "name": "叶子"})
        assert node.child_list is None

    def test_file_id_optional(self) -> None:
        """file_id 可选（非文件节点无此字段）"""
        node = ResourceNode.model_validate({"id": 1, "name": "章节"})
        assert node.file_id is None

    def test_file_id_present(self) -> None:
        """file_id 存在时正确解析"""
        data = {"id": 1, "name": "视频", "fileId": 999}
        node = ResourceNode.model_validate(data)
        assert node.file_id == 999

    def test_file_name_optional(self) -> None:
        """file_name 可选"""
        node = ResourceNode.model_validate({"id": 1, "name": "节点"})
        assert node.file_name is None

    def test_populate_by_name(self) -> None:
        """支持通过 Python 字段名构造"""
        node = ResourceNode.model_validate({"id": 1, "name": "test", "dataType": 3, "totalTime": 100})
        assert node.data_type == 3
        assert node.total_time == 100


class TestFileInfo:
    """stuViewFile 返回的文件信息"""

    def test_from_api_json(self) -> None:
        data = {"fileId": 100, "dataId": 200, "totalTime": 600}
        info = FileInfo.model_validate(data)
        assert info.file_id == 100
        assert info.data_id == 200
        assert info.total_time == 600

    def test_alias_mapping(self) -> None:
        info = FileInfo.model_validate({"fileId": 1, "dataId": 2, "totalTime": 100})
        assert info.file_id == 1
        assert info.data_id == 2
        assert info.total_time == 100
