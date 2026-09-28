"""polymas 智慧课程数据模型"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PolymasCourse(BaseModel):
    """queryStudentCourse 条目（仅 courseType==hikeAiCourse 进入播放流程）

    字段类型说明：服务端 courseId/terms 可能返回 JSON 数字（大整数），
    pydantic v2 不做 int→str 隐式转换，故用 before validator 统一 str 化。
    """

    model_config = ConfigDict(populate_by_name=True)

    course_id: str = Field(alias="courseId")
    course_name: str = Field(alias="courseName")
    course_type: str = Field(alias="courseType")
    terms: list[str] = Field(default_factory=list)
    class_id: str | None = Field(default=None, alias="classId")
    student_classes: list[dict[str, Any]] = Field(default_factory=list, alias="studentClasses")

    @field_validator("course_id", "course_type", "class_id", mode="before")
    @classmethod
    def _coerce_str(cls, v: Any) -> str | None:
        return None if v is None else str(v)

    @field_validator("terms", mode="before")
    @classmethod
    def _coerce_terms(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(t) for t in v]

    @field_validator("student_classes", mode="before")
    @classmethod
    def _coerce_student_classes(cls, v: Any) -> list[dict[str, Any]]:
        return v if isinstance(v, list) else []

    @property
    def term(self) -> str:
        """学期（terms[0]，无则空串）——polymas 各接口必需参数"""
        return self.terms[0] if self.terms else ""

    def student_class_id(self) -> str | None:
        """PR #168 班级来源：studentClasses[0].classId（顶层 classId 为空时的次选）"""
        for item in self.student_classes:
            if isinstance(item, dict) and item.get("classId"):
                return str(item["classId"])
        return None


class PolymasNodeDetail(BaseModel):
    """queryTree 节点 detail（字段按 PR #168 反推，TODO: F10 实测校正）"""

    model_config = ConfigDict(populate_by_name=True)

    classify: str | None = None  # folder / file
    title: str | None = None
    ext: str | None = None  # JSON 字符串，file 节点含 ossUrl/duration


class PolymasNode(BaseModel):
    """queryTree 树节点（字段按 PR #168 反推，TODO: F10 实测校正）"""

    model_config = ConfigDict(populate_by_name=True)

    node_id: str = Field(alias="nodeId")
    is_finished: bool | None = Field(default=None, alias="isFinished")
    is_require: bool | None = Field(default=None, alias="isRequire")
    complete_percentage: float | None = Field(default=None, alias="completePercentage")
    detail: PolymasNodeDetail | None = None
    children: list[PolymasNode] = Field(default_factory=list)

    @field_validator("node_id", mode="before")
    @classmethod
    def _coerce_node_id(cls, v: Any) -> str:
        return "" if v is None else str(v)

    @field_validator("complete_percentage", mode="before")
    @classmethod
    def _coerce_percentage(cls, v: Any) -> float | None:
        return None if v is None else float(v)

    @field_validator("children", mode="before")
    @classmethod
    def _coerce_children(cls, v: Any) -> list[Any]:
        return v if isinstance(v, list) else []

    @property
    def classify(self) -> str:
        """节点分类（folder/file），detail 缺失时为空串"""
        return (self.detail.classify if self.detail else "") or ""

    @property
    def title(self) -> str:
        """节点标题，detail 缺失时为空串"""
        return (self.detail.title if self.detail else "") or ""

    def flatten_videos(self, chapter: str = "") -> list[PolymasVideoNode]:
        """递归展平为视频节点列表（不做视频合法性过滤，由 manager 负责）"""
        videos: list[PolymasVideoNode] = []
        if self.classify == "folder":
            chapter = self.title
        if self.classify == "file":
            oss_url: str | None = None
            duration = 0.0
            try:
                ext: dict[str, Any] = json.loads(self.detail.ext or "{}") if self.detail else {}
            except json.JSONDecodeError:
                ext = {}
            if isinstance(ext, dict):
                oss_url = ext.get("ossUrl")
                duration = float(ext["duration"]) if ext.get("duration") is not None else 0.0
            videos.append(
                PolymasVideoNode(
                    resource_id=self.node_id,
                    title=self.title,
                    chapter=chapter,
                    oss_url=oss_url,
                    duration=duration,
                    is_finished=self.is_finished,
                    is_require=self.is_require,
                    complete_percentage=self.complete_percentage,
                )
            )
        for child in self.children:
            videos.extend(child.flatten_videos(chapter))
        return videos


class PolymasVideoNode(BaseModel):
    """展平后的视频节点（播放/上报载体）"""

    resource_id: str
    title: str = ""
    chapter: str = ""
    oss_url: str | None = None
    duration: float = 0.0
    is_finished: bool | None = None
    is_require: bool | None = None
    complete_percentage: float | None = None


__all__ = ["PolymasCourse", "PolymasNode", "PolymasNodeDetail", "PolymasVideoNode"]
