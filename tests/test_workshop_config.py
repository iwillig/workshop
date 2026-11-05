import pytest
from click.testing import CliRunner

from workshop.config import load_workshop_config


def test_discovery_uses_nearest_config_and_resolves_database(tmp_path):
    (tmp_path / "workshop.yaml").write_text(
        "llm:\n  logging:\n    enabled: true\n    database: private/logs.db\n"
    )
    child = tmp_path / "child"
    child.mkdir()
    config = load_workshop_config(cwd=child)
    assert config["llm"]["logging"]["database"] == str(
        tmp_path / "private/logs.db"
    )
    (child / "workshop.yaml").write_text("{}")
    assert (
        load_workshop_config(cwd=child)["llm"]["logging"]["enabled"] is False
    )


def test_explicit_config_overrides_discovery(tmp_path):
    (tmp_path / "workshop.yaml").write_text("{}")
    other = tmp_path / "other.yaml"
    other.write_text(
        "llm:\n  logging:\n    enabled: true\n    database: logs.db\n"
    )
    assert load_workshop_config(path=other, cwd=tmp_path)["llm"]["logging"][
        "enabled"
    ]


@pytest.mark.parametrize(
    "content",
    [
        "[]",
        "unknown: 1",
        "llm: {logging: {enabled: true}}",
        "llm: {logging: {enabled: 'yes'}}",
        "llm: {logging: {enabled: false, unknown: 1}}",
    ],
)
def test_invalid_workshop_config_is_rejected(tmp_path, content):
    path = tmp_path / "workshop.yaml"
    path.write_text(content)
    with pytest.raises(ValueError):
        load_workshop_config(path=path)


def test_cli_core_config_passes_logging_to_agent(tmp_path, monkeypatch):
    from workshop.cli import cli
    from types import SimpleNamespace

    path = tmp_path / "workshop.yaml"
    path.write_text(
        "llm:\n  logging:\n    enabled: true\n    database: logs.db\n"
        "version: 1\ndefault_agent: test\nagents:\n  test:\n"
        "    model: {model_name: fake}\n"
    )
    seen = {}

    def build(config):
        seen.update(config)
        return SimpleNamespace(
            run=lambda task: {"exit_status": "Submitted", "submission": "done"}
        )

    monkeypatch.setattr("workshop.agent.cli.build_agent", build)
    result = CliRunner().invoke(
        cli, ["--workshop-config", str(path), "agent", "run", "--task", "test"]
    )
    assert result.exit_code == 0, result.output
    assert seen["workshop"]["llm"]["logging"]["database"] == str(
        tmp_path / "logs.db"
    )
