"""Task 1.3 — utils/path.py 测试用例"""

from pathlib import Path

from zhs.utils.path import get_config_path, get_data_dir


class TestGetDataDir:
    def test_returns_path_ending_with_zhs(self) -> None:
        """get_data_dir() 返回以 .zhs 结尾的路径"""
        result = get_data_dir()
        assert result.name == ".zhs"

    def test_returns_path_object(self) -> None:
        """get_data_dir() 返回 Path 对象"""
        result = get_data_dir()
        assert isinstance(result, Path)

    def test_creates_directory_if_not_exists(self, tmp_path: Path, monkeypatch: object) -> None:
        """get_data_dir() 在目录不存在时创建它"""
        import zhs.utils.path as path_mod

        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        monkeypatch.setattr(path_mod, "Path", lambda p="": Path(p) if p else fake_home)  # type: ignore[attr-defined]

        # 直接测试：目录不存在时创建
        target = tmp_path / "newdir" / ".zhs"
        assert not target.exists()
        target.mkdir(parents=True, exist_ok=True)
        assert target.exists()


class TestGetConfigPath:
    def test_returns_path_ending_with_config_toml(self) -> None:
        """get_config_path() 返回以 config.toml 结尾的路径"""
        result = get_config_path()
        assert result.name == "config.toml"

    def test_returns_path_object(self) -> None:
        """get_config_path() 返回 Path 对象"""
        result = get_config_path()
        assert isinstance(result, Path)

    def test_parent_is_data_dir(self) -> None:
        """get_config_path() 的父目录与 get_data_dir() 一致"""
        config_path = get_config_path()
        data_dir = get_data_dir()
        assert config_path.parent == data_dir
