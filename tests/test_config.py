"""Task 1.6 — config.py 测试"""

import json
from pathlib import Path

import pytest

from zhs.config import AIConfig, AppConfig, ConfigManager, CryptoConfig, UrlConfig

# ---------------------------------------------------------------------------
# CryptoConfig
# ---------------------------------------------------------------------------


class TestCryptoConfig:
    def test_default_values(self) -> None:
        c = CryptoConfig()
        assert c.iv == "1g3qqdh4jvbskb9x"
        assert c.video_key == "azp53h0kft7qi78q"
        assert c.home_key == "7q9oko0vqb3la20r"
        assert c.qa_key == "kcGOlISPkYKRksSK"
        assert c.exam_key == "onbfhdyvz8x7otrp"
        assert c.ai_key == "hw2fdlwcj4cs1mx7"
        assert c.hike_salt == "o6xpt3b#Qy$Z"
        assert c.ev_key == "zzpttjd"
        assert c.ai_sign_prefix == "8ZflKEagfL"

    def test_key_bytes_video_key(self) -> None:
        c = CryptoConfig()
        assert c.key_bytes("video_key") == b"azp53h0kft7qi78q"

    def test_key_bytes_iv(self) -> None:
        c = CryptoConfig()
        assert c.key_bytes("iv") == b"1g3qqdh4jvbskb9x"

    def test_key_bytes_home_key(self) -> None:
        c = CryptoConfig()
        assert c.key_bytes("home_key") == b"7q9oko0vqb3la20r"

    def test_key_bytes_invalid_field(self) -> None:
        c = CryptoConfig()
        with pytest.raises(AttributeError):
            c.key_bytes("nonexistent_key")

    def test_custom_values(self) -> None:
        c = CryptoConfig(iv="customiv12345678", video_key="customkey1234567")
        assert c.iv == "customiv12345678"
        assert c.video_key == "customkey1234567"
        assert c.key_bytes("iv") == b"customiv12345678"


# ---------------------------------------------------------------------------
# UrlConfig
# ---------------------------------------------------------------------------


class TestUrlConfig:
    def test_default_values(self) -> None:
        u = UrlConfig()
        assert u.base == "https://onlineservice-api.zhihuishu.com"
        assert u.passport == "https://passport.zhihuishu.com"
        assert u.study == "https://studyservice-api.zhihuishu.com"
        assert u.hike == "https://hike.zhihuishu.com"
        assert u.ai == "https://kg-ai-run.zhihuishu.com"

    def test_custom_values(self) -> None:
        u = UrlConfig(base="http://localhost:8080")
        assert u.base == "http://localhost:8080"
        assert u.passport == "https://passport.zhihuishu.com"  # 默认值不变


# ---------------------------------------------------------------------------
# AIConfig
# ---------------------------------------------------------------------------


class TestAIConfig:
    def test_default_values(self) -> None:
        ai = AIConfig()
        assert ai.api_key == ""
        assert ai.base_url == "https://api.openai.com/v1"
        assert ai.model == "gpt-4o-mini"
        assert ai.max_token == 27900

    def test_custom_values(self) -> None:
        ai = AIConfig(api_key="sk-test", model="deepseek-v4-pro")
        assert ai.api_key == "sk-test"
        assert ai.model == "deepseek-v4-pro"


# ---------------------------------------------------------------------------
# AppConfig
# ---------------------------------------------------------------------------


class TestAppConfig:
    def test_defaults(self) -> None:
        cfg = AppConfig()
        assert cfg.save_cookies is True
        assert cfg.video.zhidao_speed == 1.5
        assert cfg.video.hike_speed == 1.25
        assert cfg.display.log_level == "INFO"
        assert cfg.proxies.to_dict() == {}
        assert isinstance(cfg.crypto, CryptoConfig)
        assert isinstance(cfg.urls, UrlConfig)
        assert isinstance(cfg.ai, AIConfig)

    def test_custom_values(self) -> None:
        cfg = AppConfig(save_cookies=False)
        cfg.display.log_level = "DEBUG"
        assert cfg.save_cookies is False
        assert cfg.display.log_level == "DEBUG"

    def test_nested_crypto_override(self) -> None:
        cfg = AppConfig(crypto=CryptoConfig(iv="customiv12345678"))
        assert cfg.crypto.iv == "customiv12345678"
        assert cfg.crypto.video_key == "azp53h0kft7qi78q"  # 默认值不变

    def test_nested_urls_override(self) -> None:
        cfg = AppConfig(urls=UrlConfig(base="http://localhost:8080"))
        assert cfg.urls.base == "http://localhost:8080"

    def test_nested_ai_override(self) -> None:
        cfg = AppConfig(ai=AIConfig(api_key="sk-test", model="gpt-4"))
        assert cfg.ai.api_key == "sk-test"
        assert cfg.ai.model == "gpt-4"


