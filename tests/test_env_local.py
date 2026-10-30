import os

from click.testing import CliRunner

from research_context import __main__ as research
from workshop.cli import cli


def test_loads_local_tokens_for_both_entry_points(tmp_path, monkeypatch):
    (tmp_path / ".env.local").write_text(
        "ASANA_ACCESS_TOKEN=asana-file\nNOTION_TOKEN=notion-file\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ASANA_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    runner = CliRunner()
    result = runner.invoke(cli, ["research-context", "asana", "--help"])
    assert result.exit_code == 0
    assert os.environ["ASANA_ACCESS_TOKEN"] == "asana-file"
    assert os.environ["NOTION_TOKEN"] == "notion-file"
    monkeypatch.delenv("ASANA_ACCESS_TOKEN")
    monkeypatch.delenv("NOTION_TOKEN")
    runner.invoke(research.cli, ["asana", "--help"])
    assert os.environ["ASANA_ACCESS_TOKEN"] == "asana-file"
    assert os.environ["NOTION_TOKEN"] == "notion-file"


def test_existing_environment_takes_precedence(tmp_path, monkeypatch):
    (tmp_path / ".env.local").write_text("NOTION_TOKEN=file-token\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NOTION_TOKEN", "environment-token")
    result = CliRunner().invoke(cli, ["research-context", "notion", "--help"])
    assert result.exit_code == 0
    assert os.environ["NOTION_TOKEN"] == "environment-token"
