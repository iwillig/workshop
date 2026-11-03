import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("just") is None, reason="just is required")
def test_wake_endpoint_uses_hf_token_and_temporary_config(tmp_path):
    home = tmp_path / "home"
    config = home / ".config" / "io.datasette.llm"
    config.mkdir(parents=True)
    (config / "extra-openai-models.yaml").write_text("- model_id: hf-qwen\n")
    tools = tmp_path / "tools"
    tools.mkdir()
    prefix = tmp_path / "prefix"
    (prefix / "bin").mkdir(parents=True)
    brew = tools / "brew"
    brew.write_text(f"#!/bin/sh\nprintf '%s\\n' '{prefix}'\n")
    brew.chmod(0o755)
    pipenv = prefix / "bin" / "pipenv"
    pipenv.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "p = pathlib.Path(os.environ['LLM_USER_PATH'])\n"
        "assert (p / 'extra-openai-models.yaml').is_file()\n"
        "assert os.environ['OPENAI_API_KEY'] == 'test-token'\n"
        "print(json.dumps({'args': sys.argv[1:], 'config': str(p)}))\n"
    )
    pipenv.chmod(0o755)
    env = os.environ | {
        "HOME": str(home),
        "HF_TOKEN": "test-token",
        "PATH": str(tools) + os.pathsep + os.environ["PATH"],
    }
    result = subprocess.run(
        ["just", "wake-qwen"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["args"] == ["run", "llm", "-m", "hf-qwen", "Reply with OK."]
    assert not Path(data["config"]).exists()


@pytest.mark.skipif(shutil.which("just") is None, reason="just is required")
def test_wake_endpoint_requires_hf_token():
    env = os.environ.copy()
    env.pop("HF_TOKEN", None)
    result = subprocess.run(
        ["just", "wake-qwen"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert "HF_TOKEN" in result.stderr
