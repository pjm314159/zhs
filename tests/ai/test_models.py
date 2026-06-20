"""Task 6.1 — ai/models.py TDD"""

from pydantic import BaseModel

from zhs.ai.models import (
    AiCourseInfo,
    AnswerCache,
    ExamInfo,
    KnowledgePoint,
    OptionVo,
    QuestionContent,
    QuestionSheet,
    Resource,
    ResourceDetail,
    Theme,
)


class TestKnowledgePoint:
    """知识点模型"""

    def test_basic_construction(self) -> None:
        """基本构造"""
        kp = KnowledgePoint(knowledge_id=1, knowledge_name="Python基础")
        assert kp.knowledge_id == 1
        assert kp.knowledge_name == "Python基础"
        assert kp.study_progress == 0

    def test_with_progress(self) -> None:
        """带学习进度"""
        kp = KnowledgePoint(knowledge_id=2, knowledge_name="函数", study_progress=80)
        assert kp.study_progress == 80

    def test_from_api_json(self) -> None:
        """从 API JSON 构建"""
        data = {"knowledgeId": 1, "knowledgeName": "面向对象", "studyProgress": 50}
        kp = KnowledgePoint.model_validate(data)
        assert kp.knowledge_id == 1
        assert kp.knowledge_name == "面向对象"
        assert kp.study_progress == 50


class TestTheme:
    """主题模型"""

    def test_basic_construction(self) -> None:
        """基本构造"""
        theme = Theme(theme_name="第一章")
        assert theme.theme_name == "第一章"
        assert theme.knowledge_list == []

    def test_with_knowledge_points(self) -> None:
        """包含知识点"""
        kp = KnowledgePoint(knowledge_id=1, knowledge_name="变量")
        theme = Theme(theme_name="第一章", knowledge_list=[kp])
        assert len(theme.knowledge_list) == 1
        assert theme.knowledge_list[0].knowledge_name == "变量"

    def test_from_api_json(self) -> None:
        """从 API JSON 构建"""
        data = {
            "themeName": "第一章",
            "knowledgeList": [
                {"knowledgeId": 1, "knowledgeName": "变量", "studyProgress": 0},
            ],
        }
        theme = Theme.model_validate(data)
        assert theme.theme_name == "第一章"
        assert len(theme.knowledge_list) == 1


class TestAiCourseInfo:
    """AI 课程信息模型"""

    def test_basic_construction(self) -> None:
        """基本构造"""
        info = AiCourseInfo(course_name="Python入门")
        assert info.course_name == "Python入门"
        assert info.cake_theme_list == []

    def test_from_api_json(self) -> None:
        """从 API JSON 构建"""
        data = {
            "courseName": "Python入门",
            "cakeThemeList": [
                {
                    "themeName": "第一章",
                    "knowledgeList": [
                        {"knowledgeId": 1, "knowledgeName": "变量", "studyProgress": 100},
                    ],
                }
            ],
        }
        info = AiCourseInfo.model_validate(data)
        assert info.course_name == "Python入门"
        assert len(info.cake_theme_list) == 1
        assert info.cake_theme_list[0].knowledge_list[0].study_progress == 100


class TestResourceDetail:
    """资源详情模型"""

    def test_basic_construction(self) -> None:
        """基本构造"""
        rd = ResourceDetail(
            resources_uid=100,
            resources_name="课件1",
            resources_type=1,
            resources_distribute_type=4,
        )
        assert rd.resources_uid == 100
        assert rd.resources_name == "课件1"
        assert rd.resources_type == 1
        assert rd.resources_distribute_type == 4
        assert rd.resources_url == ""
        assert rd.resources_file_id == 0

    def test_from_api_json(self) -> None:
        """从 API JSON 构建"""
        data = {
            "resourcesUid": 100,
            "resourcesName": "视频1",
            "resourcesType": 1,
            "resourcesDistributeType": 3,
            "resourcesUrl": "https://example.com/video.mp4",
            "resourcesFileId": 200,
        }
        rd = ResourceDetail.model_validate(data)
        assert rd.resources_uid == 100
        assert rd.resources_url == "https://example.com/video.mp4"
        assert rd.resources_file_id == 200


