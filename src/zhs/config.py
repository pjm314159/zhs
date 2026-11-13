"""ZHS 配置管理模块

提供 pydantic 配置模型（按功能分组）和 ConfigManager（TOML 加载/保存/旧版 JSON 迁移）。

配置结构：
- AppConfig（顶层）
  - VideoConfig（视频播放速度）
  - HomeworkConfig（作业配置）
  - DisplayConfig（显示设置）
  - ProxyConfig（代理设置）
  - QRConfig（二维码设置）
  - AIConfig（AI 配置）
  - CryptoConfig（加密密钥）
  - UrlConfig（API URL）
"""

import json
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from zhs.utils.path import get_config_path

# ============================================================
# 配置模型（按功能分组）
# ============================================================

# 流式响应默认超时（秒）：AIConfig 与 OpenAIProvider 共用，避免两处硬编码
DEFAULT_STREAM_TIMEOUT = 120.0
DEFAULT_STREAM_IDLE_TIMEOUT = 30.0


class CoursePlanConfig(BaseModel):
    """单门知到课程的分天学习设置（配置里的 [video.zhidao_courses.<课程>]）

    课程键可以是 courseId、课程名或 recruitAndCourseId，三者任一匹配即生效。
    默认跟随课程自身的学习习惯分：有习惯分才分天学，没有就一次刷完。
    """

    plan: bool | None = Field(default=None, description="是否分天学；不填则跟随习惯分自动判断")
    daily_minutes: int | None = Field(default=None, ge=30, description="该课程每天的目标分钟数")


class VideoConfig(BaseModel):
    """视频播放速度配置"""

    zhidao_speed: float = Field(
        default=1.0, description="知到视频播放速度（默认 1.0，与网页一致；上报的学习时长 = 真实时长 × 倍速，最高 2.0）"
    )
    hike_speed: float = Field(default=1.25, description="Hike 视频播放速度（默认 1.25，最高 2.0）")
    ai_speed: float = Field(default=1.5, description="AI 课程视频播放速度（默认 1.5，最高 2.0）")
    ai_learn_optional: bool = Field(default=False, description="AI 课程是否学习选学资源（resourcesSyncType != 1）")
    ai_threshold: int = Field(default=90, description="AI 视频完成阈值（0-100，进度达到此百分比视为完成）")
    zhidao_plan: bool = Field(
        default=True,
        description="知到共享课按计划分天学：首日刷大部分，剩余平均分到之后每天（学习习惯分要求每天都学）",
    )
    zhidao_daily_minutes: int = Field(
        default=40, ge=30, description="分天学时之后每天的目标分钟数（至少 30，单日太短不被记为学过）"
    )
    # 按课程覆盖：键为 courseId / 课程名 / recruitAndCourseId
    zhidao_courses: dict[str, CoursePlanConfig] = Field(
        default_factory=dict, description="按课程覆盖分天设置；只有有习惯分的课默认才分天"
    )


class HomeworkConfig(BaseModel):
    """作业配置"""

    threshold: int = Field(default=100, description="作业达标阈值（0-100，默认 100）")
    max_submit: int = Field(default=0, description="最大重做次数（0 = 无限次）")
    delay_min: float = Field(default=1.0, alias="homework_delay_min", description="每题保存后最小休息时间（秒）")
    delay_max: float = Field(default=2.0, alias="homework_delay_max", description="每题保存后最大休息时间（秒）")
    page_size: int = Field(default=100, alias="homework_page_size", description="扫描作业列表分页大小")
    ai_homework_threshold: int = Field(default=90, description="AI 课程作业跳过阈值（masteryScore > 此值则跳过）")
    skip_ai_free_exam: bool = Field(default=True, description="AI 课程作业是否跳过免考知识点（freeExam=1）")
    
    # 知识图谱课章节测验配置（kg = Knowledge Graph）
    enable_kg_exam: bool = Field(default=True, description="是否启用知识图谱课章节测验（知识点掌握度）")
    kg_exam_threshold: int = Field(default=80, description="章节测验掌握度阈值（低于此值重做，0-100）")
    kg_exam_max_retries: int = Field(default=3, description="章节测验最大重试次数")

    # 字段名（delay_min）与旧版 alias（homework_delay_min）都可用于构造
    model_config = ConfigDict(populate_by_name=True)


class DisplayConfig(BaseModel):
    """显示设置"""

    log_level: str = Field(default="INFO", description="日志级别: DEBUG, INFO, WARNING, ERROR")


