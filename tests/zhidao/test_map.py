"""新版知识图谱课程（aistudy / share-course-map）测试"""

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from zhs.config import AppConfig
from zhs.exceptions import ApiError
from zhs.session import ZhsSession
from zhs.zhidao.course import ZhidaoCourseManager
from zhs.zhidao.models import (
    CourseInfo,
    MapChapter,
    MapLesson,
    MapResource,
    ZhidaoContext,
    ZhidaoCourse,
)
from zhs.zhidao.video import ZhidaoVideoPlayer, _parse_learn_time

AISTUDY = "https://aistudy.zhihuishu.com"
SHARE_MAP = "https://share-course-map-service.zhihuishu.com"
STUDY = "https://studyservice-api.zhihuishu.com"

RAC = "ABC123_456"


@pytest.fixture
def mock_config() -> AppConfig:
    return AppConfig()


@pytest.fixture
def mock_session(mock_config: AppConfig) -> Iterator[ZhsSession]:
    with respx.mock:
        session = ZhsSession(mock_config)
        yield session


def _query_course_response(course_mode: int = 2) -> dict:
    """queryCourse 响应；courseMode=2 为新版图谱课，1 为旧版 videolist 课（抓包确认）"""
    return {
        "code": 0,
        "data": {
            "recruitId": 431490,
            "courseInfo": {"courseId": 1100000680, "name": "国家安全教育", "courseMode": course_mode},
        },
    }


def _tree_payload() -> list[dict]:
    return [
        {
            "id": None,
            "idHash": "0DzwkJWrOvidx3Ke",
            "idStr": "chapter-str",
            "name": "第一章",
            "orderNumber": 1,
            "lessons": [
                {
                    "idHash": "xQzqoBD7NlS8K9wD",
                    "idStr": "e721d3b2010d3a94e6a1ac0f66f59405",
                    "name": "已完成节点",
                    "sourceNum": 2,
                    "finishNum": 2,
                    "smallLessons": [],
                },
                {
                    "idHash": "n2Lp6Jz3GWfopO2r",
                    "idStr": "414f4bb4c059389e2fb3f7f216fc9982",
                    "name": "未完成节点",
                    "sourceNum": 2,
                    "finishNum": 0,
                    "smallLessons": [],
                },
            ],
        },
        {
            "idHash": "93jbB9r05pHGD5bW",
            "idStr": "chapter2-str",
            "name": "第二章",
            "orderNumber": 2,
            "lessons": [
                {
                    "idHash": "kzLNoE0xA7h8dKmo",
                    "idStr": "lesson2-str",
                    "name": "父节点",
                    "sourceNum": None,
                    "finishNum": None,
                    "smallLessons": [
                        {
                            "idHash": "DjnEJ9O0qKSEjDwp",
                            "idStr": "small-str",
                            "name": "子节点",
                            "sourceNum": 2,
                            "finishNum": 0,
                        }
                    ],
                }
            ],
        },
    ]


def _make_map_context() -> ZhidaoContext:
    lesson = MapLesson(
        idHash="xQzqoBD7NlS8K9wD",
        idStr="e721d3b2010d3a94e6a1ac0f66f59405",
        name="未完成节点",
        sourceNum=2,
        finishNum=0,
        chapterHash="0DzwkJWrOvidx3Ke",
    )
    chapter = MapChapter(
        idHash="0DzwkJWrOvidx3Ke",
        idStr="chapter-str",
        name="第一章",
        lessons=[lesson],
    )
    course = ZhidaoCourse(
        secret=RAC,
        course_name="国家安全教育",
        course_info=CourseInfo(courseId=1100000680, name="国家安全教育"),
        recruit_id=431490,
    )
    return ZhidaoContext(
        course=course,
        chapters=[],
        videos={},
        course_id=1100000680,
        mode="map",
        map_chapters=[chapter],
    )