class TestResource:
    """资源模型"""

    def test_basic_construction(self) -> None:
        """基本构造"""
        detail = ResourceDetail(resources_uid=1, resources_name="test", resources_type=2, resources_distribute_type=1)
        r = Resource(resources_detail=detail)
        assert r.study_status == 0
        assert r.resources_detail.resources_uid == 1

    def test_completed_resource(self) -> None:
        """已完成资源"""
        detail = ResourceDetail(resources_uid=1, resources_name="test", resources_type=2, resources_distribute_type=1)
        r = Resource(study_status=1, resources_detail=detail)
        assert r.study_status == 1

    def test_from_api_json(self) -> None:
        """从 API JSON 构建"""
        data = {
            "studyStatus": 1,
            "resourcesDetail": {
                "resourcesUid": 100,
                "resourcesName": "PPT课件",
                "resourcesType": 1,
                "resourcesDistributeType": 4,
                "resourcesUrl": "https://example.com/ppt.pptx",
                "resourcesFileId": 300,
            },
        }
        r = Resource.model_validate(data)
        assert r.study_status == 1
        assert r.resources_detail.resources_name == "PPT课件"
        assert r.resources_detail.resources_distribute_type == 4


class TestExamInfo:
    """考试信息模型"""

    def test_basic_construction(self) -> None:
        """基本构造"""
        info = ExamInfo(exam_test_id=1, paper_id=2)
        assert info.exam_test_id == 1
        assert info.paper_id == 2
        assert info.mastery_score == 0

    def test_from_api_json(self) -> None:
        """从 API JSON 构建"""
        data = {"examTestId": 10, "paperId": 20, "masteryScore": 95}
        info = ExamInfo.model_validate(data)
        assert info.exam_test_id == 10
        assert info.mastery_score == 95


class TestQuestionSheet:
    """试卷题目模型"""

    def test_basic_construction(self) -> None:
        """基本构造"""
        qs = QuestionSheet(question_id=1)
        assert qs.question_id == 1
        assert qs.version == 1

    def test_from_api_json(self) -> None:
        """从 API JSON 构建"""
        data = {"questionId": 5, "version": 2}
        qs = QuestionSheet.model_validate(data)
        assert qs.question_id == 5
        assert qs.version == 2


class TestOptionVo:
    """选项模型"""

    def test_basic_construction(self) -> None:
        """基本构造"""
        opt = OptionVo(id=1)
        assert opt.id == 1
        assert opt.content == ""
        assert opt.is_correct == 0

    def test_from_api_json(self) -> None:
        """从 API JSON 构建"""
        data = {"id": 1, "content": "选项A", "isCorrect": 1}
        opt = OptionVo.model_validate(data)
        assert opt.id == 1
        assert opt.content == "选项A"
        assert opt.is_correct == 1


