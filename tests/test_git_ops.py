"""Tests for the Git operations module."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ot.git_ops import (
    GitResult,
    add_all,
    check_git_available,
    commit,
    get_current_branch,
    get_remote_url,
    has_changes,
    has_commits,
    init_repo,
    is_git_repo,
    set_remote_url,
)


class TestCheckGitAvailable:
    """Tests for check_git_available function."""
    
    def test_git_available(self) -> None:
        """Test when git is available."""
        result = check_git_available()
        # Git should be available on most dev machines
        assert isinstance(result, bool)


class TestIsGitRepo:
    """Tests for is_git_repo function."""
    
    def test_is_git_repo_true(self, tmp_path: Path) -> None:
        """Test with a valid Git repository."""
        # Initialize a git repo
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        
        assert is_git_repo(tmp_path)
    
    def test_is_git_repo_false(self, tmp_path: Path) -> None:
        """Test with a non-Git directory."""
        assert not is_git_repo(tmp_path)


class TestInitRepo:
    """Tests for init_repo function."""
    
    def test_init_repo(self, tmp_path: Path) -> None:
        """Test initializing a Git repository."""
        result = init_repo(tmp_path)
        
        assert result.success
        assert is_git_repo(tmp_path)
    
    def test_init_sets_main_branch(self, tmp_path: Path) -> None:
        """Test that init sets main as default branch."""
        init_repo(tmp_path)
        
        # Create a commit to establish the branch
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
            env={"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@test.com",
                 "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@test.com"},
        )
        
        branch = get_current_branch(tmp_path)
        assert branch == "main"


class TestGetCurrentBranch:
    """Tests for get_current_branch function."""
    
    def test_get_current_branch(self, tmp_path: Path) -> None:
        """Test getting current branch name."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=tmp_path, capture_output=True)
        
        # Create initial commit
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
            env={"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@test.com",
                 "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@test.com"},
        )
        
        branch = get_current_branch(tmp_path)
        assert branch == "main"


class TestHasChanges:
    """Tests for has_changes function."""
    
    def test_has_changes_true(self, tmp_path: Path) -> None:
        """Test detecting uncommitted changes."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        
        # Create an untracked file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        
        assert has_changes(tmp_path)
    
    def test_has_changes_false(self, tmp_path: Path) -> None:
        """Test with no changes."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        
        # No files, no changes
        assert not has_changes(tmp_path)


class TestHasCommits:
    """Tests for has_commits function."""
    
    def test_has_commits_false(self, tmp_path: Path) -> None:
        """Test with no commits."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        
        assert not has_commits(tmp_path)
    
    def test_has_commits_true(self, tmp_path: Path) -> None:
        """Test with commits."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=tmp_path,
            capture_output=True,
            env={"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@test.com",
                 "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@test.com"},
        )
        
        assert has_commits(tmp_path)


class TestRemoteOperations:
    """Tests for remote URL operations."""
    
    def test_get_remote_url_none(self, tmp_path: Path) -> None:
        """Test getting remote when none is configured."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        
        url = get_remote_url(tmp_path)
        assert url is None
    
    def test_set_and_get_remote_url(self, tmp_path: Path) -> None:
        """Test setting and getting remote URL."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        
        test_url = "git@github.com:test/repo.git"
        result = set_remote_url(tmp_path, test_url)
        
        assert result.success
        
        url = get_remote_url(tmp_path)
        assert url == test_url


class TestCommitOperations:
    """Tests for commit operations."""
    
    def test_add_all(self, tmp_path: Path) -> None:
        """Test staging all changes."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        
        result = add_all(tmp_path)
        
        assert result.success
    
    def test_commit(self, tmp_path: Path) -> None:
        """Test committing changes."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        
        # Configure git user for this repo
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )
        
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        
        add_all(tmp_path)
        result = commit(tmp_path, "Test commit")
        
        assert result.success
        assert has_commits(tmp_path)


class TestGitResult:
    """Tests for GitResult dataclass."""
    
    def test_result_creation(self) -> None:
        """Test creating a GitResult."""
        result = GitResult(
            success=True,
            output="output",
            error="",
            exit_code=0,
        )
        
        assert result.success
        assert result.exit_code == 0
