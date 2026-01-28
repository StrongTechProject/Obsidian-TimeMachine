"""
Logging management for Obsidian Timemachine.

Provides structured logging with daily rotation and automatic cleanup.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import TextIO


# Module-level logger
_logger: logging.Logger | None = None

# Log format
LOG_FORMAT = "[%(asctime)s] %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class ColoredFormatter(logging.Formatter):
    """Formatter that adds color codes for terminal output."""
    
    COLORS = {
        logging.DEBUG: "\033[36m",     # Cyan
        logging.INFO: "\033[32m",      # Green
        logging.WARNING: "\033[33m",   # Yellow
        logging.ERROR: "\033[31m",     # Red
        logging.CRITICAL: "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record with color codes."""
        color = self.COLORS.get(record.levelno, "")
        formatted = super().format(record)
        if color and sys.stdout.isatty():
            return f"{color}{formatted}{self.RESET}"
        return formatted


def get_log_file_path(log_dir: Path) -> Path:
    """Get the log file path for today.
    
    Args:
        log_dir: Directory to store log files.
        
    Returns:
        Path to today's log file.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    return log_dir / f"backup-{today}.log"


def setup_logging(
    log_dir: Path,
    level: int = logging.INFO,
    console_output: bool = True,
) -> logging.Logger:
    """Set up the logging system.
    
    Creates a logger that writes to both a daily log file and optionally
    to the console with colored output.
    
    Args:
        log_dir: Directory to store log files.
        level: Logging level (default: INFO).
        console_output: Whether to also log to console.
        
    Returns:
        Configured logger instance.
    """
    global _logger
    
    # Ensure log directory exists
    log_dir = Path(log_dir).expanduser().resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Create or get logger
    logger = logging.getLogger("obsidian_timemachine")
    logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # File handler - plain text format
    log_file = get_log_file_path(log_dir)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    logger.addHandler(file_handler)
    
    # Console handler - colored output
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(ColoredFormatter(LOG_FORMAT, LOG_DATE_FORMAT))
        logger.addHandler(console_handler)
    
    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    """Get the configured logger instance.
    
    Returns:
        Logger instance. Creates a basic one if setup_logging wasn't called.
    """
    global _logger
    if _logger is None:
        # Create a basic console-only logger as fallback
        logger = logging.getLogger("obsidian_timemachine")
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(ColoredFormatter(LOG_FORMAT, LOG_DATE_FORMAT))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        _logger = logger
    return _logger


def rotate_logs(log_dir: Path, retention_days: int) -> int:
    """Remove old log files.
    
    Deletes log files older than the specified retention period.
    
    Args:
        log_dir: Directory containing log files.
        retention_days: Number of days to keep logs.
        
    Returns:
        Number of log files deleted.
    """
    log_dir = Path(log_dir).expanduser().resolve()
    
    if not log_dir.exists():
        return 0
    
    cutoff_date = datetime.now() - timedelta(days=retention_days)
    deleted_count = 0
    
    for log_file in log_dir.glob("backup-*.log"):
        try:
            # Extract date from filename: backup-YYYY-MM-DD.log
            date_str = log_file.stem.replace("backup-", "")
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
            
            if file_date < cutoff_date:
                log_file.unlink()
                deleted_count += 1
        except (ValueError, OSError):
            # Skip files with invalid date format or that can't be deleted
            continue
    
    return deleted_count