class ProxyConfig(BaseModel):
    """代理设置"""

    http: str = Field(default="", description="HTTP 代理地址")
    https: str = Field(default="", description="HTTPS 代理地址")

    def to_dict(self) -> dict[str, str]:
        """转换为 httpx proxies 格式（过滤空值）"""
        result: dict[str, str] = {}
        if self.http:
            result["http"] = self.http
        if self.https:
            result["https"] = self.https
        return result


class QRConfig(BaseModel):
    """二维码设置"""

    image_path: str = Field(default="", description="二维码图片保存路径（留空则使用临时目录）")


class CryptoConfig(BaseModel):
    """加解密密钥配置"""

    iv: str = "1g3qqdh4jvbskb9x"
    home_key: str = "7q9oko0vqb3la20r"
    video_key: str = "azp53h0kft7qi78q"
    qa_key: str = "kcGOlISPkYKRksSK"
    ai_key: str = "hw2fdlwcj4cs1mx7"
    exam_key: str = "onbfhdyvz8x7otrp"
    hike_salt: str = "o6xpt3b#Qy$Z"
    ev_key: str = "zzpttjd"
    ai_sign_prefix: str = "8ZflKEagfL"

    def key_bytes(self, name: str) -> bytes:
        """将密钥名转为 bytes，如 key_bytes('video_key') → b'azp53h0kft7qi78q'"""
        value: str = getattr(self, name)
        return value.encode("utf-8")


class UrlConfig(BaseModel):
    """API 基础 URL 配置"""

    base: str = "https://onlineservice-api.zhihuishu.com"
    passport: str = "https://passport.zhihuishu.com"
    study: str = "https://studyservice-api.zhihuishu.com"
    hike: str = "https://hike.zhihuishu.com"
    ai: str = "https://kg-ai-run.zhihuishu.com"
    ai_task: str = "https://kg-run-student.zhihuishu.com"
    exam: str = "https://studentexamtest.zhihuishu.com"
    homework: str = "https://studentexam-api.zhihuishu.com"
    taurusexam: str = "https://taurusexam-api.zhihuishu.com"
    ai_analysis: str = "https://ai-course-assistant-api.zhihuishu.com"
    newbase: str = "https://newbase.zhihuishu.com"
    # 新版共享课（知识图谱）接口域名
    aistudy: str = "https://aistudy.zhihuishu.com"
    share_map: str = "https://share-course-map-service.zhihuishu.com"


class AIConfig(BaseModel):
    """AI 配置"""

    enabled: bool = Field(default=True, description="是否启用 AI 功能")
    use_builtin_ai: bool = Field(
        default=True,
        description="AI 智慧课程是否使用智慧树内置 AI（false 则改用自定义 API Key）；"
        "知到作业/考试没有内置 AI，只能使用自定义 API Key",
    )
    api_key: str = Field(default="", description="OpenAI 兼容 API Key")
    base_url: str = Field(default="https://api.openai.com/v1", description="API Base URL")
    model: str = Field(default="gpt-4o-mini", description="模型名称")
    max_token: int = Field(default=27900, description="最大 Token 数")
    stream_timeout: float = Field(
        default=DEFAULT_STREAM_TIMEOUT,
        gt=0,
        description="OpenAI 兼容接口流式响应总时长上限（秒），不得小于 stream_idle_timeout",
    )
    stream_idle_timeout: float = Field(
        default=DEFAULT_STREAM_IDLE_TIMEOUT,
        gt=0,
        description="OpenAI 兼容接口相邻 chunk 空闲等待上限（秒），决定首包最长等待",
    )

    @model_validator(mode="after")
    def _check_timeout_order(self) -> "AIConfig":
        if self.stream_timeout < self.stream_idle_timeout:
            raise ValueError("stream_timeout 不能小于 stream_idle_timeout（总时长必须覆盖首包等待）")
        return self


class ExamConfig(BaseModel):
    """考试配置（知到考试 + AI 考试通用）"""

    save_nums: int = Field(default=5, description="每批保存答案的题目数量")
    delay_min: float = Field(default=3.0, description="每题保存后最小延迟（秒，缓存/随机答案用）")
    delay_max: float = Field(default=5.0, description="每题保存后最大延迟（秒，缓存/随机答案用）")


