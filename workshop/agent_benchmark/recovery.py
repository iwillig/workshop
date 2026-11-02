"""Narrow recovery for one explicitly identified diagnostic container."""

import hmac
import json
import re
import subprocess

from workshop.agent_benchmark.preflight import CheckState, preflight


def recover_probe(container_id, name, token, *, run=None):
    """Remove only the exact labelled crash diagnostic, after identity checks.

    This is not a general orphan scanner or production recovery mechanism.
    """
    if (
        not isinstance(container_id, str)
        or not re.fullmatch(r"[0-9a-f]{64}", container_id)
        or not isinstance(name, str)
        or not re.fullmatch(r"workshop-crash-[0-9a-f]{32}", name)
        or not isinstance(token, str)
        or not re.fullmatch(r"[0-9a-f]{32}", token)
    ):
        raise ValueError("invalid diagnostic container identity")
    runtime = preflight()
    for key in (
        "host_linux",
        "runtime_local",
        "runtime_available",
        "rootless",
    ):
        if runtime.checks.get(key) is not CheckState.PASS:
            return CheckState.UNVERIFIED
    run = run or subprocess.run
    try:
        result = run(
            ["podman", "inspect", container_id, "--format", "json"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0 or len(result.stdout) > 1000000:
            return CheckState.UNVERIFIED
        data = json.loads(result.stdout)
        if (
            not isinstance(data, list)
            or len(data) != 1
            or not isinstance(data[0], dict)
        ):
            return CheckState.UNVERIFIED
        obj = data[0]
        config = obj.get("Config")
        labels = config.get("Labels") if isinstance(config, dict) else None
        actual_token = (
            labels.get("io.workshop.probe")
            if isinstance(labels, dict)
            else None
        )
        if (
            obj.get("Id") != container_id
            or obj.get("Name") != name
            or not isinstance(actual_token, str)
            or not hmac.compare_digest(actual_token, token)
        ):
            return CheckState.UNVERIFIED
    except OSError, subprocess.SubprocessError, ValueError, TypeError:
        return CheckState.UNVERIFIED
    for command in (
        ["podman", "kill", "--signal", "KILL", container_id],
        ["podman", "rm", "-f", container_id],
    ):
        try:
            run(
                command,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except OSError, subprocess.SubprocessError:
            pass
    try:
        result = run(
            ["podman", "container", "exists", container_id],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 1:
            return CheckState.PASS
        if result.returncode == 0:
            return CheckState.FAIL
    except OSError, subprocess.SubprocessError:
        pass
    return CheckState.UNVERIFIED
