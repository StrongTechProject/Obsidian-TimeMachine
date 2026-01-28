"""
Rsync synchronization wrapper.

Provides a robust interface to rsync for mirroring directories.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from .logger import get_logger


class RsyncExitCode(IntEnum):
    """Common rsync exit codes."""
    SUCCESS = 0
    SYNTAX_ERROR = 1
    PROTOCOL_ERROR = 2
    IO_ERROR = 3
    REQUESTED_ACTION_NOT_SUPPORTED = 4
    STARTUP_ERROR = 5
    PARTIAL_TRANSFER_ERROR = 23
    VANISHED_SOURCE_FILES = 24
    MAX_DELETE_LIMIT = 25
    TIMEOUT = 30
    CONNECTION_TIMEOUT = 35


@dataclass
class RsyncResult:
    """Result of an rsync operation.
    
    Attributes:
        success: Whether the sync completed successfully.
        exit_code: Rsync exit code.
        stdout: Standard output from rsync.
        stderr: Standard error from rsync.
        warning: Optional warning message for partial success.
    """
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    warning: str | None = None


def check_rsync_available() -> bool:
    """Check if rsync is available on the system.
    
    Returns:
        True if rsync is found, False otherwise.
    """
    return shutil.which("rsync") is not None


def check_rsync_iconv_support() -> bool:
    """Check if rsync supports iconv for filename encoding.
    
    Returns:
        True if rsync has iconv support, False otherwise.
    """
    try:
        result = subprocess.run(
            ["rsync", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return "iconv" in result.stdout.lower()
    except (subprocess.SubprocessError, OSError):
        return False


def build_rsync_command(
    source: Path,
    dest: Path,
    exclude_patterns: list[str] | None = None,
    use_iconv: bool = False,
    delete: bool = False,
    dry_run: bool = False,
) -> list[str]:
    """Build the rsync command with appropriate options.
    
    Args:
        source: Source directory path.
        dest: Destination directory path.
        exclude_patterns: Patterns to exclude from sync.
        use_iconv: Whether to use iconv for macOS filename normalization.
        delete: Whether to delete extraneous files in destination.
        dry_run: If True, only simulate the sync.
        
    Returns:
        List of command arguments.
    """
    cmd = ["rsync", "-av", "--progress"]
    
    if dry_run:
        cmd.append("--dry-run")
    
    if delete:
        cmd.append("--delete")
    
    # Default exclusions
    default_excludes = [".git", ".DS_Store", ".trash", ".Trash", "*.icloud"]
    exclude_patterns = exclude_patterns or []
    all_excludes = default_excludes + exclude_patterns
    
    for pattern in all_excludes:
        cmd.extend(["--exclude", pattern])
    
    # Add iconv for macOS Unicode normalization if supported
    if use_iconv:
        cmd.append("--iconv=utf-8-mac,utf-8")
    
    # Source must end with / to copy contents, not the directory itself
    source_str = str(source).rstrip("/") + "/"
    cmd.extend([source_str, str(dest)])
    
    return cmd


def run_rsync(
    source: Path,
    dest: Path,
    exclude_patterns: list[str] | None = None,
    delete: bool = False,
    dry_run: bool = False,
    timeout: int | None = 300,
) -> RsyncResult:
    """Execute rsync to sync source to destination.
    
    Args:
        source: Source directory path.
        dest: Destination directory path.
        exclude_patterns: Additional patterns to exclude.
        delete: Whether to delete extraneous files in destination.
        dry_run: If True, only simulate the sync.
        timeout: Command timeout in seconds (None for no timeout).
        
    Returns:
        RsyncResult with operation status and output.
    """
    logger = get_logger()
    
    source = Path(source).expanduser().resolve()
    dest = Path(dest).expanduser().resolve()
    
    # Check rsync availability
    if not check_rsync_available():
        return RsyncResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr="rsync command not found. Please install rsync.",
            warning=None,
        )
    
    # Check for iconv support
    use_iconv = check_rsync_iconv_support()
    if use_iconv:
        logger.debug("rsync iconv support detected; enabling filename normalization.")
    
    # Build command
    cmd = build_rsync_command(
        source=source,
        dest=dest,
        exclude_patterns=exclude_patterns,
        use_iconv=use_iconv,
        delete=delete,
        dry_run=dry_run,
    )
    
    logger.info(f"📂 Starting rsync: {source} → {dest}")
    logger.debug(f"Command: {' '.join(cmd)}")
    
    if not delete:
        logger.info(
            "⚠️ Running without --delete to protect Git repository. "
            "Deleted files in source will remain in destination."
        )
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
        )
        
        exit_code = result.returncode
        # Decode with error handling for non-UTF-8 bytes (e.g., macOS filenames)
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")
        
        # Interpret exit code
        if exit_code == RsyncExitCode.SUCCESS:
            logger.info("✅ Rsync completed successfully.")
            return RsyncResult(
                success=True,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
            )
        
        elif exit_code == RsyncExitCode.PARTIAL_TRANSFER_ERROR:
            warning = (
                "rsync reported partial transfer (code 23). "
                "Some files may have issues."
            )
            logger.warning(f"⚠️ {warning}")
            return RsyncResult(
                success=True,  # Partial success is still success
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                warning=warning,
            )
        
        elif exit_code == RsyncExitCode.VANISHED_SOURCE_FILES:
            warning = (
                "rsync reported vanished source files (code 24). "
                "Some files disappeared during sync (usually harmless)."
            )
            logger.warning(f"⚠️ {warning}")
            return RsyncResult(
                success=True,  # Vanished files are usually temp files
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                warning=warning,
            )
        
        else:
            logger.error(f"❌ rsync failed with exit code {exit_code}")
            logger.error(f"stderr: {stderr}")
            return RsyncResult(
                success=False,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
            )
    
    except subprocess.TimeoutExpired:
        logger.error(f"❌ rsync timed out after {timeout}s")
        return RsyncResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr=f"rsync timed out after {timeout} seconds",
        )
    
    except OSError as e:
        logger.error(f"❌ Failed to execute rsync: {e}")
        return RsyncResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr=str(e),
        )


def copy_directory_initial(
    source: Path,
    dest: Path,
    exclude_patterns: list[str] | None = None,
) -> RsyncResult:
    """Perform initial copy using cp for reliability.
    
    For the first sync, using cp is more reliable than rsync,
    especially with iCloud directories.
    
    Args:
        source: Source directory path.
        dest: Destination directory path.
        exclude_patterns: Patterns to exclude (cleaned up after copy).
        
    Returns:
        RsyncResult with operation status.
    """
    logger = get_logger()
    
    source = Path(source).expanduser().resolve()
    dest = Path(dest).expanduser().resolve()
    
    logger.info("📦 First sync: using cp for reliability...")
    
    # Count files for progress indication
    try:
        file_count = sum(1 for _ in source.rglob("*") if _.is_file())
        logger.info(f"📊 Found {file_count} files to copy")
    except OSError:
        file_count = 0
    
    try:
        # Use cp -Rp for recursive copy preserving attributes
        cmd = ["cp", "-Rp", f"{source}/.", str(dest)]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutes for large vaults
        )
        
        if result.returncode != 0:
            return RsyncResult(
                success=False,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        
        # Clean up excluded patterns after copy
        default_excludes = [".DS_Store", ".trash", ".Trash"]
        exclude_patterns = exclude_patterns or []
        all_excludes = default_excludes + exclude_patterns
        
        for pattern in all_excludes:
            for match in dest.rglob(pattern):
                try:
                    if match.is_dir():
                        shutil.rmtree(match)
                    else:
                        match.unlink()
                except OSError:
                    pass
        
        # Remove .icloud placeholder files
        for icloud_file in dest.rglob("*.icloud"):
            try:
                icloud_file.unlink()
            except OSError:
                pass
        
        logger.info("✅ Initial copy completed successfully.")
        return RsyncResult(
            success=True,
            exit_code=0,
            stdout="Initial copy completed",
            stderr="",
        )
    
    except subprocess.TimeoutExpired:
        return RsyncResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr="Copy operation timed out",
        )
    
    except OSError as e:
        return RsyncResult(
            success=False,
            exit_code=-1,
            stdout="",
            stderr=str(e),
        )
