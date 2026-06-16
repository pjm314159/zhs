"""Hike 职教云课程数据模型"""

from pydantic import BaseModel, Field


class HikeCourse(BaseModel):
    """Hike 课程"""

    course_id: int = Field(alias="courseId")
    course_name: str = Field(alias="courseName")
    model_config = {"populate_by_name": True}


class ResourceNode(BaseModel):
    """资源树节点"""

    id: int
    name: str
    data_type: int | None = Field(default=None, alias="dataType")
    study_time: int | None = Field(default=None, alias="studyTime")
    total_time: int = Field(default=0, alias="totalTime")
    file_id: int | None = Field(default=None, alias="fileId")
    file_name: str | None = Field(default=None, alias="fileName")
    child_list: list["ResourceNode"] | None = Field(default=None, alias="childList")
    model_config = {"populate_by_name": True}


class FileInfo(BaseModel):
    """stuViewFile 返回的文件信息"""

    file_id: int = Field(alias="fileId")
    data_id: int = Field(alias="dataId")
    total_time: int = Field(alias="totalTime")
    model_config = {"populate_by_name": True}