# ---------------------------------------------------------------------------
# ConfigManager — TOML 加载
# ---------------------------------------------------------------------------


class TestConfigManagerLoad:
    def test_load_toml(self, tmp_path: Path) -> None:
        """从 TOML 文件加载配置"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
save_cookies = false
"""
        )
        mgr = ConfigManager(config_file)
        cfg = mgr.load()
        assert cfg.save_cookies is False

    def test_load_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        """配置文件不存在时返回默认值"""
        config_file = tmp_path / "nonexistent.toml"
        mgr = ConfigManager(config_file)
        cfg = mgr.load()
        assert cfg.save_cookies is True
        assert isinstance(cfg.crypto, CryptoConfig)

    def test_load_missing_fields_use_defaults(self, tmp_path: Path) -> None:
        """缺失字段使用默认值"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
speed = 1.5
"""
        )
        mgr = ConfigManager(config_file)
        cfg = mgr.load()
        assert cfg.video.zhidao_speed == 1.5
        assert cfg.video.hike_speed == 1.25
        assert cfg.save_cookies is True  # 默认值

    def test_load_crypto_section(self, tmp_path: Path) -> None:
        """加载 crypto 子配置"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[crypto]
iv = "customiv12345678"
video_key = "customkey1234567"
"""
        )
        mgr = ConfigManager(config_file)
        cfg = mgr.load()
        assert cfg.crypto.iv == "customiv12345678"
        assert cfg.crypto.video_key == "customkey1234567"
        assert cfg.crypto.home_key == "7q9oko0vqb3la20r"  # 默认值

    def test_load_urls_section(self, tmp_path: Path) -> None:
        """加载 urls 子配置"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[urls]
base = "http://localhost:8080"
"""
        )
        mgr = ConfigManager(config_file)
        cfg = mgr.load()
        assert cfg.urls.base == "http://localhost:8080"

    def test_load_ai_section(self, tmp_path: Path) -> None:
        """加载 ai 子配置"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[ai]
api_key = "sk-test"
model = "deepseek-v4-pro"
max_token = 16000
"""
        )
        mgr = ConfigManager(config_file)
        cfg = mgr.load()
        assert cfg.ai.api_key == "sk-test"
        assert cfg.ai.model == "deepseek-v4-pro"
        assert cfg.ai.max_token == 16000

    def test_load_proxies(self, tmp_path: Path) -> None:
        """加载代理配置"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[proxies]
http = "http://127.0.0.1:8080"
"""
        )
        mgr = ConfigManager(config_file)
        cfg = mgr.load()
        assert cfg.proxies.to_dict() == {"http": "http://127.0.0.1:8080"}


# ---------------------------------------------------------------------------
# ConfigManager — TOML 保存
# ---------------------------------------------------------------------------