class TestGetContextMap:
    def test_builds_map_context(self, mock_session: ZhsSession) -> None:
        respx.get(f"{STUDY}/login/gologin").mock(return_value=httpx.Response(200, text="<html>ok</html>"))
        respx.post(f"{STUDY}/gateway/t/v1/learning/queryCourse").mock(
            return_value=httpx.Response(200, json=_query_course_response())
        )
        respx.get(f"{AISTUDY}/gateway/t/v1/learning/queryCourseMapInfo").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "200",
                    "message": "success",
                    "data": {"coruseType": "2", "mapHashStr": "hash", "mapStr": "mapstr"},
                },
            )
        )
        respx.get(f"{AISTUDY}/gateway/t/v1/learning/kgCourseTreeInfoList").mock(
            return_value=httpx.Response(200, json={"code": "200", "message": "success", "data": _tree_payload()})
        )

        ctx = ZhidaoCourseManager(mock_session).get_context(RAC)

        assert ctx.mode == "map"
        assert ctx.course_id == 1100000680
        assert ctx.map_str == "mapstr"
        assert ctx.map_hash == "hash"
        assert len(ctx.map_chapters) == 2
        leaves = ctx.map_chapters[1].leaf_nodes()
        assert [leaf.id_hash for leaf in leaves] == ["DjnEJ9O0qKSEjDwp"]
        assert leaves[0].chapter_hash == "93jbB9r05pHGD5bW"

    def test_unparseable_tree_does_not_fall_back(self, mock_session: ZhsSession) -> None:
        """章节全部无法解析时直接报错，不回退旧 videolist"""
        respx.get(f"{STUDY}/login/gologin").mock(return_value=httpx.Response(200, text="<html>ok</html>"))
        respx.post(f"{STUDY}/gateway/t/v1/learning/queryCourse").mock(
            return_value=httpx.Response(200, json=_query_course_response())
        )
        respx.get(f"{AISTUDY}/gateway/t/v1/learning/queryCourseMapInfo").mock(
            return_value=httpx.Response(
                200,
                json={"code": "200", "data": {"mapHashStr": "hash", "mapStr": "mapstr"}},
            )
        )
        respx.get(f"{AISTUDY}/gateway/t/v1/learning/kgCourseTreeInfoList").mock(
            return_value=httpx.Response(200, json={"code": "200", "data": [{"not": "a chapter"}]})
        )
        videolist = respx.post(f"{STUDY}/gateway/t/v1/learning/videolist").mock(
            return_value=httpx.Response(200, json={"code": 0, "data": {"videoChapterDtos": []}})
        )

        with pytest.raises(ApiError, match="全部无法解析"):
            ZhidaoCourseManager(mock_session).get_context(RAC)

        assert not videolist.called

    def test_classic_course_ignores_map_info(self, mock_session: ZhsSession) -> None:
        """旧版课（courseMode=1）走 videolist，不调图谱接口

        抓包确认：旧版课 queryCourseMapInfo 同样返回 mapStr，而 kgCourseTreeInfoList 返回 500。
        若按 mapStr 判断版本，旧版课会被误判成图谱课，整门课无法播放。
        """
        respx.get(f"{STUDY}/login/gologin").mock(return_value=httpx.Response(200, text="<html>ok</html>"))
        respx.post(f"{STUDY}/gateway/t/v1/learning/queryCourse").mock(
            return_value=httpx.Response(200, json=_query_course_response(course_mode=1))
        )
        map_info = respx.get(f"{AISTUDY}/gateway/t/v1/learning/queryCourseMapInfo").mock(
            return_value=httpx.Response(
                200, json={"code": 200, "data": {"coruseType": None, "mapHashStr": "h", "mapStr": "s"}}
            )
        )
        tree = respx.get(f"{AISTUDY}/gateway/t/v1/learning/kgCourseTreeInfoList").mock(
            return_value=httpx.Response(200, json={"code": 500, "message": "章节结构查询出错"})
        )
        respx.post(f"{STUDY}/gateway/t/v1/learning/videolist").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "courseId": 1100000680,
                        "videoChapterDtos": [{"id": 1, "name": "第一章", "videoLessons": []}],
                    },
                },
            )
        )
        respx.post(f"{STUDY}/gateway/t/v1/learning/queryStuyInfo").mock(
            return_value=httpx.Response(200, json={"code": 0, "data": {"lv": {}, "lesson": {}}})
        )
        respx.post(f"{STUDY}/gateway/t/v1/learning/queryUserRecruitIdLastVideoId").mock(
            return_value=httpx.Response(200, json={"code": 0, "data": {}})
        )

        ctx = ZhidaoCourseManager(mock_session).get_context(RAC)

        assert ctx.mode == "classic"
        assert len(ctx.chapters) == 1
        assert not map_info.called
        assert not tree.called

    def test_map_course_without_map_str_raises(self, mock_session: ZhsSession) -> None:
        """图谱课（courseMode=2）拿不到 mapStr 时报错，不悄悄退回旧流程"""
        respx.get(f"{STUDY}/login/gologin").mock(return_value=httpx.Response(200, text="<html>ok</html>"))
        respx.post(f"{STUDY}/gateway/t/v1/learning/queryCourse").mock(
            return_value=httpx.Response(200, json=_query_course_response(course_mode=2))
        )
        respx.get(f"{AISTUDY}/gateway/t/v1/learning/queryCourseMapInfo").mock(
            return_value=httpx.Response(200, json={"code": "200", "data": {}})
        )
        videolist = respx.post(f"{STUDY}/gateway/t/v1/learning/videolist").mock(
            return_value=httpx.Response(200, json={"code": 0, "data": {"videoChapterDtos": []}})
        )

        with pytest.raises(ApiError, match="mapStr"):
            ZhidaoCourseManager(mock_session).get_context(RAC)

        assert not videolist.called


