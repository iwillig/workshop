from click.testing import CliRunner
from types import SimpleNamespace

from workshop.cli import cli
from workshop.config import load_workshop_config


def test_project_agent_and_relative_prompt(tmp_path, monkeypatch):
    (tmp_path / "prompt.md").write_text("Project instructions")
    config = tmp_path / "workshop.yaml"
    config.write_text(
        "version: 1\ndefault_agent: coding\nagents:\n  coding:\n"
        "    prompts: {system_file: prompt.md}\n"
        "    model: {model_name: example}\n"
    )
    seen = {}

    def build(value):
        seen.update(value)
        return SimpleNamespace(run=lambda task: {"exit_status": "Submitted"})

    monkeypatch.setattr("workshop.agent.cli.build_agent", build)
    result = CliRunner().invoke(
        cli, ["--workshop-config", str(config), "agent", "run", "-t", "task"]
    )
    assert result.exit_code == 0, result.output
    assert seen["agent"]["system_template"] == "Project instructions"
    assert seen["model"]["model_name"] == "example"


def test_benchmark_storage_relative_to_project(tmp_path):
    config = tmp_path / "workshop.yaml"
    config.write_text("benchmark: {storage: private/runs}\n")
    result = load_workshop_config(config)
    assert result["benchmark"]["storage"] == str(tmp_path / "private/runs")


def test_invalid_default_agent_rejected(tmp_path):
    config = tmp_path / "workshop.yaml"
    config.write_text("version: 1\ndefault_agent: missing\nagents: {}\n")
    result = CliRunner().invoke(
        cli, ["--workshop-config", str(config), "config", "validate"]
    )
    assert result.exit_code != 0
    assert "default_agent" in result.output
