"""
Configuration management for Obsidian Timemachine.

Handles loading, saving, and validating configuration from YAML files.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml


# Default configuration paths
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "ot"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"
DEFAULT_LOG_DIR = Path.home() / ".local" / "share" / "ot" / "logs"
DEFAULT_LOG_RETENTION_DAYS = 7


@dataclass
class Config:
    """Configuration data for Obsidian Timemachine.
    
    Attributes:
        source_dir: Path to the Obsidian vault (source directory).
        dest_dir: Path to the local Git repository (destination).
        log_dir: Path to store log files.
        ssh_key_path: Path to the SSH private key for Git operations.
        log_retention_days: Number of days to keep old log files.
    """
    source_dir: Path
    dest_dir: Path
    log_dir: Path = field(default_factory=lambda: DEFAULT_LOG_DIR)
    ssh_key_path: Path | None = None
    log_retention_days: int = DEFAULT_LOG_RETENTION_DAYS
    
    def __post_init__(self) -> None:
        """Convert string paths to Path objects."""
        if isinstance(self.source_dir, str):
            self.source_dir = Path(self.source_dir).expanduser().resolve()
        if isinstance(self.dest_dir, str):
            self.dest_dir = Path(self.dest_dir).expanduser().resolve()
        if isinstance(self.log_dir, str):
            self.log_dir = Path(self.log_dir).expanduser().resolve()
        if isinstance(self.ssh_key_path, str):
            self.ssh_key_path = Path(self.ssh_key_path).expanduser().resolve()
    
    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary for serialization."""
        return {
            "source_dir": str(self.source_dir),
            "dest_dir": str(self.dest_dir),
            "log_dir": str(self.log_dir),
            "ssh_key_path": str(self.ssh_key_path) if self.ssh_key_path else None,
            "log_retention_days": self.log_retention_days,
        }


class ConfigError(Exception):
    """Raised when configuration is invalid or cannot be loaded."""
    pass


def load_config(config_path: Path | None = None) -> Config:
    """Load configuration from a YAML file.
    
    Args:
        config_path: Path to the config file. Defaults to ~/.config/ot/config.yaml
        
    Returns:
        Config object with loaded values.
        
    Raises:
        ConfigError: If the config file doesn't exist or is invalid.
    """
    if config_path is None:
        config_path = DEFAULT_CONFIG_FILE
    
    config_path = Path(config_path).expanduser().resolve()
    
    if not config_path.exists():
        raise ConfigError(f"Configuration file not found: {config_path}")
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in config file: {e}")
    except OSError as e:
        raise ConfigError(f"Cannot read config file: {e}")
    
    # Validate required fields
    required_fields = ["source_dir", "dest_dir"]
    for field_name in required_fields:
        if field_name not in data:
            raise ConfigError(f"Missing required field: {field_name}")
    
    return Config(
        source_dir=data["source_dir"],
        dest_dir=data["dest_dir"],
        log_dir=data.get("log_dir", DEFAULT_LOG_DIR),
        ssh_key_path=data.get("ssh_key_path"),
        log_retention_days=data.get("log_retention_days", DEFAULT_LOG_RETENTION_DAYS),
    )


def save_config(config: Config, config_path: Path | None = None) -> None:
    """Save configuration to a YAML file.
    
    Args:
        config: Config object to save.
        config_path: Path to save the config file. Defaults to ~/.config/ot/config.yaml
        
    Raises:
        ConfigError: If the config file cannot be written.
    """
    if config_path is None:
        config_path = DEFAULT_CONFIG_FILE
    
    config_path = Path(config_path).expanduser().resolve()
    
    # Ensure parent directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(
                config.to_dict(),
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
    except OSError as e:
        raise ConfigError(f"Cannot write config file: {e}")


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Configuration validation failed: {'; '.join(errors)}")


def validate_config(config: Config) -> list[str]:
    """Validate configuration values.
    
    Checks that paths exist and have appropriate permissions.
    
    Args:
        config: Config object to validate.
        
    Returns:
        List of validation error messages (empty if valid).
    """
    errors: list[str] = []
    
    # Check source directory exists
    if not config.source_dir.exists():
        errors.append(f"Source directory does not exist: {config.source_dir}")
    elif not config.source_dir.is_dir():
        errors.append(f"Source path is not a directory: {config.source_dir}")
    
    # Check destination directory exists
    if not config.dest_dir.exists():
        errors.append(f"Destination directory does not exist: {config.dest_dir}")
    elif not config.dest_dir.is_dir():
        errors.append(f"Destination path is not a directory: {config.dest_dir}")
    elif not os.access(config.dest_dir, os.W_OK):
        errors.append(f"No write permission for destination: {config.dest_dir}")
    
    # Check SSH key if specified
    if config.ssh_key_path:
        if not config.ssh_key_path.exists():
            errors.append(f"SSH key file does not exist: {config.ssh_key_path}")
        elif not config.ssh_key_path.is_file():
            errors.append(f"SSH key path is not a file: {config.ssh_key_path}")
    
    # Check log retention days is positive
    if config.log_retention_days < 1:
        errors.append(f"Log retention days must be positive: {config.log_retention_days}")
    
    return errors