class TestMapResources:
    def test_parses_videos_and_ignores_files(self, mock_session: ZhsSession) -> None:
        respx.post(f"{SHARE_MAP}/gateway/t/node/queryNodeDescription").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 200,
                    "message": "请求成功",
                    "data": {
                        "nodeRespResourceVos": [
                            {
                                "idHash": "a",
                                "idStr": "b",
                                "resourcesFileId": "78780595",
                                "resourcesName": "导论第二节.mp4",
                                "resourcesSuffix": "mp4",
                                "resourcesTime": "297",
                            },
                            {
                                "idHash": "c",
                                "idStr": "d",
                                "resourcesFileId": "1277158241",
                                "resourcesName": "导论.pptx",
                                "resourcesSuffix": "pptx",
                                "resourcesTime": "",
                            },
                        ]
                    },
                },
            )
        )
        lesson = MapLesson(idHash="xQzqoBD7NlS8K9wD", idStr="e721d3b2010d3a94e6a1ac0f66f59405")

        resources = ZhidaoCourseManager(mock_session).query_node_resources(lesson)

        assert len(resources) == 2
        assert [r.is_video for r in resources] == [True, False]
        assert resources[0].file_id == "78780595"
        assert resources[0].duration == 297
        assert resources[0].is_elective is False

    def test_sync_type_zero_is_elective(self, mock_session: ZhsSession) -> None:
        """resourcesSyncType=0 是选学资源，上报会被 2025 拒绝"""
        respx.post(f"{SHARE_MAP}/gateway/t/node/queryNodeDescription").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": {
                        "nodeRespResourceVos": [
                            {
                                "resourcesFileId": "70587241",
                                "resourcesName": "我国国家安全形势总体概况（上）",
                                "resourcesTime": "450",
                                "resourcesSyncType": 0,
                            }
                        ]
                    },
                },
            )
        )
        lesson = MapLesson(idHash="x", idStr="y")

        resources = ZhidaoCourseManager(mock_session).query_node_resources(lesson)

        assert resources[0].is_video
        assert resources[0].is_elective


class TestSaveStudyProcess:
    def test_payload_shape(self, mock_session: ZhsSession) -> None:
        route = respx.post(f"{AISTUDY}/gateway/t/v1/learning/saveUserStudyProcess").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "message": "success", "data": {"state": 1, "submitSuccess": True}},
            )
        )

        data = ZhidaoCourseManager(mock_session).save_study_process(
            recruit_id=431490,
            chapter_hash="0DzwkJWrOvidx3Ke",
            lesson_hash="xQzqoBD7NlS8K9wD",
            data_id="78780595",
            play_times=6,
            total_time=297,
            learn_time=109,
        )

        assert data["submitSuccess"] is True
        body = route.calls[0].request.read().decode()
        import json

        payload = json.loads(body)
        assert payload["recruitId"] == 431490
        assert payload["chapterId"] == "0DzwkJWrOvidx3Ke"
        assert payload["lessonId"] == "xQzqoBD7NlS8K9wD"
        assert payload["lessonVideoId"] == ""
        assert payload["dataId"] == "78780595"
        assert payload["dataType"] == 1
        assert payload["sourceType"] == 1
        assert payload["playTimes"] == 6
        assert payload["studyTotalTime"] == "297"
        assert payload["learnTime"] == "00:01:49"


