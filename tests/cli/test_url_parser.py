"""cli/url_parser.py 单元测试

覆盖 parse_play_url / parse_homework_url_v2 / parse_exam_url 及数据类。
"""

import pytest

from zhs.cli.url_parser import (
    ParsedExamUrl,
    ParsedHomeworkUrl,
    ParsedPlayUrl,
    parse_exam_url,
    parse_homework_url_v2,
    parse_play_url,
)

# ---------------------------------------------------------------------------
# parse_play_url
# ---------------------------------------------------------------------------


class TestParsePlayUrl:
    """parse_play_url"""

    def test_zhidao_video_url(self) -> None:
        """知到视频 URL → type=zhidao, rac_id"""
        url = "https://studyvideoh5.zhihuishu.com/stuStudy?recruitAndCourseId=49515d50445a4859454a585950465d425e"
        result = parse_play_url(url)
        assert result.type == "zhidao"
        assert result.rac_id == "49515d50445a4859454a585950465d425e"
        assert result.course_id is None
        assert result.class_id is None
        assert result.node_uid is None

    def test_ai_learn_page_url(self) -> None:
        """AI 学习页 URL → type=ai, courseId/nodeUid/classId"""
        url = "https://ai-smart-course-student-pro.zhihuishu.com/learnPage/2036787923612635136/1890313092273934336/203843?catalogActiveTab=personal"
        result = parse_play_url(url)
        assert result.type == "ai"
        assert result.course_id == 2036787923612635136
        assert result.node_uid == 1890313092273934336
        assert result.class_id == 203843
        assert result.rac_id is None

    def test_ai_knowledge_study_url(self) -> None:
        """AI 课程页 URL（knowledgeStudy）→ type=ai, node_uid=None（全刷）"""
        url = "https://ai-smart-course-student-pro.zhihuishu.com/singleCourse/knowledgeStudy/2036787923612635136/203843"
        result = parse_play_url(url)
        assert result.type == "ai"
        assert result.course_id == 2036787923612635136
        assert result.class_id == 203843
        assert result.node_uid is None
        assert result.rac_id is None

    def test_unsupported_url_raises(self) -> None:
        """不支持的 URL → ValueError"""
        with pytest.raises(ValueError, match="play 命令不支持该 URL"):
            parse_play_url("https://example.com/other/123")

    def test_dohomework_url_raises(self) -> None:
        """play 不接受 dohomework URL"""
        with pytest.raises(ValueError, match="play 命令不支持该 URL"):
            parse_play_url("https://example.com/dohomework/1/2/3/4/5/0")

    def test_testdetail_url_raises(self) -> None:
        """play 不接受 testDetail URL"""
        with pytest.raises(ValueError, match="play 命令不支持该 URL"):
            parse_play_url("https://example.com/testDetail/1/2/3/4/5")


# ---------------------------------------------------------------------------
# parse_homework_url_v2
# ---------------------------------------------------------------------------


class TestParseHomeworkUrlV2:
    """parse_homework_url_v2"""

    def test_zhidao_dohomework_url(self) -> None:
        """知到作业 dohomework URL → type=zhidao_direct"""
        url = "https://onlineexamh5new.zhihuishu.com/stuExamWeb.html#/webExamList/dohomework/100/200/300/400/500/0"
        result = parse_homework_url_v2(url)
        assert result.type == "zhidao_direct"
        assert result.recruit_id == "100"
        assert result.stu_exam_id == "200"
        assert result.exam_id == "300"
        assert result.course_id == "400"
        assert result.school_id == "500"

    def test_zhidao_dohomework_with_query(self) -> None:
        """知到作业 URL 带 query string"""
        url = "https://example.com/dohomework/R1/STU1/EXAM1/C1/S1/0?foo=bar"
        result = parse_homework_url_v2(url)
        assert result.type == "zhidao_direct"
        assert result.recruit_id == "R1"
        assert result.stu_exam_id == "STU1"
        assert result.exam_id == "EXAM1"
        assert result.course_id == "C1"
        assert result.school_id == "S1"

    def test_ai_learn_page_direct_mode(self) -> None:
        """AI learnPage URL → type=ai_direct（直接模式）"""
        url = (
            "https://ai-smart-course-student-pro.zhihuishu.com/learnPage/2036787923612635136/1890313092273934336/203843"
        )
        result = parse_homework_url_v2(url)
        assert result.type == "ai_direct"
        assert result.course_id == 2036787923612635136
        assert result.node_uid == 1890313092273934336
        assert result.class_id == 203843

    def test_ai_knowledge_study_scan_mode(self) -> None:
        """AI knowledgeStudy URL → type=ai_scan（扫描模式）"""
        url = "https://ai-smart-course-student-pro.zhihuishu.com/singleCourse/knowledgeStudy/2036787923612635136/203843"
        result = parse_homework_url_v2(url)
        assert result.type == "ai_scan"
        assert result.course_id == 2036787923612635136
        assert result.class_id == 203843
        assert result.node_uid is None

    def test_unsupported_url_raises(self) -> None:
        """不支持的 URL → ValueError"""
        with pytest.raises(ValueError, match="homework 命令不支持该 URL"):
            parse_homework_url_v2("https://example.com/other/123")

    def test_testdetail_url_raises(self) -> None:
        """homework 不接受 testDetail URL"""
        with pytest.raises(ValueError, match="homework 命令不支持该 URL"):
            parse_homework_url_v2("https://example.com/testDetail/1/2/3/4/5")


