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
from typing import Any

from pydantic import BaseModel, Field

from zhs.utils.path import get_config_path

# ============================================================
# 配置模型（按功能分组）
# ============================================================


class VideoConfig(BaseModel):
    """视频播放速度配置"""

    zhidao_speed: float = Field(default=1.5, description="知到视频播放速度（默认 1.5，最高 2.0）")
    hike_speed: float = Field(default=1.25, description="Hike 视频播放速度（默认 1.25，最高 2.0）")
    ai_speed: float = Field(default=1.5, description="AI 课程视频播放速度（默认 1.5，最高 2.0）")


class HomeworkConfig(BaseModel):
    """作业配置"""

    threshold: int = Field(default=100, description="作业达标阈值（0-100，默认 100）")
    max_submit: int = Field(default=0, description="最大重做次数（0 = 无限次）")
    delay_min: float = Field(default=1.0, alias="homework_delay_min", description="每题保存后最小休息时间（秒）")
    delay_max: float = Field(default=2.0, alias="homework_delay_max", description="每题保存后最大休息时间（秒）")
    page_size: int = Field(default=100, alias="homework_page_size", description="扫描作业列表分页大小")
    ai_homework_threshold: int = Field(default=90, description="AI 课程作业跳过阈值（masteryScore > 此值则跳过）")


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
    ai_chat: str = "https://ai-knowledge-map-platform.zhihuishu.com/knowledgemap/gateway/t/qa/platform/stream"
    exam: str = "https://studentexamtest.zhihuishu.com"
    homework: str = "https://studentexam-api.zhihuishu.com"
    ai_analysis: str = "https://ai-course-assistant-api.zhihuishu.com"
    newbase: str = "https://newbase.zhihuishu.com"


class AIConfig(BaseModel):
    """AI 配置"""

    enabled: bool = Field(default=True, description="是否启用 AI 功能")
    use_zhidao_ai: bool = Field(default=True, description="是否使用智慧树内置 AI")
    api_key: str = Field(default="", description="OpenAI 兼容 API Key")
    base_url: str = Field(default="https://api.openai.com/v1", description="API Base URL")
    model: str = Field(default="gpt-4o-mini", description="模型名称")
    max_token: int = Field(default=27900, description="最大 Token 数")


class ExamConfig(BaseModel):
    """AI 考试配置"""

    save_nums: int = Field(default=5, description="每批保存答案的题目数量")
    delay_min: float = Field(default=3.0, description="每批保存后最小休息时间（秒）")
    delay_max: float = Field(default=5.0, description="每批保存后最大休息时间（秒）")


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


# ============================================================
# 配置管理器
# ============================================================

# TOML 字段映射（用于兼容旧版扁平结构）
_FLAT_KEYS = (
    "save_cookies",
    "limit",
    "threshold",
    "zhidao_speed",
    "hike_speed",
    "ai_speed",
    "homework_threshold",
    "max_submit",
    "homework_delay_min",
    "homework_delay_max",
    "homework_page_size",
    "log_level",
    "image_path",
)

_MIGRATE_KEYS = (
    "save_cookies",
    "image_path",
)


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

        # 顶层字段直接映射（兼容旧版扁平结构）
        for key in _FLAT_KEYS:
            if key in data:
                result[key] = data[key]

        # [video] section
        if "video" in data:
            result["video"] = VideoConfig(**data["video"])

        # [homework] section
        if "homework" in data:
            hw = data["homework"]
            # 兼容旧版扁平字段名
            hw_kwargs: dict[str, Any] = {}
            if "threshold" in hw:
                hw_kwargs["threshold"] = hw["threshold"]
            if "max_submit" in hw:
                hw_kwargs["max_submit"] = hw["max_submit"]
            if "delay_min" in hw:
                hw_kwargs["delay_min"] = hw["delay_min"]
            if "delay_max" in hw:
                hw_kwargs["delay_max"] = hw["delay_max"]
            if "page_size" in hw:
                hw_kwargs["page_size"] = hw["page_size"]
            if "ai_homework_threshold" in hw:
                hw_kwargs["ai_homework_threshold"] = hw["ai_homework_threshold"]
            # 兼容旧版字段名（homework_delay_min 等）
            if "homework_delay_min" in hw:
                hw_kwargs["delay_min"] = hw["homework_delay_min"]
            if "homework_delay_max" in hw:
                hw_kwargs["delay_max"] = hw["homework_delay_max"]
            if "homework_page_size" in hw:
                hw_kwargs["page_size"] = hw["homework_page_size"]
            if "homework_threshold" in hw:
                hw_kwargs["threshold"] = hw["homework_threshold"]
            result["homework"] = HomeworkConfig(**hw_kwargs)

        # [display] section
        if "display" in data:
            result["display"] = DisplayConfig(**data["display"])

        # [proxies] section
        if "proxies" in data:
            result["proxies"] = ProxyConfig(**data["proxies"])

        # [qr] section（兼容 qr_extra）
        if "qr" in data:
            result["qr"] = QRConfig(**data["qr"])
        elif "qr_extra" in data:
            qr_extra = data["qr_extra"]
            if "image_path" in qr_extra:
                result["qr"] = QRConfig(image_path=qr_extra["image_path"])

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
        for section in ("video", "homework", "display", "proxies", "qr", "crypto", "urls", "ai", "exam"):
            if section in data:
                result[section] = ConfigManager._strip_none(data.pop(section))

        return result