class TestPlayMapVideo:
    def test_sends_heartbeat_until_threshold(self) -> None:
        manager = MagicMock()
        manager.save_study_process.return_value = {"submitSuccess": True, "learnTime": 30}
        player = ZhidaoVideoPlayer(MagicMock(), speed=1.0, end_threshold=0.5)
        ctx = _make_map_context()
        lesson = ctx.map_chapters[0].leaf_nodes()[0]
        resource = MapResource(
            resourcesFileId="78780595",
            resourcesName="导论第二节.mp4",
            resourcesTime="60",
            resourcesSuffix="mp4",
        )

        with (
            patch("zhs.zhidao.video.time.sleep"),
            patch("zhs.zhidao.video.print"),
            patch("zhs.zhidao.video.random", return_value=0),
        ):
            assert player.play_map_video(manager, ctx, lesson, resource) is True

        manager.pre_learning_load.assert_called_once_with(
            course_id=1100000680,
            recruit_id=431490,
            chapter_hash="0DzwkJWrOvidx3Ke",
            lesson_hash="xQzqoBD7NlS8K9wD",
            data_id="78780595",
        )
        assert manager.save_study_process.call_count == 1
        kwargs = manager.save_study_process.call_args.kwargs
        # playTimes 是本次新增秒数（服务端据此累计 learnTime），不是自增计数
        assert kwargs["play_times"] == 30
        assert kwargs["learn_time"] == 30
        assert kwargs["total_time"] == 60
        assert kwargs["data_id"] == "78780595"
        assert kwargs["chapter_hash"] == "0DzwkJWrOvidx3Ke"

    def test_preload_failure_raises(self) -> None:
        manager = MagicMock()
        manager.pre_learning_load.return_value = False
        player = ZhidaoVideoPlayer(MagicMock(), speed=1.0, end_threshold=0.5)
        ctx = _make_map_context()
        lesson = ctx.map_chapters[0].leaf_nodes()[0]
        resource = MapResource(resourcesFileId="1", resourcesName="v.mp4", resourcesTime="60")

        with (
            patch("zhs.zhidao.video.time.sleep"),
            patch("zhs.zhidao.video.print"),
            pytest.raises(ApiError, match="preLearningLoad"),
        ):
            player.play_map_video(manager, ctx, lesson, resource)

    def test_skips_when_resume_reaches_threshold(self) -> None:
        manager = MagicMock()
        player = ZhidaoVideoPlayer(MagicMock(), end_threshold=0.5)
        ctx = _make_map_context()
        lesson = ctx.map_chapters[0].leaf_nodes()[0]
        resource = MapResource(resourcesFileId="1", resourcesName="v.mp4", resourcesTime="60")

        with patch("zhs.zhidao.video.print"):
            assert player.play_map_video(manager, ctx, lesson, resource, resume_seconds=40) is False

        manager.pre_learning_load.assert_not_called()
        manager.save_study_process.assert_not_called()

    def test_progress_updates_in_place(self) -> None:
        """进度行必须用 \\r 原地刷新，不能每次心跳新起一行"""
        player = ZhidaoVideoPlayer(MagicMock())

        with patch("zhs.zhidao.video.print") as mock_print:
            player._update_progress_line("playing 78780853 10.0%")

        args, kwargs = mock_print.call_args
        assert args[0].startswith("\r")
        assert kwargs.get("end") == ""
        assert player._progress_line == "playing 78780853 10.0%"

    def test_time_limit_stops_before_preload(self) -> None:
        """时间限制已到：不应再发 preLearningLoad（否则会连续打上百个请求）"""
        manager = MagicMock()
        player = ZhidaoVideoPlayer(MagicMock(), end_threshold=0.5, time_limit=10)
        ctx = _make_map_context()
        ctx.fucked_time = 10
        lesson = ctx.map_chapters[0].leaf_nodes()[0]
        resource = MapResource(resourcesFileId="1", resourcesName="v.mp4", resourcesTime="60")

        with patch("zhs.zhidao.video.print"):
            assert player.play_map_video(manager, ctx, lesson, resource) is False

        manager.pre_learning_load.assert_not_called()
        manager.save_study_process.assert_not_called()