class TestConfigManagerSave:
    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        """保存后重新加载一致"""
        config_file = tmp_path / "config.toml"
        cfg = AppConfig(save_cookies=False)
        cfg.video.zhidao_speed = 1.5
        mgr = ConfigManager(config_file)
        mgr.save(cfg)
        loaded = mgr.load()
        assert loaded.save_cookies is False
        assert loaded.video.zhidao_speed == 1.5

    def test_save_creates_file(self, tmp_path: Path) -> None:
        """保存时创建文件"""
        config_file = tmp_path / "config.toml"
        cfg = AppConfig()
        mgr = ConfigManager(config_file)
        mgr.save(cfg)
        assert config_file.exists()

    def test_save_preserves_nested_config(self, tmp_path: Path) -> None:
        """保存和加载保留嵌套配置"""
        config_file = tmp_path / "config.toml"
        cfg = AppConfig(
            crypto=CryptoConfig(iv="customiv12345678"),
            urls=UrlConfig(base="http://localhost:8080"),
            ai=AIConfig(api_key="sk-test", model="gpt-4"),
        )
        mgr = ConfigManager(config_file)
        mgr.save(cfg)
        loaded = mgr.load()
        assert loaded.crypto.iv == "customiv12345678"
        assert loaded.urls.base == "http://localhost:8080"
        assert loaded.ai.api_key == "sk-test"
        assert loaded.ai.model == "gpt-4"

    def test_roundtrip_all_defaults(self, tmp_path: Path) -> None:
        """默认值保存后加载一致"""
        config_file = tmp_path / "config.toml"
        cfg = AppConfig()
        mgr = ConfigManager(config_file)
        mgr.save(cfg)
        loaded = mgr.load()
        assert loaded == cfg


# ---------------------------------------------------------------------------
# ConfigManager — 旧版 JSON 迁移
# ---------------------------------------------------------------------------


class TestConfigManagerMigrate:
    def test_migrate_legacy_json(self, tmp_path: Path) -> None:
        """旧版 JSON 配置迁移"""
        json_file = tmp_path / "config.json"
        legacy = {
            "save_cookies": True,
            "proxies": {},
            "logLevel": "DEBUG",
            "qr_extra": {"show_in_terminal": None, "ensure_unicode": False},
            "image_path": "",
            "ai": {
                "enabled": True,
                "use_zhidao_ai": True,
                "openai": {
                    "api_base": "https://api.deepseek.com",
                    "api_key": "sk-test",
                    "model_name": "deepseek-v4-pro",
                },
                "use_stream": True,
            },
        }
        json_file.write_text(json.dumps(legacy), encoding="utf-8")

        mgr = ConfigManager(tmp_path / "config.toml")
        cfg = mgr.migrate(json_file)
        assert cfg.save_cookies is True
        assert cfg.display.log_level == "DEBUG"

    def test_migrate_extracts_openai_config(self, tmp_path: Path) -> None:
        """迁移时提取 OpenAI 配置"""
        json_file = tmp_path / "config.json"
        legacy = {
            "ai": {
                "enabled": True,
                "use_zhidao_ai": False,
                "openai": {
                    "api_base": "https://api.deepseek.com",
                    "api_key": "sk-abc123",
                    "model_name": "deepseek-v4-pro",
                },
                "use_stream": True,
            },
        }
        json_file.write_text(json.dumps(legacy), encoding="utf-8")

        mgr = ConfigManager(tmp_path / "config.toml")
        cfg = mgr.migrate(json_file)
        assert cfg.ai.api_key == "sk-abc123"
        assert cfg.ai.base_url == "https://api.deepseek.com"
        assert cfg.ai.model == "deepseek-v4-pro"

    def test_migrate_minimal_json(self, tmp_path: Path) -> None:
        """迁移最小 JSON 配置"""
        json_file = tmp_path / "config.json"
        json_file.write_text('{"save_cookies": false}', encoding="utf-8")

        mgr = ConfigManager(tmp_path / "config.toml")
        cfg = mgr.migrate(json_file)
        assert cfg.save_cookies is False

    def test_migrate_saves_toml(self, tmp_path: Path) -> None:
        """迁移后自动保存 TOML 文件"""
        json_file = tmp_path / "config.json"
        toml_file = tmp_path / "config.toml"
        json_file.write_text('{"save_cookies": false}', encoding="utf-8")

        mgr = ConfigManager(toml_file)
        mgr.migrate(json_file)
        assert toml_file.exists()
        # 重新加载验证
        loaded = mgr.load()
        assert loaded.save_cookies is False

    def test_migrate_logLevel_to_log_level(self, tmp_path: Path) -> None:
        """迁移时 logLevel → log_level 字段名转换"""
        json_file = tmp_path / "config.json"
        json_file.write_text('{"logLevel": "WARNING"}', encoding="utf-8")

        mgr = ConfigManager(tmp_path / "config.toml")
        cfg = mgr.migrate(json_file)
        assert cfg.display.log_level == "WARNING"
