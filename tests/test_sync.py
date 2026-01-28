"""Tests for the sync module."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ot.sync import (
    RsyncExitCode,
    RsyncResult,
    build_rsync_command,
    check_rsync_available,
    check_rsync_iconv_support,
    run_rsync,
)


class TestCheckRsyncAvailable:
    """Tests for check_rsync_available function."""
    
    def test_rsync_available(self) -> None:
        """Test when rsync is available."""
        # This should pass on most systems
        result = check_rsync_available()
        # We can't assert True because rsync might not be installed
        assert isinstance(result, bool)


class TestBuildRsyncCommand:
    """Tests for build_rsync_command function."""
    
    def test_basic_command(self, tmp_path: Path) -> None:
        """Test building a basic rsync command."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        
        cmd = build_rsync_command(source, dest)
        
        assert cmd[0] == "rsync"
        assert "-av" in cmd
        assert "--progress" in cmd
        assert f"{source}/" in cmd
        assert str(dest) in cmd
    
    def test_exclude_patterns(self, tmp_path: Path) -> None:
        """Test that exclusions are added."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        
        cmd = build_rsync_command(source, dest)
        
        # Check default exclusions
        assert "--exclude" in cmd
        exclude_indices = [i for i, x in enumerate(cmd) if x == "--exclude"]
        exclusions = [cmd[i + 1] for i in exclude_indices]
        
        assert ".git" in exclusions
        assert ".DS_Store" in exclusions
    
    def test_custom_exclude_patterns(self, tmp_path: Path) -> None:
        """Test custom exclusion patterns."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        
        cmd = build_rsync_command(
            source, dest,
            exclude_patterns=["*.tmp", "cache/"],
        )
        
        exclude_indices = [i for i, x in enumerate(cmd) if x == "--exclude"]
        exclusions = [cmd[i + 1] for i in exclude_indices]
        
        assert "*.tmp" in exclusions
        assert "cache/" in exclusions
    
    def test_delete_flag(self, tmp_path: Path) -> None:
        """Test --delete flag."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        
        cmd = build_rsync_command(source, dest, delete=True)
        assert "--delete" in cmd
        
        cmd_no_delete = build_rsync_command(source, dest, delete=False)
        assert "--delete" not in cmd_no_delete
    
    def test_dry_run_flag(self, tmp_path: Path) -> None:
        """Test --dry-run flag."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        
        cmd = build_rsync_command(source, dest, dry_run=True)
        assert "--dry-run" in cmd
    
    def test_iconv_flag(self, tmp_path: Path) -> None:
        """Test iconv flag for macOS."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        
        cmd = build_rsync_command(source, dest, use_iconv=True)
        assert "--iconv=utf-8-mac,utf-8" in cmd


class TestRunRsync:
    """Tests for run_rsync function."""
    
    def test_run_rsync_success(self, tmp_path: Path) -> None:
        """Test successful rsync operation."""
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()
        
        # Create a test file
        test_file = source / "test.txt"
        test_file.write_text("test content")
        
        result = run_rsync(source, dest)
        
        # Check if rsync is available
        if not check_rsync_available():
            assert not result.success
            assert "not found" in result.stderr
        else:
            assert result.success
            assert (dest / "test.txt").exists()
    
    def test_run_rsync_missing_source(self, tmp_path: Path) -> None:
        """Test rsync with missing source directory."""
        source = tmp_path / "missing_source"
        dest = tmp_path / "dest"
        dest.mkdir()
        
        result = run_rsync(source, dest)
        
        # Rsync returns code 23 (partial transfer) for missing source
        # which we treat as partial success with a warning
        if check_rsync_available():
            assert result.exit_code == 23
            assert result.warning is not None
    
    @patch("ot.sync.check_rsync_available")
    def test_rsync_not_available(
        self,
        mock_check: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Test when rsync is not available."""
        mock_check.return_value = False
        
        source = tmp_path / "source"
        dest = tmp_path / "dest"
        source.mkdir()
        dest.mkdir()
        
        result = run_rsync(source, dest)
        
        assert not result.success
        assert "not found" in result.stderr


class TestRsyncResult:
    """Tests for RsyncResult dataclass."""
    
    def test_result_creation(self) -> None:
        """Test creating an RsyncResult."""
        result = RsyncResult(
            success=True,
            exit_code=0,
            stdout="output",
            stderr="",
        )
        
        assert result.success
        assert result.exit_code == 0
        assert result.warning is None
    
    def test_result_with_warning(self) -> None:
        """Test RsyncResult with warning."""
        result = RsyncResult(
            success=True,
            exit_code=24,
            stdout="output",
            stderr="",
            warning="Some files vanished",
        )
        
        assert result.success
        assert result.warning is not None