class QuestionBankConfig(BaseModel):
    """题库配置（外部题库查询，作为 LLM 答题的提示源）"""

    enabled: bool = Field(default=False, description="是否启用题库查询")
    token: str = Field(default="", description="题库 token（enncy.cn 个人中心-更多配置获取）")
    query_url: str = Field(default="https://tk.enncy.cn/query", description="题库查询 API URL")
    info_url: str = Field(default="https://tk.enncy.cn/info", description="题库信息 API URL")
    scopes: list[Literal["zhidao_homework", "zhidao_exam", "ai_homework", "ai_exam"]] = Field(
        default=["zhidao_exam", "ai_exam"], description="启用题库查询的范围"
    )


class AppConfig(BaseModel):
    """应用全局配置"""

    # 基础设置
    save_cookies: bool = Field(default=True, description="是否保存 Cookie")
    limit: int = Field(default=0, description="刷课时间限制（分钟，0 = 不限制）")
    threshold: float = Field(default=0.91, description="视频结束阈值（0.0-1.0）")

    # 功能配置（嵌套模型）
    video: VideoConfig = VideoConfig()
    homework: HomeworkConfig = HomeworkConfig()
    display: DisplayConfig = DisplayConfig()
    proxies: ProxyConfig = ProxyConfig()
    qr: QRConfig = QRConfig()
    crypto: CryptoConfig = CryptoConfig()
    urls: UrlConfig = UrlConfig()
    ai: AIConfig = AIConfig()
    exam: ExamConfig = ExamConfig()
    question_bank: QuestionBankConfig = QuestionBankConfig()


# ============================================================
# 配置管理器
# ============================================================

# 顶层直接字段
_TOP_KEYS = ("save_cookies", "limit", "threshold")

# 旧版扁平键 → (嵌套段, 字段名)；pydantic 不会自动把顶层键放进嵌套模型，需显式路由
_FLAT_KEY_ROUTES: dict[str, tuple[str, str]] = {
    "zhidao_speed": ("video", "zhidao_speed"),
    "hike_speed": ("video", "hike_speed"),
    "ai_speed": ("video", "ai_speed"),
    "homework_threshold": ("homework", "threshold"),
    "max_submit": ("homework", "max_submit"),
    "homework_delay_min": ("homework", "delay_min"),
    "homework_delay_max": ("homework", "delay_max"),
    "homework_page_size": ("homework", "page_size"),
    "log_level": ("display", "log_level"),
    "image_path": ("qr", "image_path"),
}

# [homework] 段内的旧版字段名 → 新字段名
_HOMEWORK_LEGACY_KEYS = {
    "homework_delay_min": "delay_min",
    "homework_delay_max": "delay_max",
    "homework_page_size": "page_size",
    "homework_threshold": "threshold",
}

_MIGRATE_KEYS = ("save_cookies",)