# ---------------------------------------------------------------------------
# parse_exam_url
# ---------------------------------------------------------------------------


class TestParseExamUrl:
    """parse_exam_url"""

    def test_ai_test_detail_url(self) -> None:
        """AI 考试 testDetail URL → type=ai_direct"""
        url = (
            "https://ai-smart-course-student-pro.zhihuishu.com/testDetail/"
            "2036787923612635136/203843/2786542/270661609/416884"
            "?examType=0&mapUid=1879396934922407936&currentLabel=1"
        )
        result = parse_exam_url(url)
        assert result.type == "ai_direct"
        assert result.course_id == 2036787923612635136
        assert result.class_id == 203843
        assert result.exam_test_id == 2786542
        assert result.exam_paper_id == 270661609

    def test_ai_test_detail_ignores_fifth_segment(self) -> None:
        """testDetail 第 5 段被忽略（正则只匹配 4 段）"""
        url = "https://example.com/testDetail/100/200/300/400/500"
        result = parse_exam_url(url)
        assert result.course_id == 100
        assert result.class_id == 200
        assert result.exam_test_id == 300
        assert result.exam_paper_id == 400

    def test_learnpage_url_raises(self) -> None:
        """exam 不接受 learnPage URL（改用 testDetail）"""
        with pytest.raises(ValueError, match="exam 命令不支持该 URL"):
            parse_exam_url("https://example.com/learnPage/1/2/3")

    def test_dohomework_url_raises(self) -> None:
        """exam 不接受 dohomework URL"""
        with pytest.raises(ValueError, match="exam 命令不支持该 URL"):
            parse_exam_url("https://example.com/dohomework/1/2/3/4/5/0")

    def test_unsupported_url_raises(self) -> None:
        """不支持的 URL → ValueError"""
        with pytest.raises(ValueError, match="exam 命令不支持该 URL"):
            parse_exam_url("https://example.com/other/123")


# ---------------------------------------------------------------------------
# 数据类字段
# ---------------------------------------------------------------------------


class TestParsedDataClasses:
    """ParsedPlayUrl / ParsedHomeworkUrl / ParsedExamUrl 数据类"""

    def test_parsed_play_url_defaults(self) -> None:
        """ParsedPlayUrl 默认值"""
        p = ParsedPlayUrl(type="zhidao")
        assert p.rac_id is None
        assert p.course_id is None
        assert p.class_id is None
        assert p.node_uid is None

    def test_parsed_homework_url_defaults(self) -> None:
        """ParsedHomeworkUrl 默认值"""
        p = ParsedHomeworkUrl(type="ai_direct")
        assert p.recruit_id is None
        assert p.stu_exam_id is None
        assert p.exam_id is None
        assert p.course_id is None
        assert p.school_id is None
        assert p.class_id is None
        assert p.node_uid is None

    def test_parsed_exam_url_defaults(self) -> None:
        """ParsedExamUrl 默认值"""
        p = ParsedExamUrl(type="ai_direct")
        assert p.course_id is None
        assert p.class_id is None
        assert p.exam_test_id is None
        assert p.exam_paper_id is None
