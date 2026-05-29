"""Tests for CLI commands."""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock

from nowcasting_toolbox.cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


def test_cli_help(runner):
    """CLI should show help without error."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Nowcasting Toolbox" in result.output


def test_cli_fetch_help(runner):
    """fetch command should show help."""
    result = runner.invoke(cli, ["fetch", "--help"])
    assert result.exit_code == 0


def test_cli_run_help(runner):
    """run command should show help."""
    result = runner.invoke(cli, ["run", "--help"])
    assert result.exit_code == 0


def test_cli_backtest_help(runner):
    """backtest command should show help."""
    result = runner.invoke(cli, ["backtest", "--help"])
    assert result.exit_code == 0


def test_cli_leaderboard_no_file(runner, tmp_path):
    """leaderboard command should handle missing file gracefully."""
    import os
    os.chdir(tmp_path)
    result = runner.invoke(cli, ["leaderboard"])
    assert result.exit_code == 0
    assert "No leaderboard found" in result.output


def test_cli_config_template(runner, tmp_path):
    """config-template should generate a JSON file."""
    import os
    import json
    os.chdir(tmp_path)
    result = runner.invoke(cli, ["config-template"])
    assert result.exit_code == 0
    assert (tmp_path / "config_example.json").exists()

    # Verify it's valid JSON
    with open(tmp_path / "config_example.json") as f:
        cfg = json.load(f)
    assert "dfm" in cfg
    assert "bvar" in cfg
    assert "beq" in cfg


def test_cli_verbose_flag(runner):
    """--verbose flag should be accepted."""
    result = runner.invoke(cli, ["--verbose", "--help"])
    assert result.exit_code == 0


def test_cli_config_flag(runner, tmp_path):
    """--config flag should load config file."""
    import json
    cfg = {"startyear": 2020, "startmonth": 1}
    cfg_path = tmp_path / "test_config.json"
    cfg_path.write_text(json.dumps(cfg))

    result = runner.invoke(cli, ["--config", str(cfg_path), "--help"])
    assert result.exit_code == 0


def test_cli_schedule_help(runner):
    """schedule command should show help."""
    result = runner.invoke(cli, ["schedule", "--help"])
    assert result.exit_code == 0


def test_cli_select_vars_help(runner):
    """select-vars command should show help."""
    result = runner.invoke(cli, ["select-vars", "--help"])
    assert result.exit_code == 0


def test_cli_news_help(runner):
    """news command should show help."""
    result = runner.invoke(cli, ["news", "--help"])
    assert result.exit_code == 0
