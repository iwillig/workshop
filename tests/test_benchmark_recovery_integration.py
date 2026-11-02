"""Opt-in disposable crash test; never runs an agent or scans containers."""

import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid

import pytest

from workshop.agent_benchmark.preflight import CheckState, preflight
from workshop.agent_benchmark.probe import PROBE_IMAGE
from workshop.agent_benchmark.recovery import recover_probe


@pytest.mark.skipif(
    os.environ.get("WORKSHOP_PODMAN_CRASH_TEST") != "1",
    reason="set WORKSHOP_PODMAN_CRASH_TEST=1 for disposable Podman test",
)
def test_controller_crash_recovers_only_its_diagnostic_container(tmp_path):
    runtime = preflight()
    for key in (
        "host_linux",
        "runtime_available",
        "runtime_local",
        "rootless",
    ):
        assert runtime.checks[key] is CheckState.PASS
    name = "workshop-crash-" + uuid.uuid4().hex
    token = uuid.uuid4().hex
    id_file = tmp_path / "container-id"
    controller = tmp_path / "controller.py"
    controller.write_text("""\
import pathlib, subprocess, sys, time
name, token, image, path = sys.argv[1:]
result = subprocess.run([
    "podman", "run", "-d", "--name", name, "--pull=never", "--network=none",
    "--read-only", "--cap-drop=all", "--security-opt=no-new-privileges",
    "--user=65534:65534", "--memory=512m", "--pids-limit=128", "--cpus=1",
    "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m",
    "--label=io.workshop.probe=" + token, "--entrypoint=/bin/sleep",
    image, "120"], capture_output=True, text=True, timeout=30, check=True)
pathlib.Path(path).write_text(result.stdout.strip())
time.sleep(120)
""")
    process = subprocess.Popen(
        [
            sys.executable,
            str(controller),
            name,
            token,
            PROBE_IMAGE,
            str(id_file),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    container_id = None
    try:
        deadline = time.monotonic() + 25
        while (
            not id_file.exists()
            and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.05)
        assert id_file.exists(), "controller did not create the container"
        container_id = id_file.read_text().strip()
        assert re.fullmatch(r"[0-9a-f]{64}", container_id)
        assert process.poll() is None
        process.kill()
        process.wait(timeout=5)
        assert process.returncode != 0
        exists = subprocess.run(
            ["podman", "container", "exists", container_id],
            capture_output=True,
            timeout=10,
            check=False,
        )
        assert exists.returncode == 0
        assert recover_probe(container_id, name, token) is CheckState.PASS
        assert (
            subprocess.run(
                ["podman", "container", "exists", container_id],
                capture_output=True,
                timeout=10,
                check=False,
            ).returncode
            == 1
        )
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        # Recover only this test's exact ID and label after a failure.
        if container_id is None:
            inspected = subprocess.run(
                ["podman", "inspect", name, "--format", "json"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if inspected.returncode == 0:
                try:
                    candidate = json.loads(inspected.stdout)[0]["Id"]
                    if re.fullmatch(r"[0-9a-f]{64}", candidate):
                        container_id = candidate
                except ValueError, KeyError, IndexError, TypeError:
                    pass
        if container_id:
            exists = subprocess.run(
                ["podman", "container", "exists", container_id],
                capture_output=True,
                timeout=10,
                check=False,
            )
            if exists.returncode == 0:
                assert (
                    recover_probe(container_id, name, token) is CheckState.PASS
                )
