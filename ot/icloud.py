"""
iCloud synchronization wait utilities.

Provides functions to wait for iCloud to finish syncing files before
performing backup operations. Handles both legacy .icloud placeholder files
and modern "dataless" (evicted) files.
"""

from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from .logger import get_logger

# macOS file flag for compressed/dataless files
# UF_COMPRESSED = 0x00000020
UF_COMPRESSED = 0x20


def check_brctl_available() -> bool:
    """Check if brctl command is available on the system.
    
    brctl is macOS's official tool for managing CloudDocs/iCloud files.
    
    Returns:
        True if brctl is available, False otherwise.
    """
    try:
        result = subprocess.run(
            ["which", "brctl"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def is_dataless_file(file_path: Path) -> bool:
    """Check if a file is in iCloud "dataless" (evicted) state.
    
    Dataless files have their content stored only in iCloud, with only
    metadata present locally. They have the UF_COMPRESSED flag set and
    zero allocated blocks.
    
    Args:
        file_path: Path to the file to check.
        
    Returns:
        True if the file is dataless, False otherwise.
    """
    try:
        st = os.stat(file_path)
        # Check if UF_COMPRESSED flag is set and no blocks allocated
        has_compressed_flag = bool(st.st_flags & UF_COMPRESSED)
        has_no_blocks = st.st_blocks == 0
        has_size = st.st_size > 0
        
        # A truly dataless file has the compressed flag, some reported size,
        # but no actual disk blocks allocated
        return has_compressed_flag and has_no_blocks and has_size
    except (OSError, AttributeError):
        # AttributeError: st_flags not available on non-macOS
        return False


def find_dataless_files(
    directory: Path,
    exclude_patterns: list[str] | None = None,
) -> list[Path]:
    """Find iCloud "dataless" (evicted) files in a directory.
    
    These are files that appear to exist but have their content stored
    only in iCloud, not downloaded locally. They will cause rsync to fail
    with "Resource deadlock avoided" (exit code 20).
    
    Args:
        directory: Directory to search recursively.
        exclude_patterns: Filename patterns to exclude.
        
    Returns:
        List of paths to dataless files.
    """
    directory = Path(directory).expanduser().resolve()
    exclude_patterns = exclude_patterns or [".DS_Store"]
    
    if not directory.exists():
        return []
    
    dataless_files: list[Path] = []
    
    try:
        for file_path in directory.rglob("*"):
            if not file_path.is_file():
                continue
            
            # Check exclusion patterns
            if any(pattern in file_path.name for pattern in exclude_patterns):
                continue
            
            if is_dataless_file(file_path):
                dataless_files.append(file_path)
    except OSError:
        pass
    
    return dataless_files


def download_dataless_file(
    file_path: Path,
    timeout: int = 30,
    verify_wait: float = 0.5,
    max_verify_attempts: int = 3,
) -> bool:
    """Trigger download of a single dataless file from iCloud.
    
    Prefers using macOS's official 'brctl download' command for reliability.
    Falls back to 'cat' if brctl is not available.
    
    Args:
        file_path: Path to the dataless file.
        timeout: Maximum seconds to wait for download command.
        verify_wait: Seconds to wait before each verification attempt.
        max_verify_attempts: Maximum number of verification attempts.
        
    Returns:
        True if file was successfully downloaded, False otherwise.
    """
    use_brctl = check_brctl_available()
    
    try:
        if use_brctl:
            # Use macOS official brctl command for more reliable downloads
            subprocess.run(
                ["brctl", "download", str(file_path)],
                capture_output=True,
                timeout=timeout,
            )
        else:
            # Fallback: Reading the file triggers iCloud download
            subprocess.run(
                ["cat", str(file_path)],
                capture_output=True,
                timeout=timeout,
            )
        
        # iCloud download is async, wait and verify with retries
        for attempt in range(max_verify_attempts):
            time.sleep(verify_wait)
            if not is_dataless_file(file_path):
                return True
            # Increase wait time for subsequent attempts
            verify_wait = min(verify_wait * 1.5, 2.0)
        
        # Final check
        return not is_dataless_file(file_path)
        
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
        return False


def download_dataless_files(
    directory: Path,
    max_files: int = 1000,
    timeout_per_file: int = 30,
    use_batch_mode: bool = True,
    batch_size: int = 50,
) -> tuple[int, int]:
    """Download all dataless files in a directory.
    
    Supports both single-file and batch download modes. Batch mode uses
    brctl with xargs for parallel downloads, which is faster for many files.
    
    Args:
        directory: Directory to search.
        max_files: Maximum number of files to download in one batch.
        timeout_per_file: Timeout in seconds per file (single mode only).
        use_batch_mode: If True, use batch download with brctl + xargs.
        batch_size: Number of files to download in each batch.
        
    Returns:
        Tuple of (successfully downloaded count, failed count).
    """
    logger = get_logger()
    
    dataless_files = find_dataless_files(directory)
    
    if not dataless_files:
        return (0, 0)
    
    total_files = len(dataless_files)
    files_to_download = dataless_files[:max_files]
    
    if total_files > max_files:
        logger.warning(
            f"⚠️ Found {total_files} dataless files, "
            f"only downloading first {max_files}"
        )
    
    logger.info(f"☁️ Downloading {len(files_to_download)} dataless files from iCloud...")
    
    # Try batch mode with brctl if available
    if use_batch_mode and check_brctl_available():
        logger.info("   Using batch mode with brctl...")
        success_count, fail_count = _download_batch_brctl(
            files_to_download, batch_size, logger
        )
    else:
        # Fall back to single-file mode
        success_count = 0
        fail_count = 0
        
        for i, file_path in enumerate(files_to_download, 1):
            relative_path = file_path.name
            if len(relative_path) > 40:
                relative_path = "..." + relative_path[-37:]
            
            if download_dataless_file(file_path, timeout_per_file):
                success_count += 1
                logger.debug(f"   [{i}/{len(files_to_download)}] ✓ {relative_path}")
            else:
                fail_count += 1
                logger.warning(f"   [{i}/{len(files_to_download)}] ✗ {relative_path}")
    
    if success_count > 0:
        logger.info(f"✅ Downloaded {success_count} files from iCloud")
    if fail_count > 0:
        logger.warning(f"⚠️ Failed to download {fail_count} files")
    
    return (success_count, fail_count)


def _download_batch_brctl(
    files: list[Path],
    batch_size: int,
    logger,
) -> tuple[int, int]:
    """Download files in batches using brctl.
    
    Args:
        files: List of files to download.
        batch_size: Number of files per batch.
        logger: Logger instance.
        
    Returns:
        Tuple of (success count, fail count).
    """
    total = len(files)
    success_count = 0
    fail_count = 0
    
    # Process in batches
    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch = files[batch_start:batch_end]
        
        logger.info(f"   Batch {batch_start + 1}-{batch_end}/{total}...")
        
        # Trigger downloads for entire batch first
        for file_path in batch:
            try:
                subprocess.run(
                    ["brctl", "download", str(file_path)],
                    capture_output=True,
                    timeout=5,  # Short timeout, just trigger
                )
            except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
                pass
        
        # Wait for batch to download
        time.sleep(2.0)
        
        # Verify which files were downloaded
        for file_path in batch:
            # Give a bit more time and re-check
            for _ in range(3):
                if not is_dataless_file(file_path):
                    success_count += 1
                    break
                time.sleep(0.3)
            else:
                fail_count += 1
    
    return (success_count, fail_count)


def find_icloud_placeholders(directory: Path) -> list[Path]:
    """Find iCloud placeholder files (.icloud files).
    
    These files indicate that the actual content hasn't been downloaded
    from iCloud yet. This is the legacy format; newer macOS versions
    may use "dataless" files instead.
    
    Args:
        directory: Directory to search.
        
    Returns:
        List of paths to .icloud placeholder files.
    """
    directory = Path(directory).expanduser().resolve()
    
    if not directory.exists():
        return []
    
    return list(directory.rglob("*.icloud"))


def find_recently_modified_files(
    directory: Path,
    seconds: int = 5,
    exclude_patterns: list[str] | None = None,
) -> list[Path]:
    """Find files modified within the last N seconds.
    
    Args:
        directory: Directory to search.
        seconds: Time window in seconds.
        exclude_patterns: Patterns to exclude (e.g., [".icloud", ".DS_Store"]).
        
    Returns:
        List of recently modified file paths.
    """
    directory = Path(directory).expanduser().resolve()
    exclude_patterns = exclude_patterns or [".icloud", ".DS_Store"]
    
    if not directory.exists():
        return []
    
    cutoff_time = datetime.now() - timedelta(seconds=seconds)
    recent_files: list[Path] = []
    
    try:
        for file_path in directory.rglob("*"):
            if not file_path.is_file():
                continue
            
            # Check exclusion patterns
            if any(pattern in file_path.name for pattern in exclude_patterns):
                continue
            
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime > cutoff_time:
                    recent_files.append(file_path)
            except OSError:
                # Skip files we can't stat
                continue
    except OSError:
        # Directory access error
        pass
    
    return recent_files


def wait_for_icloud_sync(
    source_dir: Path,
    max_wait_seconds: int = 60,
    check_interval: float = 2.0,
    stability_threshold: int = 2,
    download_dataless: bool = True,
) -> bool:
    """Wait for iCloud to finish syncing files.
    
    This function checks for three conditions:
    1. No .icloud placeholder files (all files downloaded - legacy format)
    2. No dataless files (all files downloaded - modern format)
    3. No recently modified files (sync activity has stopped)
    
    If dataless files are found, it will attempt to trigger their download
    from iCloud before proceeding.
    
    Args:
        source_dir: Source directory to monitor.
        max_wait_seconds: Maximum time to wait in seconds.
        check_interval: Time between checks in seconds.
        stability_threshold: Number of consecutive stable checks required.
        download_dataless: Whether to automatically download dataless files.
        
    Returns:
        True if sync completed within timeout, False if timed out.
    """
    logger = get_logger()
    source_dir = Path(source_dir).expanduser().resolve()
    
    logger.info("⏳ Checking iCloud sync status...")
    
    start_time = time.time()
    stable_count = 0
    dataless_download_attempted = False
    
    while True:
        elapsed = time.time() - start_time
        
        if elapsed >= max_wait_seconds:
            logger.warning(
                f"⚠️ Timeout after {max_wait_seconds}s waiting for iCloud sync. "
                "Proceeding anyway."
            )
            return False
        
        # Check for .icloud placeholder files (legacy format)
        placeholders = find_icloud_placeholders(source_dir)
        if placeholders:
            logger.info(
                f"   Waiting for iCloud downloads... "
                f"({len(placeholders)} .icloud files pending, {elapsed:.0f}s elapsed)"
            )
            stable_count = 0
            time.sleep(check_interval)
            continue
        
        # Check for dataless files (modern format)
        dataless_files = find_dataless_files(source_dir)
        if dataless_files:
            if download_dataless and not dataless_download_attempted:
                # Attempt to download dataless files
                logger.info(
                    f"   Found {len(dataless_files)} dataless files, "
                    "triggering iCloud download..."
                )
                download_dataless_files(source_dir)
                dataless_download_attempted = True
                stable_count = 0
                time.sleep(check_interval)
                continue
            else:
                # Already attempted download or download disabled
                remaining = find_dataless_files(source_dir)
                if remaining:
                    logger.warning(
                        f"⚠️ {len(remaining)} dataless files could not be downloaded. "
                        "These may cause rsync errors."
                    )
                    # Don't block forever on dataless files, just warn
                    # Fall through to stability check
        
        # Check for recently modified files
        recent_files = find_recently_modified_files(source_dir, seconds=5)
        if recent_files:
            logger.info(
                f"   Waiting for file stability... "
                f"({len(recent_files)} files recently modified)"
            )
            stable_count = 0
            time.sleep(check_interval)
            continue
        
        # No pending files and no recent modifications
        stable_count += 1
        
        if stable_count >= stability_threshold:
            logger.info("✅ iCloud sync appears complete. Files are stable.")
            
            # Extra safety delay for file system to settle
            time.sleep(1)
            return True
        
        time.sleep(check_interval)
    
    return False
