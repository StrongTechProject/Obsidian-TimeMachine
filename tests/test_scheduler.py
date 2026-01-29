"""Tests for scheduler module."""

from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from ot.scheduler import (
    CronJob,
    _get_current_crontab,
    find_ot_cron_jobs,
    describe_schedule,
    SCHEDULE_PRESETS,
)


class TestCronJob:
    """Tests for CronJob dataclass."""
    
    def test_cron_job_creation(self) -> None:
        """Test creating a CronJob."""
        job = CronJob(
            schedule="*/15 * * * *",
            command="/usr/bin/ot sync",
            comment="Obsidian sync",
        )
        
        assert job.schedule == "*/15 * * * *"
        assert job.command == "/usr/bin/ot sync"
        assert job.comment == "Obsidian sync"
    
    def test_to_cron_line_with_comment(self) -> None:
        """Test converting to cron line with comment."""
        job = CronJob(
            schedule="0 * * * *",
            command="ot sync",
            comment="hourly sync",
        )
        
        line = job.to_cron_line()
        assert line == "0 * * * * ot sync # hourly sync"
    
    def test_to_cron_line_without_comment(self) -> None:
        """Test converting to cron line without comment."""
        job = CronJob(
            schedule="0 2 * * *",
            command="ot sync",
        )
        
        line = job.to_cron_line()
        assert line == "0 2 * * * ot sync"
    
    def test_from_cron_line_with_comment(self) -> None:
        """Test parsing a cron line with comment."""
        line = "*/30 * * * * /usr/bin/ot sync # auto backup"
        
        job = CronJob.from_cron_line(line)
        
        assert job is not None
        assert job.schedule == "*/30 * * * *"
        assert job.command == "/usr/bin/ot sync"
        assert job.comment == "auto backup"
    
    def test_from_cron_line_without_comment(self) -> None:
        """Test parsing a cron line without comment."""
        line = "0 9 * * * ot sync"
        
        job = CronJob.from_cron_line(line)
        
        assert job is not None
        assert job.schedule == "0 9 * * *"
        assert job.command == "ot sync"
        assert job.comment is None
    
    def test_from_cron_line_empty(self) -> None:
        """Test parsing empty line."""
        assert CronJob.from_cron_line("") is None
    
    def test_from_cron_line_comment_only(self) -> None:
        """Test parsing comment-only line."""
        assert CronJob.from_cron_line("# this is a comment") is None


class TestGetCurrentCrontab:
    """Tests for get_current_crontab function."""
    
    @patch("ot.scheduler.subprocess.run")
    def test_get_crontab_success(self, mock_run: MagicMock) -> None:
        """Test getting crontab successfully."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="*/15 * * * * ot sync\n",
        )
        
        result = _get_current_crontab()
        assert "ot sync" in result
    
    @patch("ot.scheduler.subprocess.run")
    def test_get_crontab_empty(self, mock_run: MagicMock) -> None:
        """Test when no crontab exists."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="no crontab for user",
        )
        
        result = _get_current_crontab()
        assert result == ""


class TestFindOTCronJobs:
    """Tests for find_ot_cron_jobs function."""
    
    @patch("ot.scheduler._get_current_crontab")
    def test_find_jobs_with_ot_sync(self, mock_crontab: MagicMock) -> None:
        """Test finding OT sync jobs."""
        mock_crontab.return_value = (
            "0 * * * * some-other-command\n"
            "*/15 * * * * /usr/bin/ot sync # OT backup\n"
            "0 2 * * * backup-script\n"
        )
        
        jobs = find_ot_cron_jobs()
        
        assert len(jobs) == 1
        assert "ot sync" in jobs[0].command
    
    @patch("ot.scheduler._get_current_crontab")
    def test_find_jobs_none(self, mock_crontab: MagicMock) -> None:
        """Test when no OT jobs exist."""
        mock_crontab.return_value = "0 * * * * other-command\n"
        
        jobs = find_ot_cron_jobs()
        assert jobs == []


class TestDescribeSchedule:
    """Tests for describe_schedule function."""
    
    def test_describe_15min(self) -> None:
        """Test describing 15min preset."""
        desc = describe_schedule(SCHEDULE_PRESETS["15min"])
        assert "15 minutes" in desc
    
    def test_describe_hourly(self) -> None:
        """Test describing hourly preset."""
        desc = describe_schedule(SCHEDULE_PRESETS["hourly"])
        assert "hour" in desc.lower()
    
    def test_describe_daily(self) -> None:
        """Test describing daily preset."""
        desc = describe_schedule(SCHEDULE_PRESETS["daily"])
        assert "2:00 AM" in desc or "Daily" in desc
    
    def test_describe_custom(self) -> None:
        """Test describing custom schedule returns the raw expression."""
        custom_schedule = "*/5 * * * *"
        desc = describe_schedule(custom_schedule)
        # Custom schedules that are not presets return the raw expression
        assert desc == custom_schedule


class TestSchedulePresets:
    """Tests for schedule presets."""
    
    def test_presets_exist(self) -> None:
        """Test that all expected presets exist."""
        assert "15min" in SCHEDULE_PRESETS
        assert "30min" in SCHEDULE_PRESETS
        assert "hourly" in SCHEDULE_PRESETS
        assert "daily" in SCHEDULE_PRESETS
    
    def test_presets_valid_cron(self) -> None:
        """Test that presets are valid cron expressions."""
        for name, expr in SCHEDULE_PRESETS.items():
            parts = expr.split()
            assert len(parts) == 5, f"Invalid cron expression for {name}"
