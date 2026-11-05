"""Execution environments, ported from mini-swe-agent.

Every action is one independent subprocess, so swapping local execution for a
container means swapping this class and nothing else.
"""

import logging
import os
import platform
import shlex
import signal
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from workshop.agent.exceptions import Submitted
from workshop.agent.serialize import config_as_dict, recursive_merge

SUBMIT_SENTINEL = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"


def check_finished(output: dict):
    """Raise Submitted if the output indicates task completion."""
    lines = output.get("output", "").lstrip().splitlines(keepends=True)
    if (
        lines
        and lines[0].strip() == SUBMIT_SENTINEL
        and output["returncode"] == 0
    ):
        submission = "".join(lines[1:])
        raise Submitted(
            {
                "role": "exit",
                "content": submission,
                "extra": {
                    "exit_status": "Submitted",
                    "submission": submission,
                },
            }
        )


def _exception_output(e: Exception) -> dict[str, Any]:
    raw_output = getattr(e, "output", None)
    raw_output = (
        raw_output.decode("utf-8", errors="replace")
        if isinstance(raw_output, bytes)
        else (raw_output or "")
    )
    return {
        "output": raw_output,
        "returncode": -1,
        "exception_info": (
            f"An error occurred while executing the command: {e}"
        ),
        "extra": {"exception_type": type(e).__name__, "exception": str(e)},
    }


@dataclass
class LocalEnvironmentConfig:
    cwd: str = ""
    env: dict[str, str] = field(default_factory=dict)
    timeout: int = 30


class LocalEnvironment:
    """Executes bash commands directly on the local machine. No isolation."""

    def __init__(
        self, *, config_class: type = LocalEnvironmentConfig, **kwargs
    ):
        self.config = config_class(**kwargs)

    def execute(
        self, action: dict, cwd: str = "", *, timeout: int | None = None
    ) -> dict[str, Any]:
        command = action.get("command", "")
        cwd = cwd or self.config.cwd or os.getcwd()
        try:
            result = _run(
                command,
                cwd,
                os.environ | self.config.env,
                timeout or self.config.timeout,
            )
            output = {
                "output": result.stdout,
                "returncode": result.returncode,
                "exception_info": "",
            }
        except Exception as e:
            output = _exception_output(e)
        check_finished(output)
        return output

    def get_template_vars(self, **kwargs) -> dict[str, Any]:
        return recursive_merge(
            config_as_dict(self.config),
            platform.uname()._asdict(),
            dict(os.environ),
            kwargs,
        )

    def serialize(self) -> dict:
        return {
            "info": {
                "config": {
                    "environment": config_as_dict(self.config),
                    "environment_type": (
                        f"{self.__class__.__module__}."
                        f"{self.__class__.__name__}"
                    ),
                }
            }
        }


def _run(
    command: str | list[str],
    cwd: str | None,
    env: dict[str, str] | None,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    """Run a command, killing its process group on timeout."""
    process = subprocess.Popen(
        command,
        shell=isinstance(command, str),
        text=True,
        cwd=cwd,
        env=env,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=os.name == "posix",
    )
    chunks = []
    size = 0
    truncated = False

    def drain():
        nonlocal size, truncated
        while chunk := process.stdout.read(8192):
            remaining = 50000 - size
            if remaining > 0:
                chunks.append(chunk[:remaining])
                size += min(len(chunk), remaining)
            if len(chunk) > remaining:
                truncated = True

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(
            process.pid, signal.SIGKILL
        ) if os.name == "posix" else process.kill()
        process.wait()
    reader.join(timeout=1 if timed_out else timeout)
    incomplete = reader.is_alive()
    stdout = "".join(chunks) + ("\n[output truncated]" if truncated else "")
    if incomplete:
        stdout += "\n[output incomplete: pipe still open]"
    if timed_out:
        raise subprocess.TimeoutExpired(command, timeout, output=stdout)
    return subprocess.CompletedProcess(
        command, process.returncode, stdout=stdout
    )


@dataclass
class DockerEnvironmentConfig:
    image: str = ""
    cwd: str = "/"
    env: dict[str, str] = field(default_factory=dict)
    forward_env: list[str] = field(default_factory=list)
    """Host environment variables to forward to the container, if set."""
    timeout: int = 30
    executable: str = "docker"
    run_args: list[str] = field(default_factory=lambda: ["--rm"])
    container_timeout: str = "2h"
    """Max duration to keep the container running; same format as sleep(1)."""
    pull_timeout: int = 120
    interpreter: list[str] = field(default_factory=lambda: ["bash", "-lc"])


class DockerEnvironment:
    """Execute bash commands in a Docker or Podman container."""

    def __init__(
        self,
        *,
        config_class: type = DockerEnvironmentConfig,
        logger: logging.Logger | None = None,
        **kwargs,
    ):
        self.logger = logger or logging.getLogger("workshop.agent.environment")
        self.container_id: str | None = None
        self.config = config_class(**kwargs)
        if not self.config.image:
            raise ValueError("DockerEnvironment requires an image")

    def _start_container(self):
        container_name = (
            getattr(self, "supervised_container_name", None)
            or f"workshop-agent-{uuid.uuid4().hex[:8]}"
        )
        cmd = [
            self.config.executable,
            "run",
            "-d",
            "--name",
            container_name,
            "-w",
            self.config.cwd,
            *self.config.run_args,
            self.config.image,
            "sleep",
            self.config.container_timeout,
        ]
        self.logger.debug(
            "Starting container with command: %s", shlex.join(cmd)
        )
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.config.pull_timeout,
            check=True,
        )
        self.container_id = result.stdout.strip()
        self.logger.info(
            "Started container %s with ID %s",
            container_name,
            self.container_id,
        )

    def execute(
        self, action: dict, cwd: str = "", *, timeout: int | None = None
    ) -> dict[str, Any]:
        command = action.get("command", "")
        cwd = cwd or self.config.cwd
        self.ensure_started()
        assert self.container_id, "Container not started"
        cmd = [self.config.executable, "exec", "-w", cwd]
        for key in self.config.forward_env:
            if (value := os.getenv(key)) is not None:
                cmd.extend(["-e", f"{key}={value}"])
        for key, value in self.config.env.items():
            cmd.extend(["-e", f"{key}={value}"])
        cmd.extend([self.container_id, *self.config.interpreter, command])
        try:
            result = _run(cmd, None, None, timeout or self.config.timeout)
            output = {
                "output": result.stdout,
                "returncode": result.returncode,
                "exception_info": "",
            }
        except Exception as e:
            output = _exception_output(e)
        check_finished(output)
        return output

    def get_template_vars(self, **kwargs) -> dict[str, Any]:
        return recursive_merge(
            config_as_dict(self.config), platform.uname()._asdict(), kwargs
        )

    def serialize(self) -> dict:
        return {
            "info": {
                "config": {
                    "environment": config_as_dict(self.config),
                    "environment_type": (
                        f"{self.__class__.__module__}."
                        f"{self.__class__.__name__}"
                    ),
                }
            }
        }

    def ensure_started(self):
        if self.container_id is None:
            self._start_container()

    def cleanup(self):
        if self.container_id is None:
            return
        container_id = self.container_id
        try:
            subprocess.run(
                [self.config.executable, "stop", container_id],
                capture_output=True,
                timeout=60,
                check=True,
            )
        except subprocess.SubprocessError, OSError:
            subprocess.run(
                [self.config.executable, "rm", "-f", container_id],
                capture_output=True,
                timeout=60,
                check=True,
            )
        self.container_id = None