class ConfigManager:
    """配置管理器：加载/保存/迁移 TOML 配置"""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or get_config_path()

    def load(self) -> AppConfig:
        """从 TOML 文件加载配置，文件不存在或字段缺失时使用默认值"""
        if not self.config_path.exists():
            return AppConfig()
        with open(self.config_path, "rb") as f:
            data = tomllib.load(f)
        return AppConfig(**self._flatten_toml(data))

    def save(self, config: AppConfig) -> None:
        """将配置保存为 TOML 文件"""
        import tomli_w

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = self._unflatten_config(config.model_dump())
        with open(self.config_path, "wb") as f:
            tomli_w.dump(data, f)

    def migrate(self, json_path: Path) -> AppConfig:
        """从旧版 JSON 配置迁移到 AppConfig，并保存为 TOML"""
        with open(json_path, encoding="utf-8") as f:
            legacy: dict[str, Any] = json.load(f)

        kwargs: dict[str, Any] = {}

        # 基础字段迁移
        for key in _MIGRATE_KEYS:
            if key in legacy:
                kwargs[key] = legacy[key]

        # image_path → qr.image_path
        if "image_path" in legacy:
            kwargs["qr"] = QRConfig(image_path=legacy["image_path"])

        # logLevel → display.log_level
        if "logLevel" in legacy:
            kwargs["display"] = DisplayConfig(log_level=legacy["logLevel"])

        # 代理迁移
        if "proxies" in legacy:
            proxies_legacy = legacy["proxies"]
            proxy_kwargs: dict[str, Any] = {}
            if "http" in proxies_legacy:
                proxy_kwargs["http"] = proxies_legacy["http"]
            if "https" in proxies_legacy:
                proxy_kwargs["https"] = proxies_legacy["https"]
            kwargs["proxies"] = ProxyConfig(**proxy_kwargs)

        # AI 配置迁移
        if "ai" in legacy:
            ai_legacy = legacy["ai"]
            ai_kwargs: dict[str, Any] = {}
            if "openai" in ai_legacy:
                openai_legacy = ai_legacy["openai"]
                if "api_key" in openai_legacy:
                    ai_kwargs["api_key"] = openai_legacy["api_key"]
                if "api_base" in openai_legacy:
                    ai_kwargs["base_url"] = openai_legacy["api_base"]
                if "model_name" in openai_legacy:
                    ai_kwargs["model"] = openai_legacy["model_name"]
            kwargs["ai"] = AIConfig(**ai_kwargs)

        config = AppConfig(**kwargs)
        self.save(config)
        return config

    @staticmethod
    def _flatten_toml(data: dict[str, Any]) -> dict[str, Any]:
        """将 TOML 嵌套结构展平为 AppConfig 构造参数"""
        result: dict[str, Any] = {}

        # 顶层字段直接映射
        for key in _TOP_KEYS:
            if key in data:
                result[key] = data[key]

        # 旧版扁平键路由到嵌套段（段内显式写的值优先）
        sections: dict[str, dict[str, Any]] = {}
        for key, (section, field) in _FLAT_KEY_ROUTES.items():
            if key in data:
                sections.setdefault(section, {})[field] = data[key]
        for section in ("video", "homework", "display", "qr"):
            if isinstance(data.get(section), dict):
                sections.setdefault(section, {}).update(data[section])

        # [video] section
        if "video" in sections:
            result["video"] = VideoConfig(**sections["video"])

        # [homework] section：段内旧版字段名翻译为字段名，新字段名优先
        if "homework" in sections:
            hw = dict(sections["homework"])
            for old, new in _HOMEWORK_LEGACY_KEYS.items():
                if old in hw:
                    value = hw.pop(old)
                    hw.setdefault(new, value)
            result["homework"] = HomeworkConfig(**hw)

        # [display] section
        if "display" in sections:
            result["display"] = DisplayConfig(**sections["display"])

        # [proxies] section
        if "proxies" in data:
            result["proxies"] = ProxyConfig(**data["proxies"])

        # [qr] section（兼容 qr_extra）
        if "qr" not in data and "image_path" in data.get("qr_extra", {}):
            sections.setdefault("qr", {})["image_path"] = data["qr_extra"]["image_path"]
        if "qr" in sections:
            result["qr"] = QRConfig(**sections["qr"])

        # [crypto] section
        if "crypto" in data:
            result["crypto"] = CryptoConfig(**data["crypto"])

        # [urls] section
        if "urls" in data:
            result["urls"] = UrlConfig(**data["urls"])

        # [ai] section
        if "ai" in data:
            result["ai"] = AIConfig(**data["ai"])

        # [exam] section
        if "exam" in data:
            result["exam"] = ExamConfig(**data["exam"])

        # [question_bank] section
        if "question_bank" in data:
            result["question_bank"] = QuestionBankConfig(**data["question_bank"])

        return result

    @staticmethod
    def _strip_none(data: object) -> object:
        """递归移除 dict 中的 None 值，TOML 不支持 None"""
        if isinstance(data, dict):
            return {k: ConfigManager._strip_none(v) for k, v in data.items() if v is not None}
        if isinstance(data, list):
            return [ConfigManager._strip_none(v) for v in data]
        return data

    @staticmethod
    def _unflatten_config(data: dict[str, Any]) -> dict[str, Any]:
        """将 AppConfig.model_dump() 的扁平结构转为 TOML 嵌套结构"""
        data = dict(data)  # 浅拷贝，避免修改原 dict
        result: dict[str, Any] = {}

        # 基础设置
        if "save_cookies" in data:
            result["save_cookies"] = data.pop("save_cookies")
        if "limit" in data:
            result["limit"] = data.pop("limit")
        if "threshold" in data:
            result["threshold"] = data.pop("threshold")

        # 嵌套配置
        sections = (
            "video",
            "homework",
            "display",
            "proxies",
            "qr",
            "crypto",
            "urls",
            "ai",
            "exam",
            "question_bank",
        )
        for section in sections:
            if section in data:
                result[section] = ConfigManager._strip_none(data.pop(section))

        return result
