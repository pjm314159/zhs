"""ZHS 配置管理模块

提供 pydantic 配置模型（CryptoConfig、UrlConfig、AIConfig、AppConfig）
和 ConfigManager（TOML 加载/保存/旧版 JSON 迁移）。
"""

import json
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from zhs.utils.path import get_config_path

_AUTH_KEYS = ("save_cookies", "proxies")
_TOP_KEYS = (
    "save_cookies",
    "speed",
    "proxies",
    "log_level",
    "tree_view",
    "progressbar_view",
    "qr_extra",
    "image_path",
    "limit",
    "threshold",
    "homework_threshold",
    "max_submit",
)
_DISPLAY_KEYS = (
    "speed",
    "log_level",
    "tree_view",
    "progressbar_view",
    "qr_extra",
    "image_path",
    "limit",
    "threshold",
    "homework_threshold",
    "max_submit",
)
_MIGRATE_KEYS = (
    "save_cookies",
    "proxies",
    "tree_view",
    "progressbar_view",
    "image_path",
)


class CryptoConfig(BaseModel):
    """加解密密钥配置（可覆盖，默认值与旧版一致）"""

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
    """API 基础 URL 配置（可覆盖，便于部署私有镜像或 API 变更）"""

    base: str = "https://onlineservice-api.zhihuishu.com"
    passport: str = "https://passport.zhihuishu.com"
    study: str = "https://studyservice-api.zhihuishu.com"
    hike: str = "https://hike.zhihuishu.com"
    ai: str = "https://kg-ai-run.zhihuishu.com"
    ai_chat: str = "https://ai-knowledge-map-platform.zhihuishu.com/knowledgemap/gateway/t/qa/platform/stream"
    exam: str = "https://studentexamtest.zhihuishu.com"
    homework: str = "https://studentexam-api.zhihuishu.com"
    ai_analysis: str = "https://ai-course-assistant-api.zhihuishu.com"
    newbase: str = "https://newbase.zhihuishu.com"


class AIConfig(BaseModel):
    """AI 配置"""

    enabled: bool = True
    use_zhidao_ai: bool = True
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    moonshot_api_key: str = ""
    max_token: int = 27900


class AppConfig(BaseModel):
    """应用全局配置"""

    save_cookies: bool = True
    zhidao_speed: float = 1.5
    hike_speed: float = 1.25
    ai_speed: float = 1.5
    proxies: dict[str, str] = {}
    log_level: str = "INFO"
    tree_view: bool = True
    progressbar_view: bool = True
    qr_extra: dict[str, Any] = {}
    image_path: str = ""  # 默认在运行时设为 .zhs/qrcode.png
    limit: int = 0
    threshold: float = 0.91
    homework_threshold: int = 100
    max_submit: int = 3
    crypto: CryptoConfig = CryptoConfig()
    urls: UrlConfig = UrlConfig()
    ai: AIConfig = AIConfig()


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

        # 映射旧字段到新字段
        kwargs: dict[str, Any] = {}
        for key in _MIGRATE_KEYS:
            if key in legacy:
                kwargs[key] = legacy[key]

        # logLevel → log_level
        if "logLevel" in legacy:
            kwargs["log_level"] = legacy["logLevel"]

        # qr_extra
        if "qr_extra" in legacy:
            kwargs["qr_extra"] = legacy["qr_extra"]

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
            if "ppt_processing" in ai_legacy:
                ppt = ai_legacy["ppt_processing"]
                if "moonShot" in ppt:
                    moonshot = ppt["moonShot"]
                    if "api_key" in moonshot:
                        ai_kwargs["moonshot_api_key"] = moonshot["api_key"]
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

        # [auth] section
        if "auth" in data:
            auth = data["auth"]
            for key in _AUTH_KEYS:
                if key in auth:
                    result[key] = auth[key]

        # [crypto] section
        if "crypto" in data:
            result["crypto"] = CryptoConfig(**data["crypto"])

        # [urls] section
        if "urls" in data:
            result["urls"] = UrlConfig(**data["urls"])

        # [ai] section
        if "ai" in data:
            result["ai"] = AIConfig(**data["ai"])

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
        auth: dict[str, Any] = {}
        for key in _AUTH_KEYS:
            if key in data:
                auth[key] = data.pop(key)
        if auth:
            result["auth"] = auth

        for key in _DISPLAY_KEYS:
            if key in data:
                val = data.pop(key)
                result[key] = ConfigManager._strip_none(val)

        if "crypto" in data:
            result["crypto"] = data.pop("crypto")
        if "urls" in data:
            result["urls"] = data.pop("urls")
        if "ai" in data:
            result["ai"] = data.pop("ai")

        return result
