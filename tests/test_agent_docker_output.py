import json
import sys

import pytest

from workshop.agent.environments import DockerEnvironment
from workshop.agent.exceptions import Submitted


@pytest.fixture
def docker_stub(tmp_path):
    script = tmp_path / "docker"
    marker = tmp_path / "events"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys, time\n"
        f"marker = {str(marker)!r}\n"
        "with open(marker, 'a') as f:\n"
        "    f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if sys.argv[1] == 'exec':\n"
        "    mode = sys.argv[-1]\n"
        "    if mode == 'large':\n"
        "        print('x' * 200000)\n"
        "    elif mode == 'timeout':\n"
        "        print('started', flush=True)\n"
        "        time.sleep(30)\n"
        "    elif mode == 'failure':\n"
        "        print('failed', file=sys.stderr)\n"
        "        sys.exit(7)\n"
        "    elif mode == 'submit':\n"
        "        print('COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT')\n"
        "        print('done')\n"
    )
    script.chmod(0o755)
    env = DockerEnvironment(image="test", executable=str(script), timeout=1)
    env.container_id = "container-test"
    return env, marker


def test_docker_large_output_is_bounded(docker_stub):
    env, _ = docker_stub
    result = env.execute({"command": "large"})
    assert result["returncode"] == 0
    assert len(result["output"]) < 50100
    assert "[output truncated]" in result["output"]


def test_docker_exec_preserves_arguments_and_exit_status(docker_stub):
    env, marker = docker_stub
    env.config.env = {"EXAMPLE": "a b;$(ignored)"}
    result = env.execute({"command": "failure"}, cwd="/work")
    assert result["returncode"] == 7
    assert "failed" in result["output"]
    args = json.loads(marker.read_text().splitlines()[0])
    assert args == [
        "exec",
        "-w",
        "/work",
        "-e",
        "EXAMPLE=a b;$(ignored)",
        "container-test",
        "bash",
        "-lc",
        "failure",
    ]


def test_docker_timeout_retains_partial_output_and_cleanup(docker_stub):
    env, marker = docker_stub
    result = env.execute({"command": "timeout"})
    assert result["returncode"] == -1
    assert result["extra"]["exception_type"] == "TimeoutExpired"
    assert "started" in result["output"]
    env.cleanup()
    calls = [json.loads(line) for line in marker.read_text().splitlines()]
    assert calls[-1] == ["stop", "container-test"]
    assert env.container_id is None


def test_docker_submission_sentinel(docker_stub):
    env, _ = docker_stub
    with pytest.raises(Submitted) as result:
        env.execute({"command": "submit"})
    assert result.value.messages[0]["extra"]["submission"] == "done\n"
