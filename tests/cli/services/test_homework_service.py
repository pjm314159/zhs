"""cli/services/homework_service.py 单元测试

覆盖 run_homework_from_url / run_zhidao_homework_by_course / run_zhidao_homework /
run_all_zhidao_homework / run_ai_homework / run_ai_homework_by_str / run_all_homework。
"""

from unittest.mock import MagicMock, patch

import pytest

from zhs.cli.services.homework_service import (
    run_ai_homework,
    run_ai_homework_by_str,
    run_all_homework,
    run_all_zhidao_homework,
    run_homework_from_url,
    run_zhidao_homework,
    run_zhidao_homework_by_course,
)


def _make_config() -> MagicMock:
    """创建 mock 配置"""
    config = MagicMock()
    config.homework.threshold = 100
    config.ai.enabled = True
    config.ai.use_zhidao_ai = True
    config.video.ai_speed = 1.5
    return config


class TestRunAiHomework:
    """run_ai_homework"""

    @patch("zhs.ai.course.AiCourseManager")
    def test_calls_run_course(self, mock_mgr_cls: MagicMock) -> None:
        """调用 AiCourseManager.run_course"""
        session = MagicMock()
        config = _make_config()
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr

        run_ai_homework(session, config, 100, 200)

        mock_mgr.run_course.assert_called_once()
        call_args = mock_mgr.run_course.call_args
        assert call_args[0][0] == 100
        assert call_args[0][1] == 200
        assert call_args[0][2] == config.ai
        assert call_args[0][3] == config.homework
        assert call_args.kwargs["speed"] == config.video.ai_speed


class TestRunAiHomeworkByStr:
    """run_ai_homework_by_str"""

    def test_valid_string_calls_run_ai_homework(self) -> None:
        """合法字符串调用 run_ai_homework"""
        session = MagicMock()
        config = _make_config()
        with patch("zhs.cli.services.homework_service.run_ai_homework") as mock_run:
            run_ai_homework_by_str(session, config, "100:200")
        mock_run.assert_called_once_with(session, config, 100, 200)

    def test_invalid_string_does_nothing(self) -> None:
        """非法字符串不调用 run_ai_homework"""
        session = MagicMock()
        config = _make_config()
        with patch("zhs.cli.services.homework_service.run_ai_homework") as mock_run:
            run_ai_homework_by_str(session, config, "invalid")
        mock_run.assert_not_called()


