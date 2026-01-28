"""
Git operations for Obsidian Timemachine.

Provides functions for Git repository management, including
fetch, merge, commit, and push operations.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .logger import get_logger


@dataclass
class GitResult:
    """Result of a Git operation.
    
    Attributes:
        success: Whether the operation succeeded.
        output: Combined stdout output.
        error: Error message if failed.
        exit_code: Git command exit code.
    """
    success: bool
    output: str
    error: str
    exit_code: int


class GitError(Exception):
    """Raised when a Git operation fails."""
    
    def __init__(self, message: str, result: GitResult | None = None):
        self.result = result
        super().__init__(message)


def check_git_available() -> bool:
    """Check if git is available on the system.
    
    Returns:
        True if git is found, False otherwise.
    """
    return shutil.which("git") is not None


def _run_git(
    args: list[str],
    cwd: Path,
    ssh_key_path: Path | None = None,
    timeout: int | None = 60,
) -> GitResult:
    """Execute a git command.
    
    Args:
        args: Git command arguments (without 'git' prefix).
        cwd: Working directory for the command.
        ssh_key_path: Path to SSH private key for authentication.
        timeout: Command timeout in seconds.
        
    Returns:
        GitResult with operation status and output.
    """
    cmd = ["git"] + args
    
    env = os.environ.copy()
    
    # Configure SSH command if key path is provided
    if ssh_key_path:
        ssh_key_path = Path(ssh_key_path).expanduser().resolve()
        env["GIT_SSH_COMMAND"] = f"ssh -i {ssh_key_path} -o IdentitiesOnly=yes"
    
    # Ensure consistent locale
    env["LC_ALL"] = "en_US.UTF-8"
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
        
        return GitResult(
            success=result.returncode == 0,
            output=result.stdout,
            error=result.stderr,
            exit_code=result.returncode,
        )
    
    except subprocess.TimeoutExpired:
        return GitResult(
            success=False,
            output="",
            error=f"Git command timed out after {timeout}s",
            exit_code=-1,
        )
    
    except OSError as e:
        return GitResult(
            success=False,
            output="",
            error=str(e),
            exit_code=-1,
        )


def is_git_repo(path: Path) -> bool:
    """Check if a directory is a Git repository.
    
    Args:
        path: Directory path to check.
        
    Returns:
        True if the directory contains a .git directory.
    """
    path = Path(path).expanduser().resolve()
    return (path / ".git").is_dir()


def init_repo(path: Path) -> GitResult:
    """Initialize a new Git repository.
    
    Args:
        path: Directory to initialize.
        
    Returns:
        GitResult with operation status.
    """
    logger = get_logger()
    path = Path(path).expanduser().resolve()
    
    logger.info(f"Initializing Git repository in {path}")
    
    result = _run_git(["init"], cwd=path)
    
    if result.success:
        # Set default branch to main
        _run_git(["branch", "-M", "main"], cwd=path)
        # Disable quoted paths for Unicode filenames
        _run_git(["config", "core.quotepath", "false"], cwd=path)
        logger.info("✅ Git repository initialized.")
    else:
        logger.error(f"❌ Failed to initialize repository: {result.error}")
    
    return result


def get_current_branch(repo_path: Path) -> str | None:
    """Get the current Git branch name.
    
    Args:
        repo_path: Path to the Git repository.
        
    Returns:
        Branch name, or None if detection fails.
    """
    result = _run_git(["branch", "--show-current"], cwd=repo_path)
    
    if result.success and result.output.strip():
        return result.output.strip()
    
    # Fallback: try to get from HEAD
    result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
    
    if result.success and result.output.strip():
        return result.output.strip()
    
    return None


def get_remote_url(repo_path: Path, remote: str = "origin") -> str | None:
    """Get the URL of a remote repository.
    
    Args:
        repo_path: Path to the Git repository.
        remote: Remote name (default: "origin").
        
    Returns:
        Remote URL, or None if not configured.
    """
    result = _run_git(["remote", "get-url", remote], cwd=repo_path)
    
    if result.success:
        return result.output.strip()
    
    return None


def set_remote_url(
    repo_path: Path,
    url: str,
    remote: str = "origin",
) -> GitResult:
    """Set or update a remote repository URL.
    
    Args:
        repo_path: Path to the Git repository.
        url: Remote URL to set.
        remote: Remote name (default: "origin").
        
    Returns:
        GitResult with operation status.
    """
    # Check if remote exists
    existing_url = get_remote_url(repo_path, remote)
    
    if existing_url is None:
        # Add new remote
        return _run_git(["remote", "add", remote, url], cwd=repo_path)
    else:
        # Update existing remote
        return _run_git(["remote", "set-url", remote, url], cwd=repo_path)


def has_commits(repo_path: Path) -> bool:
    """Check if the repository has any commits.
    
    Args:
        repo_path: Path to the Git repository.
        
    Returns:
        True if there are commits, False otherwise.
    """
    result = _run_git(["rev-parse", "HEAD"], cwd=repo_path)
    return result.success


def has_changes(repo_path: Path) -> bool:
    """Check if there are uncommitted changes.
    
    Args:
        repo_path: Path to the Git repository.
        
    Returns:
        True if there are changes, False otherwise.
    """
    result = _run_git(["status", "-s"], cwd=repo_path)
    return result.success and bool(result.output.strip())


def fetch(
    repo_path: Path,
    remote: str = "origin",
    branch: str | None = None,
    ssh_key_path: Path | None = None,
) -> GitResult:
    """Fetch updates from remote repository.
    
    Args:
        repo_path: Path to the Git repository.
        remote: Remote name.
        branch: Branch to fetch (optional).
        ssh_key_path: SSH key for authentication.
        
    Returns:
        GitResult with operation status.
    """
    logger = get_logger()
    logger.info("🔄 Fetching remote updates...")
    
    args = ["fetch", remote]
    if branch:
        args.append(branch)
    
    result = _run_git(
        args,
        cwd=repo_path,
        ssh_key_path=ssh_key_path,
        timeout=120,
    )
    
    if result.success:
        logger.info("✅ Fetch completed.")
    else:
        logger.warning(f"⚠️ Fetch failed: {result.error}")
    
    return result


def merge(
    repo_path: Path,
    ref: str,
) -> GitResult:
    """Merge a reference into the current branch.
    
    Args:
        repo_path: Path to the Git repository.
        ref: Reference to merge (e.g., "origin/main").
        
    Returns:
        GitResult with operation status.
    """
    logger = get_logger()
    logger.info(f"🔀 Merging {ref}...")
    
    result = _run_git(["merge", ref], cwd=repo_path)
    
    if result.success:
        logger.info("✅ Merge completed.")
    else:
        # Check for merge conflicts
        status_result = _run_git(["status"], cwd=repo_path)
        if "Unmerged paths" in status_result.output or "both modified" in status_result.output:
            logger.error("❌ Merge conflict detected! Manual resolution required.")
            # Abort the merge to leave repo in clean state
            _run_git(["merge", "--abort"], cwd=repo_path)
        else:
            logger.warning(f"⚠️ Merge failed: {result.error}")
    
    return result


def pull(
    repo_path: Path,
    remote: str = "origin",
    branch: str | None = None,
    ssh_key_path: Path | None = None,
) -> GitResult:
    """Pull updates from remote (fetch + merge).
    
    Args:
        repo_path: Path to the Git repository.
        remote: Remote name.
        branch: Branch to pull.
        ssh_key_path: SSH key for authentication.
        
    Returns:
        GitResult with operation status.
    """
    logger = get_logger()
    
    # Detect current branch if not specified
    if branch is None:
        branch = get_current_branch(repo_path) or "main"
    
    logger.info(f"🔄 Pulling from {remote}/{branch}...")
    
    # First fetch
    fetch_result = fetch(repo_path, remote, branch, ssh_key_path)
    
    if not fetch_result.success:
        logger.warning("⚠️ Fetch failed; proceeding with local sync only.")
        return fetch_result
    
    # Check if we're up to date
    local_result = _run_git(["rev-parse", "HEAD"], cwd=repo_path)
    remote_result = _run_git(["rev-parse", f"{remote}/{branch}"], cwd=repo_path)
    
    if not local_result.success:
        # No local commits yet, skip merge
        logger.info("No local commits yet; skipping merge.")
        return GitResult(success=True, output="", error="", exit_code=0)
    
    if not remote_result.success:
        # Remote branch doesn't exist yet
        logger.info("Remote branch doesn't exist yet; skipping merge.")
        return GitResult(success=True, output="", error="", exit_code=0)
    
    local_commit = local_result.output.strip()
    remote_commit = remote_result.output.strip()
    
    if local_commit == remote_commit:
        logger.info("✅ Already up-to-date with remote.")
        return GitResult(success=True, output="Already up-to-date", error="", exit_code=0)
    
    # Merge remote changes
    return merge(repo_path, f"{remote}/{branch}")


def add_all(repo_path: Path) -> GitResult:
    """Stage all changes for commit.
    
    Args:
        repo_path: Path to the Git repository.
        
    Returns:
        GitResult with operation status.
    """
    return _run_git(["add", "."], cwd=repo_path)


def commit(
    repo_path: Path,
    message: str,
) -> GitResult:
    """Commit staged changes.
    
    Args:
        repo_path: Path to the Git repository.
        message: Commit message.
        
    Returns:
        GitResult with operation status.
    """
    logger = get_logger()
    logger.info("📝 Committing changes...")
    
    result = _run_git(["commit", "-m", message], cwd=repo_path)
    
    if result.success:
        logger.info("✅ Commit successful.")
    else:
        logger.error(f"❌ Commit failed: {result.error}")
    
    return result


def push(
    repo_path: Path,
    remote: str = "origin",
    branch: str | None = None,
    ssh_key_path: Path | None = None,
    set_upstream: bool = False,
) -> GitResult:
    """Push commits to remote repository.
    
    Args:
        repo_path: Path to the Git repository.
        remote: Remote name.
        branch: Branch to push.
        ssh_key_path: SSH key for authentication.
        set_upstream: Whether to set upstream tracking.
        
    Returns:
        GitResult with operation status.
    """
    logger = get_logger()
    
    # Detect current branch if not specified
    if branch is None:
        branch = get_current_branch(repo_path) or "main"
    
    logger.info(f"🚀 Pushing to {remote}/{branch}...")
    
    args = ["push", remote, branch]
    if set_upstream:
        args.insert(1, "-u")
    
    result = _run_git(
        args,
        cwd=repo_path,
        ssh_key_path=ssh_key_path,
        timeout=120,
    )
    
    if result.success:
        logger.info("✅ Push successful.")
    else:
        logger.error(f"❌ Push failed: {result.error}")
    
    return result


def commit_and_push(
    repo_path: Path,
    message: str | None = None,
    remote: str = "origin",
    branch: str | None = None,
    ssh_key_path: Path | None = None,
) -> GitResult:
    """Stage, commit, and push all changes.
    
    Args:
        repo_path: Path to the Git repository.
        message: Commit message (auto-generated if None).
        remote: Remote name.
        branch: Branch to push.
        ssh_key_path: SSH key for authentication.
        
    Returns:
        GitResult with operation status.
    """
    logger = get_logger()
    
    # Check for changes
    if not has_changes(repo_path):
        logger.info("☕ No changes to commit.")
        return GitResult(success=True, output="No changes", error="", exit_code=0)
    
    logger.info("📝 Changes detected; preparing to commit...")
    
    # Stage all changes
    add_result = add_all(repo_path)
    if not add_result.success:
        return add_result
    
    # Generate commit message if not provided
    if message is None:
        from datetime import datetime
        message = f"Auto-save: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    # Commit
    commit_result = commit(repo_path, message)
    if not commit_result.success:
        return commit_result
    
    # Push
    # Determine if this is the first push (set upstream)
    is_first_push = not has_commits(repo_path) or get_remote_url(repo_path) is None
    
    return push(
        repo_path,
        remote=remote,
        branch=branch,
        ssh_key_path=ssh_key_path,
        set_upstream=is_first_push,
    )
