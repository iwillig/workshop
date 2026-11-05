import pytest

from workshop.agent.config import load_config, resolve_class
from workshop.agent.default_agent import DefaultAgent
from workshop.agent.environments import LocalEnvironment
from workshop.agent.interactive import InteractiveAgent
from workshop.config import load_workshop_config


def write_project(tmp_path, body):
    path = tmp_path / "workshop.yaml"
    path.write_text(
        "version: 1\ndefault_agent: test\nagents:\n  test:\n" + body
    )
    return path


def test_yaml_values_reach_dataclass_configs(tmp_path):
    path = write_project(
        tmp_path,
        """\
    agent: {agent_class: default, step_limit: 7}
    environment: {environment_class: local, cwd: /tmp, timeout: 5}
    model: {model_name: test-model, model_options: {temperature: 0}}
""",
    )
    config = load_config(path)
    assert config["agent"]["step_limit"] == 7
    assert config["environment"]["cwd"] == "/tmp"
    assert config["model"]["model_options"] == {"temperature": 0}


def test_obsolete_confirm_mode_is_rejected():
    with pytest.raises(ValueError, match="approval"):
        InteractiveAgent(None, None, mode="confirm")


def test_system_template_file_relative_to_config(tmp_path):
    (tmp_path / "system.txt").write_text("System for {{ task }}")
    path = write_project(tmp_path, "    prompts: {system_file: system.txt}\n")
    config = load_workshop_config(path)["agents"]["test"]
    assert config["agent"]["system_template"] == "System for {{ task }}"


def test_system_template_file_conflicts_with_inline(tmp_path):
    path = write_project(
        tmp_path, "    prompts: {system: inline, system_file: other}\n"
    )
    with pytest.raises(ValueError, match="Set only one"):
        load_workshop_config(path)


def test_missing_system_template_file(tmp_path):
    path = write_project(tmp_path, "    prompts: {system_file: missing.txt}\n")
    with pytest.raises(FileNotFoundError):
        load_workshop_config(path)


def test_resolve_class_dotted_path():
    assert (
        resolve_class("workshop.agent.default_agent.DefaultAgent", {})
        is DefaultAgent
    )


def test_resolve_class_unknown_name_raises():
    with pytest.raises(ValueError, match="Unknown class"):
        resolve_class("nope", {"local": LocalEnvironment})


def test_unknown_config_key_raises(tmp_path):
    path = write_project(tmp_path, "    environment: {not_a_field: 1}\n")
    with pytest.raises(ValueError, match="not_a_field"):
        load_workshop_config(path)


def test_standalone_agent_yaml_is_rejected(tmp_path):
    path = tmp_path / "agent.yaml"
    path.write_text("model: {model_name: test}\n")
    with pytest.raises(ValueError):
        load_config(path)
    path.write_text("agents: {test: {model: {model_name: example}}}\n")
    with pytest.raises(ValueError, match="version"):
        load_config(path, agent_name="test")