class TestPlayMapCourse:
    def test_finish_num_does_not_skip_node(self) -> None:
        """节点 finishNum 不是完成依据；跳过只看 queryUserStudyInfo.state"""
        player = ZhidaoVideoPlayer(MagicMock())
        ctx = _make_map_context()
        ctx.map_chapters[0].lessons[0].finish_num = 2

        manager = MagicMock()
        manager.query_node_resources.return_value = [
            MapResource(resourcesFileId="1", resourcesName="v.mp4", resourcesTime="60")
        ]
        manager.query_user_study_info.return_value = {"state": 1, "learnTime": "00:00:00"}

        with (
            patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=manager),
            patch.object(player, "play_map_video", return_value=True) as mock_play,
            patch("zhs.zhidao.video.tree_print"),
            patch("zhs.zhidao.video.print"),
        ):
            player._play_map_course(ctx)

        mock_play.assert_called_once()
        manager.query_node_resources.assert_called_once()

    def test_skips_already_finished_by_study_info(self) -> None:
        """queryUserStudyInfo 返回 state=2 时直接跳过该视频"""
        player = ZhidaoVideoPlayer(MagicMock())
        ctx = _make_map_context()
        manager = MagicMock()
        manager.query_node_resources.return_value = [
            MapResource(resourcesFileId="1", resourcesName="v.mp4", resourcesTime="60")
        ]
        manager.query_user_study_info.return_value = {"state": 2, "learnTime": "00:00:59"}

        with (
            patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=manager),
            patch.object(player, "play_map_video") as mock_play,
            patch("zhs.zhidao.video.tree_print"),
            patch("zhs.zhidao.video.print"),
        ):
            player._play_map_course(ctx)

        mock_play.assert_not_called()

    def test_resumes_from_study_info_learn_time(self) -> None:
        """按节点的 learnTime 续播，而不是从 0 开始"""
        player = ZhidaoVideoPlayer(MagicMock())
        ctx = _make_map_context()
        manager = MagicMock()
        manager.query_node_resources.return_value = [
            MapResource(resourcesFileId="1", resourcesName="v.mp4", resourcesTime="60")
        ]
        manager.query_user_study_info.return_value = {"state": 1, "learnTime": "00:01:00"}

        with (
            patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=manager),
            patch.object(player, "play_map_video", return_value=True) as mock_play,
            patch("zhs.zhidao.video.tree_print"),
            patch("zhs.zhidao.video.print"),
        ):
            player._play_map_course(ctx)

        assert mock_play.call_args.args[4] == 60

    def test_aborts_course_on_multi_window(self) -> None:
        """2021 多窗口观看异常是账号级状态，继续播只会全失败，应立刻停课"""
        player = ZhidaoVideoPlayer(MagicMock())
        ctx = _make_map_context()

        manager = MagicMock()
        manager.query_last_knowledge.return_value = {}
        manager.query_node_resources.return_value = [
            MapResource(resourcesFileId="1", resourcesName="v.mp4", resourcesTime="60")
        ]

        with (
            patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=manager),
            patch.object(player, "play_map_video", side_effect=ApiError(2021, "多窗口观看异常")) as mock_play,
            patch("zhs.zhidao.video.tree_print") as mock_tree,
            patch("zhs.zhidao.video.print"),
        ):
            player._play_map_course(ctx)

        assert mock_play.call_count == 1
        texts = " ".join(str(call.args[0]) for call in mock_tree.call_args_list)
        assert "多窗口" in texts

    def test_skips_elective_video(self) -> None:
        """选学视频不计入进度，不能拿去上报（否则 2025）"""
        player = ZhidaoVideoPlayer(MagicMock())
        ctx = _make_map_context()
        manager = MagicMock()
        manager.query_node_resources.return_value = [
            MapResource(
                resourcesFileId="70587241",
                resourcesName="选学视频",
                resourcesTime="450",
                resourcesSyncType=0,
            ),
            MapResource(resourcesFileId="1", resourcesName="必修视频", resourcesTime="60", resourcesSyncType=1),
        ]
        manager.query_user_study_info.return_value = {"state": 1, "learnTime": "00:00:00"}

        with (
            patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=manager),
            patch.object(player, "play_map_video", return_value=True) as mock_play,
            patch("zhs.zhidao.video.tree_print"),
            patch("zhs.zhidao.video.print") as mock_print,
        ):
            player._play_map_course(ctx)

        assert mock_play.call_count == 1
        assert mock_play.call_args.args[3].file_id == "1"
        texts = " ".join(str(call.args[0]) for call in mock_print.call_args_list)
        assert "选学" in texts
        assert "章节 1:" in texts
        assert "课时 1.1:" in texts

    def test_study_info_error_does_not_replay(self) -> None:
        """学习记录查询失败时记失败，不从 0 重播"""
        player = ZhidaoVideoPlayer(MagicMock())
        ctx = _make_map_context()
        manager = MagicMock()
        manager.query_node_resources.return_value = [
            MapResource(resourcesFileId="1", resourcesName="v.mp4", resourcesTime="60")
        ]
        manager.query_user_study_info.side_effect = ApiError(2043, "参数异常")

        with (
            patch("zhs.zhidao.course.ZhidaoCourseManager", return_value=manager),
            patch.object(player, "play_map_video") as mock_play,
            patch("zhs.zhidao.video.tree_print") as mock_tree,
            patch("zhs.zhidao.video.print"),
        ):
            player._play_map_course(ctx)

        mock_play.assert_not_called()
        texts = " ".join(str(call.args[0]) for call in mock_tree.call_args_list)
        assert "视频失败" in texts


