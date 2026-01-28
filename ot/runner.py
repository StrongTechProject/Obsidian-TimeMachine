"""
Main sync runner for Obsidian Timemachine.

Orchestrates the complete backup workflow: iCloud wait, rsync, Git operations.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .config import Config, ConfigError, load_config, validate_config
from .git_ops import (
    GitResult,
    commit_and_push,
    has_commits,
    is_git_repo,
    pull,
)
from .icloud import wait_for_icloud_sync
from .logger import get_logger, rotate_logs, setup_logging
from .sync import RsyncResult, copy_directory_initial, run_rsync


@dataclass
class SyncResult:
    """Result of a complete sync operation.
    
    Attributes:
        success: Whether the overall sync succeeded.
        rsync_result: Result of rsync operation.
        git_result: Result of Git operations.
        errors: List of error messages.
        warnings: List of warning messages.
    """
    success: bool
    rsync_result: RsyncResult | None = None
    git_result: GitResult | None = None
    errors: list[str] | None = None
    warnings: list[str] | None = None


class SyncRunner:
    """Orchestrates the backup workflow.
    
    This class manages the complete sync process:
    1. Load and validate configuration
    2. Set up logging with rotation
    3. Wait for iCloud sync (if applicable)
    4. Sync files using rsync
    5. Commit and push to Git
    """
    
    def __init__(
        self,
        config: Config | None = None,
        config_path: Path | None = None,
    ):
        """Initialize the sync runner.
        
        Args:
            config: Pre-loaded configuration object.
            config_path: Path to config file (used if config is None).
        """
        self._config = config
        self._config_path = config_path
        self._logger = None
        self._errors: list[str] = []
        self._warnings: list[str] = []
    
    @property
    def config(self) -> Config:
        """Get the configuration, loading if necessary."""
        if self._config is None:
            self._config = load_config(self._config_path)
        return self._config
    
    def _setup_logging(self) -> None:
        """Initialize the logging system."""
        self._logger = setup_logging(
            log_dir=self.config.log_dir,
            console_output=True,
        )
        
        # Rotate old logs
        deleted = rotate_logs(
            self.config.log_dir,
            self.config.log_retention_days,
        )
        if deleted > 0:
            self._logger.debug(f"Cleaned up {deleted} old log files.")
    
    def _validate_environment(self) -> bool:
        """Validate the environment and configuration.
        
        Returns:
            True if validation passes, False otherwise.
        """
        logger = get_logger()
        
        # Validate config
        errors = validate_config(self.config)
        if errors:
            for error in errors:
                logger.error(f"❌ {error}")
                self._errors.append(error)
            return False
        
        # Check Git repository
        if not is_git_repo(self.config.dest_dir):
            error = f"Destination is not a Git repository: {self.config.dest_dir}"
            logger.error(f"❌ {error}")
            logger.error("   Please initialize with: git init && git remote add origin <url>")
            self._errors.append(error)
            return False
        
        return True
    
    def _should_skip_rsync(self) -> bool:
        """Check if rsync should be skipped (same source and dest).
        
        Returns:
            True if rsync should be skipped.
        """
        try:
            real_source = self.config.source_dir.resolve()
            real_dest = self.config.dest_dir.resolve()
            return real_source == real_dest
        except OSError:
            return False
    
    def _sync_files(self) -> RsyncResult | None:
        """Perform file synchronization.
        
        Returns:
            RsyncResult or None if sync was skipped.
        """
        logger = get_logger()
        
        if self._should_skip_rsync():
            logger.info(
                "📂 Source and destination are the same; "
                "skipping rsync and going straight to Git..."
            )
            return None
        
        # Check if this is the first sync (no Git history)
        is_first_sync = not has_commits(self.config.dest_dir)
        
        if is_first_sync:
            logger.info("🆕 First-time sync detected (no Git history)")
            return copy_directory_initial(
                source=self.config.source_dir,
                dest=self.config.dest_dir,
            )
        else:
            return run_rsync(
                source=self.config.source_dir,
                dest=self.config.dest_dir,
                delete=False,  # Don't delete to protect .git
            )
    
    def run(self) -> SyncResult:
        """Execute the complete sync workflow.
        
        Returns:
            SyncResult with operation status and details.
        """
        self._errors = []
        self._warnings = []
        
        # Step 1: Set up logging
        try:
            self._setup_logging()
        except Exception as e:
            return SyncResult(
                success=False,
                errors=[f"Failed to set up logging: {e}"],
            )
        
        logger = get_logger()
        logger.info("=== Starting automated backup ===")
        
        # Step 2: Validate environment
        if not self._validate_environment():
            return SyncResult(
                success=False,
                errors=self._errors,
            )
        
        # Step 3: Git pull (fetch remote updates)
        logger.info("🔄 Checking remote updates...")
        pull_result = pull(
            repo_path=self.config.dest_dir,
            ssh_key_path=self.config.ssh_key_path,
        )
        
        if not pull_result.success:
            # Pull failure is usually network issues; continue with local sync
            self._warnings.append(f"Pull failed (network issue?): {pull_result.error}")
        
        # Step 4: Wait for iCloud sync
        if not self._should_skip_rsync():
            wait_for_icloud_sync(
                source_dir=self.config.source_dir,
                max_wait_seconds=60,
            )
        
        # Step 5: Sync files
        rsync_result = self._sync_files()
        
        if rsync_result is not None and not rsync_result.success:
            error = f"Rsync failed: {rsync_result.stderr}"
            logger.error(f"❌ {error}")
            return SyncResult(
                success=False,
                rsync_result=rsync_result,
                errors=[error],
                warnings=self._warnings,
            )
        
        if rsync_result is not None and rsync_result.warning:
            self._warnings.append(rsync_result.warning)
        
        # Step 6: Commit and push
        git_result = commit_and_push(
            repo_path=self.config.dest_dir,
            ssh_key_path=self.config.ssh_key_path,
        )
        
        if not git_result.success:
            error = f"Git operation failed: {git_result.error}"
            logger.error(f"❌ {error}")
            return SyncResult(
                success=False,
                rsync_result=rsync_result,
                git_result=git_result,
                errors=[error],
                warnings=self._warnings,
            )
        
        logger.info("=== Backup completed successfully ===")
        
        return SyncResult(
            success=True,
            rsync_result=rsync_result,
            git_result=git_result,
            warnings=self._warnings if self._warnings else None,
        )


def run_sync(
    config_path: Path | None = None,
    config: Config | None = None,
) -> SyncResult:
    """Convenience function to run a sync.
    
    Args:
        config_path: Path to configuration file.
        config: Pre-loaded configuration object.
        
    Returns:
        SyncResult with operation status.
    """
    runner = SyncRunner(config=config, config_path=config_path)
    return runner.run()


def main() -> int:
    """Entry point for direct script execution.
    
    Returns:
        Exit code (0 for success, 1 for failure).
    """
    result = run_sync()
    
    if not result.success:
        if result.errors:
            for error in result.errors:
                print(f"Error: {error}", file=sys.stderr)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