class TestRunZhidaoHomeworkByCourse:
    """run_zhidao_homework_by_course"""

    @patch("zhs.cli.services.homework_service.run_zhidao_homework")
    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_finds_recruit_id_and_runs(
        self,
        mock_mgr_cls: MagicMock,
        mock_run_zhidao: MagicMock,
    ) -> None:
        """找到 recruit_id 后调用 run_zhidao_homework

        注意：run_zhidao_homework_by_course 的 course_id 参数是字符串，
        内部用 int(course_id) if course_id.isdigit() else 0 转换。
        传入 "12345" → 12345；传入 "ABC123" → 0。
        """
        session = MagicMock()
        config = _make_config()
        mock_course = MagicMock()
        mock_course.secret = "12345"  # 必须与传入的 course_id 一致
        mock_course.recruit_id = 67890
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_course_list.return_value = [mock_course]

        run_zhidao_homework_by_course(session, config, "12345")

        mock_run_zhidao.assert_called_once()
        call_args = mock_run_zhidao.call_args
        # call_args[0] 是位置参数: (session, config, recruit_id, course_id, depth)
        assert call_args[0][2] == "67890"  # recruit_id 转为 str
        assert call_args[0][3] == 12345  # course_id 为 int("12345")

    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_no_recruit_id_prints_error(
        self,
        mock_mgr_cls: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """未找到 recruit_id 打印错误"""
        session = MagicMock()
        config = _make_config()
        mock_course = MagicMock()
        mock_course.secret = "OTHER"
        mock_course.recruit_id = None
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_course_list.return_value = [mock_course]

        run_zhidao_homework_by_course(session, config, "ABC123")
        captured = capsys.readouterr()
        assert "未找到课程" in captured.out
        assert "recruitId" in captured.out

    @patch("zhs.cli.services.homework_service.run_zhidao_homework")
    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_non_digit_course_id_passes_zero(
        self,
        mock_mgr_cls: MagicMock,
        mock_run_zhidao: MagicMock,
    ) -> None:
        """非数字 course_id 传 0"""
        session = MagicMock()
        config = _make_config()
        mock_course = MagicMock()
        mock_course.secret = "ABC123"
        mock_course.recruit_id = 12345
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_course_list.return_value = [mock_course]

        run_zhidao_homework_by_course(session, config, "ABC123")

        call_args = mock_run_zhidao.call_args
        assert call_args[0][3] == 0  # course_id=0 因为 "ABC123" 非 digit

    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_calls_exam_sso_login(self, mock_mgr_cls: MagicMock) -> None:
        """调用 session.exam_sso_login"""
        session = MagicMock()
        config = _make_config()
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_course_list.return_value = []

        run_zhidao_homework_by_course(session, config, "ABC123")

        session.exam_sso_login.assert_called_once()


class TestRunZhidaoHomework:
    """run_zhidao_homework"""

    @patch("zhs.cli.bootstrap.init_llm")
    @patch("zhs.zhidao.homework.worker.HomeworkWorker")
    @patch("zhs.cache.zhidao_cache.ZhidaoHomeworkCache")
    @patch("zhs.zhidao.homework.scanner.HomeworkScanner")
    def test_no_pending_prints_skip(
        self,
        mock_scanner_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_worker_cls: MagicMock,
        mock_init_llm: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """无待处理作业打印 skip"""
        session = MagicMock()
        config = _make_config()
        mock_scanner = MagicMock()
        mock_scanner_cls.return_value = mock_scanner
        mock_scanner.scan_homework.return_value = []
        mock_scanner.filter_pending.return_value = []

        run_zhidao_homework(session, config, "12345", 67890)

        captured = capsys.readouterr()
        assert "无待处理作业" in captured.out

    @patch("zhs.cli.bootstrap.init_llm")
    @patch("zhs.zhidao.homework.worker.HomeworkWorker")
    @patch("zhs.cache.zhidao_cache.ZhidaoHomeworkCache")
    @patch("zhs.zhidao.homework.scanner.HomeworkScanner")
    def test_pending_runs_worker(
        self,
        mock_scanner_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_worker_cls: MagicMock,
        mock_init_llm: MagicMock,
    ) -> None:
        """有待处理作业时调用 worker.run_homework"""
        session = MagicMock()
        config = _make_config()
        config.homework.threshold = 80

        mock_item = MagicMock()
        mock_item.exam_name = "测试作业"
        mock_item.state = 1
        mock_item.score = 0
        mock_scanner = MagicMock()
        mock_scanner_cls.return_value = mock_scanner
        mock_scanner.scan_homework.return_value = [mock_item]
        mock_scanner.filter_pending.return_value = [mock_item]

        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker
        mock_worker.run_homework.return_value = 90.0  # 达标

        run_zhidao_homework(session, config, "12345", 67890)

        mock_worker.run_homework.assert_called_once()

    @patch("zhs.cli.bootstrap.init_llm")
    @patch("zhs.zhidao.homework.worker.HomeworkWorker")
    @patch("zhs.cache.zhidao_cache.ZhidaoHomeworkCache")
    @patch("zhs.zhidao.homework.scanner.HomeworkScanner")
    def test_score_below_threshold_prints_warn(
        self,
        mock_scanner_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_worker_cls: MagicMock,
        mock_init_llm: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """分数低于阈值打印警告"""
        session = MagicMock()
        config = _make_config()
        config.homework.threshold = 80

        mock_item = MagicMock()
        mock_item.exam_name = "测试作业"
        mock_item.state = 1
        mock_item.score = 0
        mock_scanner = MagicMock()
        mock_scanner_cls.return_value = mock_scanner
        mock_scanner.scan_homework.return_value = [mock_item]
        mock_scanner.filter_pending.return_value = [mock_item]

        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker
        mock_worker.run_homework.return_value = 50.0  # 未达标

        run_zhidao_homework(session, config, "12345", 67890)

        captured = capsys.readouterr()
        assert "未达标" in captured.out

    @patch("zhs.cli.bootstrap.init_llm")
    @patch("zhs.zhidao.homework.worker.HomeworkWorker")
    @patch("zhs.cache.zhidao_cache.ZhidaoHomeworkCache")
    @patch("zhs.zhidao.homework.scanner.HomeworkScanner")
    def test_worker_exception_prints_error(
        self,
        mock_scanner_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_worker_cls: MagicMock,
        mock_init_llm: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """worker 异常打印错误"""
        session = MagicMock()
        config = _make_config()

        mock_item = MagicMock()
        mock_item.exam_name = "测试作业"
        mock_item.state = 1
        mock_item.score = 0
        mock_scanner = MagicMock()
        mock_scanner_cls.return_value = mock_scanner
        mock_scanner.scan_homework.return_value = [mock_item]
        mock_scanner.filter_pending.return_value = [mock_item]

        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker
        mock_worker.run_homework.side_effect = Exception("err")

        run_zhidao_homework(session, config, "12345", 67890)

        captured = capsys.readouterr()
        assert "失败" in captured.out


class TestRunAllZhidaoHomework:
    """run_all_zhidao_homework"""

    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_no_courses_prints_zero(
        self,
        mock_mgr_cls: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """无课程打印 0"""
        session = MagicMock()
        config = _make_config()
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_course_list.return_value = []

        run_all_zhidao_homework(session, config)

        captured = capsys.readouterr()
        assert "发现 0 门课程" in captured.out

    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_course_without_recruit_id_skipped(
        self,
        mock_mgr_cls: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """无 recruit_id 的课程跳过"""
        session = MagicMock()
        config = _make_config()
        mock_course = MagicMock()
        mock_course.recruit_id = None
        mock_course.course_name = "测试课程"
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_course_list.return_value = [mock_course]

        run_all_zhidao_homework(session, config)

        captured = capsys.readouterr()
        assert "跳过" in captured.out

    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_course_without_course_id_skipped(
        self,
        mock_mgr_cls: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """无 course_id 的课程跳过"""
        session = MagicMock()
        config = _make_config()
        mock_course = MagicMock()
        mock_course.recruit_id = 12345
        mock_course.course_id = 0
        mock_course.course_info = None
        mock_course.course_name = "测试课程"
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_course_list.return_value = [mock_course]

        run_all_zhidao_homework(session, config)

        captured = capsys.readouterr()
        assert "跳过" in captured.out

    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_course_exception_continues(
        self,
        mock_mgr_cls: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """单个课程异常不中断"""
        session = MagicMock()
        config = _make_config()
        mock_course = MagicMock()
        mock_course.recruit_id = 12345
        mock_course.course_id = 67890
        mock_course.course_name = "测试课程"
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_course_list.return_value = [mock_course]
        # 让 run_zhidao_homework 抛异常
        with patch("zhs.cli.services.homework_service.run_zhidao_homework", side_effect=Exception("err")):
            run_all_zhidao_homework(session, config)

        captured = capsys.readouterr()
        assert "课程失败" in captured.out

    @patch("zhs.zhidao.course.ZhidaoCourseManager")
    def test_calls_exam_sso_login(self, mock_mgr_cls: MagicMock) -> None:
        """调用 session.exam_sso_login"""
        session = MagicMock()
        config = _make_config()
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.get_course_list.return_value = []

        run_all_zhidao_homework(session, config)

        session.exam_sso_login.assert_called_once()


class TestRunAllHomework:
    """run_all_homework"""

    @patch("zhs.ai.course.AiCourseManager")
    @patch("zhs.cli.services.homework_service.run_all_zhidao_homework")
    def test_default_runs_zhidao_and_ai(
        self,
        mock_run_zhidao: MagicMock,
        mock_ai_cls: MagicMock,
    ) -> None:
        """默认（None）运行 zhidao + ai"""
        session = MagicMock()
        config = _make_config()
        mock_ai_cls.return_value.get_ai_course_list.return_value = []

        run_all_homework(session, config, None)

        mock_run_zhidao.assert_called_once()
        mock_ai_cls.return_value.get_ai_course_list.assert_called_once()

    @patch("zhs.ai.course.AiCourseManager")
    @patch("zhs.cli.services.homework_service.run_all_zhidao_homework")
    def test_type_zhidao_only_runs_zhidao(
        self,
        mock_run_zhidao: MagicMock,
        mock_ai_cls: MagicMock,
    ) -> None:
        """--type zhidao 只运行 zhidao"""
        session = MagicMock()
        config = _make_config()

        run_all_homework(session, config, "zhidao")

        mock_run_zhidao.assert_called_once()
        mock_ai_cls.assert_not_called()

    @patch("zhs.ai.course.AiCourseManager")
    @patch("zhs.cli.services.homework_service.run_all_zhidao_homework")
    def test_type_ai_only_runs_ai(
        self,
        mock_run_zhidao: MagicMock,
        mock_ai_cls: MagicMock,
    ) -> None:
        """--type ai 只运行 ai"""
        session = MagicMock()
        config = _make_config()
        mock_ai_cls.return_value.get_ai_course_list.return_value = []

        run_all_homework(session, config, "ai")

        mock_ai_cls.return_value.get_ai_course_list.assert_called_once()
        mock_run_zhidao.assert_not_called()

    @patch("zhs.ai.course.AiCourseManager")
    @patch("zhs.cli.services.homework_service.run_all_zhidao_homework")
    def test_type_auto_runs_both(
        self,
        mock_run_zhidao: MagicMock,
        mock_ai_cls: MagicMock,
    ) -> None:
        """--type auto 运行 zhidao + ai"""
        session = MagicMock()
        config = _make_config()
        mock_ai_cls.return_value.get_ai_course_list.return_value = []

        run_all_homework(session, config, "auto")

        mock_run_zhidao.assert_called_once()
        mock_ai_cls.return_value.get_ai_course_list.assert_called_once()

    @patch("zhs.ai.course.AiCourseManager")
    @patch("zhs.cli.services.homework_service.run_all_zhidao_homework")
    def test_zhidao_exception_continues_to_ai(
        self,
        mock_run_zhidao: MagicMock,
        mock_ai_cls: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """知到作业异常不中断 AI 作业"""
        session = MagicMock()
        config = _make_config()
        mock_run_zhidao.side_effect = Exception("err")
        mock_ai_cls.return_value.get_ai_course_list.return_value = []

        run_all_homework(session, config, None)

        captured = capsys.readouterr()
        assert "知到课程作业处理失败" in captured.out
        mock_ai_cls.return_value.get_ai_course_list.assert_called_once()

    @patch("zhs.ai.course.AiCourseManager")
    @patch("zhs.cli.services.homework_service.run_all_zhidao_homework")
    def test_ai_list_exception_handled(
        self,
        mock_run_zhidao: MagicMock,
        mock_ai_cls: MagicMock,
    ) -> None:
        """AI 课程列表获取异常被捕获"""
        session = MagicMock()
        config = _make_config()
        mock_ai_cls.return_value.get_ai_course_list.side_effect = Exception("err")

        # 不应抛异常
        run_all_homework(session, config, None)

    @patch("zhs.ai.course.AiCourseManager")
    @patch("zhs.cli.services.homework_service.run_all_zhidao_homework")
    def test_ai_course_missing_ids_logged(
        self,
        mock_run_zhidao: MagicMock,
        mock_ai_cls: MagicMock,
    ) -> None:
        """AI 课程缺少 courseId 或 classId 记录日志"""
        session = MagicMock()
        config = _make_config()
        mock_ai_cls.return_value.get_ai_course_list.return_value = [
            {"courseName": "测试课程"}  # 缺少 courseId 和 classId
        ]

        run_all_homework(session, config, "ai")
        # 不应调用 run_course
        mock_ai_cls.return_value.run_course.assert_not_called()


class TestRunHomeworkFromUrl:
    """run_homework_from_url"""

    @patch("zhs.cli.bootstrap.init_llm")
    @patch("zhs.zhidao.homework.worker.HomeworkWorker")
    @patch("zhs.cache.zhidao_cache.ZhidaoHomeworkCache")
    @patch("zhs.zhidao.homework.scanner.HomeworkScanner")
    def test_url_with_matching_exam(
        self,
        mock_scanner_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_worker_cls: MagicMock,
        mock_init_llm: MagicMock,
    ) -> None:
        """URL 指定的作业在扫描列表中"""
        session = MagicMock()
        config = _make_config()
        config.homework.threshold = 80

        mock_item = MagicMock()
        mock_item.exam_id = "EXAM1"
        mock_item.exam_name = "测试作业"
        mock_item.state = 1
        mock_item.score = 0
        mock_item.back_num = 0
        mock_item.is_marking = False
        mock_scanner = MagicMock()
        mock_scanner_cls.return_value = mock_scanner
        mock_scanner.scan_homework.return_value = [mock_item]

        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker
        mock_worker.run_homework.return_value = 90.0

        url = "https://example.com/dohomework/R1/STU1/EXAM1/12345/S1/0"
        run_homework_from_url(session, config, url)

        session.exam_sso_login.assert_called_once()
        mock_worker.run_homework.assert_called_once()

    @patch("zhs.cli.bootstrap.init_llm")
    @patch("zhs.zhidao.homework.worker.HomeworkWorker")
    @patch("zhs.cache.zhidao_cache.ZhidaoHomeworkCache")
    @patch("zhs.zhidao.homework.scanner.HomeworkScanner")
    def test_url_with_no_matching_exam_constructs_item(
        self,
        mock_scanner_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_worker_cls: MagicMock,
        mock_init_llm: MagicMock,
    ) -> None:
        """URL 指定的作业不在扫描列表中，构造 HomeworkItem"""
        session = MagicMock()
        config = _make_config()
        config.homework.threshold = 80

        mock_scanner = MagicMock()
        mock_scanner_cls.return_value = mock_scanner
        mock_scanner.scan_homework.return_value = []  # 空列表

        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker
        mock_worker.run_homework.return_value = 90.0

        url = "https://example.com/dohomework/R1/STU1/EXAM1/12345/S1/0"
        run_homework_from_url(session, config, url)

        mock_worker.run_homework.assert_called_once()
        # 验证构造的 HomeworkItem
        call_args = mock_worker.run_homework.call_args
        item = call_args[0][0]
        assert item.exam_id == "EXAM1"
        assert item.id == "STU1"

    @patch("zhs.cli.bootstrap.init_llm")
    @patch("zhs.zhidao.homework.worker.HomeworkWorker")
    @patch("zhs.cache.zhidao_cache.ZhidaoHomeworkCache")
    @patch("zhs.zhidao.homework.scanner.HomeworkScanner")
    def test_score_below_threshold_prints_warn(
        self,
        mock_scanner_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_worker_cls: MagicMock,
        mock_init_llm: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """分数低于阈值打印警告"""
        session = MagicMock()
        config = _make_config()
        config.homework.threshold = 80

        mock_item = MagicMock()
        mock_item.exam_id = "EXAM1"
        mock_item.exam_name = "测试作业"
        mock_item.state = 1
        mock_item.score = 0
        mock_item.back_num = 0
        mock_item.is_marking = False
        mock_scanner = MagicMock()
        mock_scanner_cls.return_value = mock_scanner
        mock_scanner.scan_homework.return_value = [mock_item]

        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker
        mock_worker.run_homework.return_value = 50.0

        url = "https://example.com/dohomework/R1/STU1/EXAM1/12345/S1/0"
        run_homework_from_url(session, config, url)

        captured = capsys.readouterr()
        assert "未达标" in captured.out

    @patch("zhs.cli.bootstrap.init_llm")
    @patch("zhs.zhidao.homework.worker.HomeworkWorker")
    @patch("zhs.cache.zhidao_cache.ZhidaoHomeworkCache")
    @patch("zhs.zhidao.homework.scanner.HomeworkScanner")
    def test_score_above_threshold_prints_done(
        self,
        mock_scanner_cls: MagicMock,
        mock_cache_cls: MagicMock,
        mock_worker_cls: MagicMock,
        mock_init_llm: MagicMock,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """分数达标打印完成"""
        session = MagicMock()
        config = _make_config()
        config.homework.threshold = 80

        mock_item = MagicMock()
        mock_item.exam_id = "EXAM1"
        mock_item.exam_name = "测试作业"
        mock_item.state = 1
        mock_item.score = 0
        mock_item.back_num = 0
        mock_item.is_marking = False
        mock_scanner = MagicMock()
        mock_scanner_cls.return_value = mock_scanner
        mock_scanner.scan_homework.return_value = [mock_item]

        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker
        mock_worker.run_homework.return_value = 90.0

        url = "https://example.com/dohomework/R1/STU1/EXAM1/12345/S1/0"
        run_homework_from_url(session, config, url)

        captured = capsys.readouterr()
        assert "达标" in captured.out
