"""按命令分层的 URL 解析

每个命令一个专属解析函数，用 URL 路径结构（正则）识别类型，不依赖域名前缀。

支持的 URL:
- play: 知到视频 (recruitAndCourseId=xxx) / AI 学习页 (learnPage/{cid}/{nodeUid}/{classId})
- homework: 知到作业 (dohomework/...) / AI 学习页 (learnPage) / AI 课程页 (knowledgeStudy)
- exam: AI 考试 (testDetail/{courseId}/{classId}/{examTestId}/{examPaperId})
"""

import re
from dataclasses import dataclass


@dataclass
class ParsedPlayUrl:
    """play 命令解析结果"""

    type: str  # "zhidao" / "ai"
    rac_id: str | None = None
    course_id: int | None = None
    class_id: int | None = None
    node_uid: int | None = None


@dataclass
class ParsedHomeworkUrl:
    """homework 命令解析结果"""

    type: str  # "zhidao_direct" / "ai_direct" / "ai_scan"
    # 知到作业（zhidao_direct）
    recruit_id: str | None = None
    stu_exam_id: str | None = None
    exam_id: str | None = None
    course_id: int | str | None = None
    school_id: str | None = None
    # AI 课程（ai_direct / ai_scan）
    class_id: int | None = None
    node_uid: int | None = None


@dataclass
class ParsedExamUrl:
    """exam 命令解析结果"""

    type: str  # "ai_direct" / ...
    course_id: int | None = None
    class_id: int | None = None
    exam_test_id: int | None = None
    exam_paper_id: int | None = None


def parse_play_url(url: str) -> ParsedPlayUrl:
    """解析 play 命令的 URL

    支持:
    - 知到视频: recruitAndCourseId=xxx
    - AI 学习页（直接模式）: learnPage/{courseId}/{nodeUid}/{classId}
    - AI 课程页（扫描模式）: knowledgeStudy/{courseId}/{classId}
    """
    # 知到视频
    m = re.search(r"recruitAndCourseId=([a-zA-Z0-9]+)", url)
    if m:
        return ParsedPlayUrl(type="zhidao", rac_id=m.group(1))

    # AI 学习页（3 段：courseId/nodeUid/classId）
    m = re.search(r"learnPage/(\d+)/(\d+)/(\d+)", url)
    if m:
        return ParsedPlayUrl(
            type="ai",
            course_id=int(m.group(1)),
            node_uid=int(m.group(2)),
            class_id=int(m.group(3)),
        )

    # AI 课程页（扫描模式，无 nodeUid，全刷）
    m = re.search(r"knowledgeStudy/(\d+)/(\d+)", url)
    if m:
        return ParsedPlayUrl(
            type="ai",
            course_id=int(m.group(1)),
            class_id=int(m.group(2)),
        )

    raise ValueError(
        f"play 命令不支持该 URL\n"
        f"支持的格式:\n"
        f"  知到: ...?recruitAndCourseId=xxx\n"
        f"  AI 直接: .../learnPage/{{courseId}}/{{nodeUid}}/{{classId}}\n"
        f"  AI 扫描: .../knowledgeStudy/{{courseId}}/{{classId}}\n"
        f"实际 URL: {url}"
    )


def parse_homework_url_v2(url: str) -> ParsedHomeworkUrl:
    """解析 homework 命令的 URL

    支持:
    - 知到作业: dohomework/{recruitId}/{stuExamId}/{examId}/{courseId}/{schoolId}/...
    - AI 学习页（直接模式）: learnPage/{courseId}/{nodeUid}/{classId}
    - AI 课程页（扫描模式）: knowledgeStudy/{courseId}/{classId}
    """
    # 知到作业 dohomework（5 段路径参数）
    m = re.search(r"dohomework/([^/]+)/([^/]+)/([^/]+)/([^/]+)/([^/]+)", url)
    if m:
        return ParsedHomeworkUrl(
            type="zhidao_direct",
            recruit_id=m.group(1),
            stu_exam_id=m.group(2),
            exam_id=m.group(3),
            course_id=m.group(4),
            school_id=m.group(5),
        )

    # AI 学习页（直接模式，有 nodeUid）
    m = re.search(r"learnPage/(\d+)/(\d+)/(\d+)", url)
    if m:
        return ParsedHomeworkUrl(
            type="ai_direct",
            course_id=int(m.group(1)),
            node_uid=int(m.group(2)),
            class_id=int(m.group(3)),
        )

    # AI 课程页（扫描模式，无 nodeUid）
    m = re.search(r"knowledgeStudy/(\d+)/(\d+)", url)
    if m:
        return ParsedHomeworkUrl(
            type="ai_scan",
            course_id=int(m.group(1)),
            class_id=int(m.group(2)),
        )

    raise ValueError(
        f"homework 命令不支持该 URL\n"
        f"支持的格式:\n"
        f"  知到作业: .../dohomework/...\n"
        f"  AI 直接: .../learnPage/{{courseId}}/{{nodeUid}}/{{classId}}\n"
        f"  AI 扫描: .../knowledgeStudy/{{courseId}}/{{classId}}\n"
        f"实际 URL: {url}"
    )


def parse_exam_url(url: str) -> ParsedExamUrl:
    """解析 exam 命令的 URL

    支持:
    - AI 考试: testDetail/{courseId}/{classId}/{examTestId}/{examPaperId}/{?}

    URL 示例:
    https://ai-smart-course-student-pro.zhihuishu.com/testDetail/2036787923612635136/203843/2786542/270661609/416884?examType=0

    路径参数:
    - 第 1 段: courseId
    - 第 2 段: classId
    - 第 3 段: examTestId
    - 第 4 段: examPaperId
    - 第 5 段: 忽略（正则只匹配 4 段）

    注: examId 不在 URL 路径中，需通过 API 查询获取。
    """
    # AI 考试 testDetail（4 段必需，第 5 段忽略）
    m = re.search(r"testDetail/(\d+)/(\d+)/(\d+)/(\d+)", url)
    if m:
        return ParsedExamUrl(
            type="ai_direct",
            course_id=int(m.group(1)),
            class_id=int(m.group(2)),
            exam_test_id=int(m.group(3)),
            exam_paper_id=int(m.group(4)),
        )

    raise ValueError(
        f"exam 命令不支持该 URL\n"
        f"支持的格式:\n"
        f"  AI: .../testDetail/{{courseId}}/{{classId}}/{{examTestId}}/{{examPaperId}}/...\n"
        f"实际 URL: {url}"
    )


__all__ = [
    "ParsedExamUrl",
    "ParsedHomeworkUrl",
    "ParsedPlayUrl",
    "parse_exam_url",
    "parse_homework_url_v2",
    "parse_play_url",
]
