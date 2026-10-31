import importlib
import subprocess
import sys


def test_agent_subsystem_packages_and_legacy_config_imports():
    config = importlib.import_module("workshop.agent_config")
    legacy = importlib.import_module("workshop.agent.config")
    assert config.load_config is legacy.load_config
    assert config.build_agent is legacy.build_agent
    assert config.DEFAULT_CONFIG_PATH.is_file()
    assert importlib.import_module("workshop.agent_benchmark")
    assert importlib.import_module("workshop.agent_eval")


def test_config_import_does_not_load_agent_runtime():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import workshop.agent_config, sys; assert 'workshop.agent' not in sys.modules",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_agent_runtime_does_not_load_config_package():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import workshop.agent, sys; assert 'workshop.agent_config' not in sys.modules",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_packaged_default_config_loads():
    from workshop.agent_config import DEFAULT_CONFIG_PATH, load_config

    config = load_config(DEFAULT_CONFIG_PATH)
    assert config["agent"]["agent_class"] == "interactive"
