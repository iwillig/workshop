from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from workshop.cli import cli
from workshop.config import load_workshop_config


@pytest.mark.parametrize(
    "body",
    [
        "agents: {x: {model: {typo: true}}}",
        "agents: {x: {environment: {timeout: bad}}}",
        "agents: {x: {model: {retry_attempts: 0}}}",
        "agents: {x: {tools: {read: {}}}}",
        "agents: {x: {model: {protocol: native}, "
        "mcp_servers: {a: {transport: stdio}}}}",
        "benchmark: {suite: not-a-suite}",
        "evaluation: {budget: -1}",
        "browser: {width: 0}",
    ],
)
def test_invalid_project_config(tmp_path, body):
    path = tmp_path / "workshop.yaml"
    path.write_text("version: 1\n" + body)
    with pytest.raises(ValueError):
        load_workshop_config(path)


@pytest.mark.parametrize(
    "command",
    [["agent", "run"], ["benchmark", "run"], ["eval", "review-trace"]],
)
def test_standalone_agent_config_option_is_not_supported(command):
    result = CliRunner().invoke(cli, [*command, "--config", "old.yaml"])
    assert result.exit_code != 0
    assert "--config" in result.output


def test_config_show_redacts_values(tmp_path):
    path = tmp_path / "workshop.yaml"
    path.write_text(
        "version: 1\nagents: {x: {model: {model_name: super-secret}}}"
    )
    result = CliRunner().invoke(
        cli, ["--workshop-config", str(path), "config", "show"]
    )
    assert result.exit_code == 0, result.output
    assert "super-secret" not in result.output
    assert "<redacted>" in result.output


def test_benchmark_uses_project_defaults_and_flags_override(
    tmp_path, monkeypatch
):
    config = tmp_path / "workshop.yaml"
    config.write_text("""\
version: 1
default_agent: coding
benchmark: {storage: runs, suite: coding-v1}
agents:
  coding:
    model: {model_name: fake}
""")
    seen = {}

    def run(suite, agent, name, storage, **kwargs):
        seen.update(suite=suite, agent=agent, name=name, storage=storage)
        return {"counts": {"infrastructure_error": 0}}

    monkeypatch.setattr("workshop.agent_benchmark.cli.run_suite", run)
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--workshop-config", str(config), "benchmark", "run", "--local"]
    )
    assert result.exit_code == 0, result.output
    assert seen["suite"] == "coding-v1"
    assert Path(seen["storage"]) == tmp_path / "runs"
    result = runner.invoke(
        cli,
        [
            "--workshop-config",
            str(config),
            "benchmark",
            "run",
            "--local",
            "--suite",
            "review-v1",
            "--storage",
            str(tmp_path / "other"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert seen["suite"] == "review-v1"
    assert Path(seen["storage"]) == tmp_path / "other"


def test_project_storage_used_by_read_commands(tmp_path, monkeypatch):
    path = tmp_path / "workshop.yaml"
    path.write_text("benchmark: {storage: runs}\n")
    seen = []
    monkeypatch.setattr(
        "workshop.agent_benchmark.cli.load_report",
        lambda root, run: seen.append(root) or {},
    )
    monkeypatch.setattr(
        "workshop.agent_eval.cli.load_proposals",
        lambda root: seen.append(root) or {},
    )
    runner = CliRunner()
    for args in (["benchmark", "report", "run"], ["eval", "proposals"]):
        result = runner.invoke(cli, ["--workshop-config", str(path), *args])
        assert result.exit_code == 0, result.output
    assert seen == [tmp_path / "runs", tmp_path / "runs"]


def test_project_agent_requires_explicit_model(tmp_path, monkeypatch):
    path = tmp_path / "workshop.yaml"
    path.write_text("version: 1\ndefault_agent: x\nagents: {x: {}}\n")
    monkeypatch.setattr(
        "workshop.agent.cli.build_agent",
        lambda config: SimpleNamespace(
            run=lambda _: {"exit_status": "Submitted"}
        ),
    )
    runner = CliRunner()
    result = runner.invoke(
        cli, ["--workshop-config", str(path), "agent", "run", "-t", "test"]
    )
    assert result.exit_code != 0
    assert "model_name" in result.output
    result = runner.invoke(
        cli,
        [
            "--workshop-config",
            str(path),
            "agent",
            "run",
            "--model",
            "fake",
            "-t",
            "test",
        ],
    )
    assert result.exit_code == 0, result.output