class TestQueryUserStudyInfo:
    def test_parses_state_and_learn_time(self, mock_session: ZhsSession) -> None:
        route = respx.get(f"{AISTUDY}/gateway/t/v1/learning/queryUserStudyInfo").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": "200",
                    "message": "success",
                    "data": {
                        "knowledgeHashId": "bGLed3kMyKsAR9jp",
                        "knowledgeStrId": "1ba37fc6",
                        "dataId": 78780619,
                        "state": 2,
                        "learnTime": "00:04:42",
                    },
                },
            )
        )

        data = ZhidaoCourseManager(mock_session).query_user_study_info(
            course_id=1100000680,
            recruit_id=431490,
            lesson_hash="bGLed3kMyKsAR9jp",
            data_id="78780619",
        )

        assert data["state"] == 2
        assert data["learnTime"] == "00:04:42"
        assert "secretStr" in route.calls[0].request.url.params

    def test_raises_on_error(self, mock_session: ZhsSession) -> None:
        """业务码拒绝不能当成没学过，否则播放循环会从 0 重播已完成视频"""
        respx.get(f"{AISTUDY}/gateway/t/v1/learning/queryUserStudyInfo").mock(
            return_value=httpx.Response(200, json={"code": 2043, "message": "recruitId不能为空"})
        )

        with pytest.raises(ApiError) as exc_info:
            ZhidaoCourseManager(mock_session).query_user_study_info(
                course_id=0,
                recruit_id=0,
                lesson_hash="x",
                data_id="y",
            )

        assert exc_info.value.code == 2043


class TestPreLearningLoad:
    def test_payload_and_ok(self, mock_session: ZhsSession) -> None:
        route = respx.get(f"{AISTUDY}/gateway/t/v1/learning/preLearningLoad").mock(
            return_value=httpx.Response(200, json={"code": "200", "message": "success", "data": True})
        )

        ok = ZhidaoCourseManager(mock_session).pre_learning_load(
            course_id=1100000680,
            recruit_id=431490,
            chapter_hash="0DzwkJWrOvidx3Ke",
            lesson_hash="xQzqoBD7NlS8K9wD",
            data_id="78780595",
        )

        assert ok is True
        params = route.calls[0].request.url.params
        assert "secretStr" in params
        assert "dateFormate" in params


class TestParseLearnTime:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [("00:01:49", 109), ("01:02:03", 3723), ("05:30", 330), ("", 0), ("bad", 0)],
    )
    def test_parse(self, value: str, expected: int) -> None:
        assert _parse_learn_time(value) == expected
