"""Tests for the configuration module."""

import tempfile
from pathlib import Path

import pytest
import yaml

from ot.config import (
    Config,
    ConfigError,
    DEFAULT_LOG_RETENTION_DAYS,
    load_config,
    save_config,
    validate_config,
)


class TestConfig:
    """Tests for the Config dataclass."""
    
    def test_config_creation(self, tmp_path: Path) -> None:
        """Test creating a Config object."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()
        
        config = Config(
            source_dir=source,
            dest_dir=dest,
        )
        
        assert config.source_dir == source
        assert config.dest_dir == dest
        assert config.log_retention_days == DEFAULT_LOG_RETENTION_DAYS
    
    def test_config_string_paths(self, tmp_path: Path) -> None:
        """Test that string paths are converted to Path objects."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()
        
        config = Config(
            source_dir=str(source),
            dest_dir=str(dest),
        )
        
        assert isinstance(config.source_dir, Path)
        assert isinstance(config.dest_dir, Path)
    
    def test_config_to_dict(self, tmp_path: Path) -> None:
        """Test converting config to dictionary."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()
        
        config = Config(
            source_dir=source,
            dest_dir=dest,
        )
        
        data = config.to_dict()
        
        assert "source_dir" in data
        assert "dest_dir" in data
        assert data["source_dir"] == str(source)


class TestLoadConfig:
    """Tests for load_config function."""
    
    def test_load_valid_config(self, tmp_path: Path) -> None:
        """Test loading a valid configuration file."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()
        
        config_file = tmp_path / "config.yaml"
        config_data = {
            "source_dir": str(source),
            "dest_dir": str(dest),
            "log_retention_days": 14,
        }
        
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)
        
        config = load_config(config_file)
        
        assert config.source_dir == source
        assert config.dest_dir == dest
        assert config.log_retention_days == 14
    
    def test_load_missing_config(self, tmp_path: Path) -> None:
        """Test loading a non-existent config file."""
        missing_file = tmp_path / "missing.yaml"
        
        with pytest.raises(ConfigError, match="not found"):
            load_config(missing_file)
    
    def test_load_config_missing_required_field(self, tmp_path: Path) -> None:
        """Test loading config with missing required fields."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "source_dir": str(tmp_path / "source"),
            # Missing dest_dir
        }
        
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)
        
        with pytest.raises(ConfigError, match="Missing required field"):
            load_config(config_file)


class TestSaveConfig:
    """Tests for save_config function."""
    
    def test_save_config(self, tmp_path: Path) -> None:
        """Test saving a configuration file."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()
        
        config = Config(
            source_dir=source,
            dest_dir=dest,
        )
        
        config_file = tmp_path / "config.yaml"
        save_config(config, config_file)
        
        assert config_file.exists()
        
        # Verify contents
        with open(config_file) as f:
            data = yaml.safe_load(f)
        
        assert data["source_dir"] == str(source)
        assert data["dest_dir"] == str(dest)
    
    def test_save_config_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Test that save_config creates parent directories."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()
        
        config = Config(source_dir=source, dest_dir=dest)
        
        config_file = tmp_path / "subdir" / "config.yaml"
        save_config(config, config_file)
        
        assert config_file.exists()


class TestValidateConfig:
    """Tests for validate_config function."""
    
    def test_validate_valid_config(self, tmp_path: Path) -> None:
        """Test validating a valid configuration."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()
        
        config = Config(source_dir=source, dest_dir=dest)
        
        errors = validate_config(config)
        
        assert len(errors) == 0
    
    def test_validate_missing_source(self, tmp_path: Path) -> None:
        """Test validating with missing source directory."""
        source = tmp_path / "missing_source"
        dest = tmp_path / "dest"
        dest.mkdir()
        
        config = Config(source_dir=source, dest_dir=dest)
        
        errors = validate_config(config)
        
        assert len(errors) == 1
        assert "Source directory does not exist" in errors[0]
    
    def test_validate_missing_dest(self, tmp_path: Path) -> None:
        """Test validating with missing destination directory."""
        source = tmp_path / "source"
        dest = tmp_path / "missing_dest"
        source.mkdir()
        
        config = Config(source_dir=source, dest_dir=dest)
        
        errors = validate_config(config)
        
        assert len(errors) == 1
        assert "Destination directory does not exist" in errors[0]
    
    def test_validate_invalid_log_retention(self, tmp_path: Path) -> None:
        """Test validating with invalid log retention days."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()
        
        config = Config(
            source_dir=source,
            dest_dir=dest,
            log_retention_days=0,
        )
        
        errors = validate_config(config)
        
        assert len(errors) == 1
        assert "Log retention days must be positive" in errors[0]