class TestQuestionContent:
    """题目内容模型"""

    def test_basic_construction(self) -> None:
        """基本构造"""
        qc = QuestionContent(id=1, content="1+1=?", question_type=1)
        assert qc.id == 1
        assert qc.content == "1+1=?"
        assert qc.question_type == 1
        assert qc.option_vos == []
        assert qc.version == 1

    def test_with_options(self) -> None:
        """包含选项"""
        opt = OptionVo(id=1, content="1")
        qc = QuestionContent(id=1, content="1+1=?", question_type=1, option_vos=[opt])
        assert len(qc.option_vos) == 1
        assert qc.option_vos[0].content == "1"

    def test_from_api_json(self) -> None:
        """从 API JSON 构建"""
        data = {
            "id": 10,
            "content": "Python是?",
            "questionType": 2,
            "optionVos": [
                {"id": 1, "content": "编程语言", "isCorrect": 0},
                {"id": 2, "content": "数据库", "isCorrect": 0},
            ],
            "version": 3,
        }
        qc = QuestionContent.model_validate(data)
        assert qc.id == 10
        assert qc.question_type == 2
        assert len(qc.option_vos) == 2
        assert qc.version == 3

    def test_from_api_json_with_null_fields(self) -> None:
        """API 返回的 null 字段应被正确处理（非 Optional 字段为 None 时使用默认值）"""
        data = {
            "analysisVo": None,
            "childQuestionVos": None,
            "codeQuestionDetailDto": None,
            "content": "关于大学体育课程的综合价值，下列哪项描述最为全面？",
            "dataFileVos": None,
            "examDesc": None,
            "examTitle": None,
            "id": 7234567890,
            "optionVos": [
                {"content": "仅有助于提高学生的身体素质", "id": 739512774, "isCorrect": None, "sort": 1},
                {"content": "主要培养学生的专业技能", "id": 739512775, "isCorrect": None, "sort": 2},
                {
                    "content": "有助于促进学生身心健康、思想道德建设和社会适应能力的提升",
                    "id": 739512776,
                    "isCorrect": None,
                    "sort": 3,
                },
                {"content": "只关注体育竞技成绩", "id": 739512777, "isCorrect": None, "sort": 4},
            ],
            "questionType": 1,
            "questionTypeName": "单选题",
            "readOverFileVos": None,
            "result": None,
            "studentRemarkList": None,
            "teacherRemarkList": None,
            "userAnswerVo": None,
        }
        qc = QuestionContent.model_validate(data)
        assert qc.id == 7234567890
        assert qc.question_type == 1
        assert len(qc.option_vos) == 4
        # isCorrect 为 None 时应回退为 0
        assert qc.option_vos[0].is_correct == 0
        # userAnswerVo 为 None 时应回退为空列表
        assert qc.user_answer_vos == []

    def test_fill_blank_question_with_null_option_content(self) -> None:
        """填空题 optionVos 的 content 为 None 时应回退为空字符串"""
        data = {
            "id": 7345678901,
            "content": "大学体育课程不仅提升学生体质健康，还能培养团队协作、____等社会能力。",
            "questionType": 3,
            "questionTypeName": "填空客观题（自动批阅）",
            "result": None,
            "childQuestionVos": None,
            "userAnswerVo": None,
            "analysisVo": None,
            "optionVos": [{"id": 739512113, "content": None, "isCorrect": None, "sort": 1}],
            "dataFileVos": None,
            "codeQuestionDetailDto": None,
            "examTitle": None,
            "examDesc": None,
            "readOverFileVos": None,
            "studentRemarkList": None,
            "teacherRemarkList": None,
        }
        qc = QuestionContent.model_validate(data)
        assert qc.question_type == 3
        assert len(qc.option_vos) == 1
        # content 为 None 时应回退为空字符串
        assert qc.option_vos[0].content == ""
        # isCorrect 为 None 时应回退为 0
        assert qc.option_vos[0].is_correct == 0


class TestAnswerCache:
    """答案缓存模型"""

    def test_basic_construction(self) -> None:
        """基本构造"""
        ac = AnswerCache()
        assert ac.version == 1
        assert ac.question == ""
        assert ac.answer == ""
        assert ac.answer_content == ""
        assert ac.question_dict == {}

    def test_with_data(self) -> None:
        """带数据构造"""
        ac = AnswerCache(
            version=2,
            question="1+1=?",
            answer="1#@#2",
            answer_content="选项A\n选项B",
            question_dict={"key": "value"},
        )
        assert ac.version == 2
        assert ac.answer == "1#@#2"
        assert ac.answer_content == "选项A\n选项B"

    def test_is_pydantic_model(self) -> None:
        """是 pydantic 模型"""
        assert issubclass(AnswerCache, BaseModel)
