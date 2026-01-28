"""Tests for the logging module."""

import logging
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from ot.logger import (
    get_log_file_path,
    get_logger,
    rotate_logs,
    setup_logging,
)


class TestGetLogFilePath:
    """Tests for get_log_file_path function."""
    
    def test_log_file_path_format(self, tmp_path: Path) -> None:
        """Test that log file path has correct format."""
        log_path = get_log_file_path(tmp_path)
        
        today = datetime.now().strftime("%Y-%m-%d")
        expected_name = f"backup-{today}.log"
        
        assert log_path.parent == tmp_path
        assert log_path.name == expected_name


class TestSetupLogging:
    """Tests for setup_logging function."""
    
    def test_setup_creates_log_dir(self, tmp_path: Path) -> None:
        """Test that setup_logging creates the log directory."""
        log_dir = tmp_path / "logs"
        
        setup_logging(log_dir, console_output=False)
        
        assert log_dir.exists()
    
    def test_setup_creates_log_file(self, tmp_path: Path) -> None:
        """Test that setup_logging creates a log file."""
        log_dir = tmp_path / "logs"
        
        logger = setup_logging(log_dir, console_output=False)
        logger.info("Test message")
        
        log_files = list(log_dir.glob("backup-*.log"))
        assert len(log_files) == 1
    
    def test_logger_writes_to_file(self, tmp_path: Path) -> None:
        """Test that logger writes messages to file."""
        log_dir = tmp_path / "logs"
        
        logger = setup_logging(log_dir, console_output=False)
        logger.info("Test log message")
        
        log_file = get_log_file_path(log_dir)
        content = log_file.read_text()
        
        assert "Test log message" in content


class TestRotateLogs:
    """Tests for rotate_logs function."""
    
    def test_rotate_deletes_old_logs(self, tmp_path: Path) -> None:
        """Test that rotate_logs deletes old log files."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        
        # Create old log file
        old_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        old_log = log_dir / f"backup-{old_date}.log"
        old_log.write_text("old log content")
        
        # Create recent log file
        today = datetime.now().strftime("%Y-%m-%d")
        new_log = log_dir / f"backup-{today}.log"
        new_log.write_text("new log content")
        
        # Rotate with 7 days retention
        deleted = rotate_logs(log_dir, retention_days=7)
        
        assert deleted == 1
        assert not old_log.exists()
        assert new_log.exists()
    
    def test_rotate_keeps_recent_logs(self, tmp_path: Path) -> None:
        """Test that rotate_logs keeps recent log files."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        
        # Create log from 3 days ago
        recent_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        recent_log = log_dir / f"backup-{recent_date}.log"
        recent_log.write_text("recent log content")
        
        # Rotate with 7 days retention
        deleted = rotate_logs(log_dir, retention_days=7)
        
        assert deleted == 0
        assert recent_log.exists()
    
    def test_rotate_empty_dir(self, tmp_path: Path) -> None:
        """Test rotate_logs with empty directory."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        
        deleted = rotate_logs(log_dir, retention_days=7)
        
        assert deleted == 0
    
    def test_rotate_nonexistent_dir(self, tmp_path: Path) -> None:
        """Test rotate_logs with non-existent directory."""
        log_dir = tmp_path / "nonexistent"
        
        deleted = rotate_logs(log_dir, retention_days=7)
        
        assert deleted == 0


class TestGetLogger:
    """Tests for get_logger function."""
    
    def test_get_logger_returns_logger(self) -> None:
        """Test that get_logger returns a logger instance."""
        logger = get_logger()
        
        assert isinstance(logger, logging.Logger)
        assert logger.name == "obsidian_timemachine"
