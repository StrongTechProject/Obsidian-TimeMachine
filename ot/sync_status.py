"""
Sync status tracking for Obsidian Timemachine.

Stores and retrieves the last sync status for display in the menu.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Status file location
DEFAULT_STATUS_DIR = Path.home() / ".local" / "share" / "ot"
STATUS_FILE = DEFAULT_STATUS_DIR / "last_sync.json"


@dataclass
class SyncStatus:
    """Represents the status of the last sync operation.
    
    Attributes:
        timestamp: When the sync occurred.
        success: Whether the sync succeeded.
        result_type: Type of result (e.g., 'pushed', 'no_changes', 'failed').
        message: Human-readable message about the result.
        commit_hash: Git commit hash if a commit was made.
    """
    timestamp: datetime
    success: bool
    result_type: str  # 'pushed', 'no_changes', 'failed', 'pull_only'
    message: str
    commit_hash: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "result_type": self.result_type,
            "message": self.message,
            "commit_hash": self.commit_hash,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SyncStatus":
        """Create from dictionary."""
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            success=data["success"],
            result_type=data["result_type"],
            message=data["message"],
            commit_hash=data.get("commit_hash"),
        )
    
    def time_ago(self) -> str:
        """Get human-readable time since sync."""
        now = datetime.now()
        delta = now - self.timestamp
        
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return "Just now"
        
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        
        days = hours // 24
        if days == 1:
            return "Yesterday"
        return f"{days}d ago"
    
    def status_emoji(self) -> str:
        """Get emoji for the result type."""
        if not self.success:
            return "❌"
        if self.result_type == "pushed":
            return "✅"
        if self.result_type == "no_changes":
            return "📦"
        return "✓"


def save_sync_status(status: SyncStatus) -> None:
    """Save the sync status to disk.
    
    Args:
        status: SyncStatus to save.
    """
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status.to_dict(), f, indent=2)
    except OSError:
        pass  # Best effort, don't fail on status save


def load_sync_status() -> SyncStatus | None:
    """Load the last sync status from disk.
    
    Returns:
        SyncStatus or None if no status file exists.
    """
    if not STATUS_FILE.exists():
        return None
    
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SyncStatus.from_dict(data)
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def record_sync_result(
    success: bool,
    result_type: str,
    message: str,
    commit_hash: str | None = None,
) -> SyncStatus:
    """Record a sync result.
    
    Args:
        success: Whether the sync succeeded.
        result_type: Type of result.
        message: Human-readable message.
        commit_hash: Git commit hash if applicable.
        
    Returns:
        The created SyncStatus.
    """
    status = SyncStatus(
        timestamp=datetime.now(),
        success=success,
        result_type=result_type,
        message=message,
        commit_hash=commit_hash,
    )
    save_sync_status(status)
    return status
