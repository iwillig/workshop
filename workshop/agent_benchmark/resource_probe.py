"""Fixed memory and inode diagnostics; never run benchmark workloads."""

import json
import subprocess
import uuid

from workshop.agent_benchmark.preflight import (
    CheckState,
    PreflightReport,
    preflight,
)
from workshop.agent_benchmark.probe import PROBE_IMAGE


_MEMORY_SCRIPT = r"""
printf 'memory_max=%s\n' "$(cat /sys/fs/cgroup/memory.max)"
exec dd if=/dev/zero of=/tmp/workshop-memory bs=1048576 count=128
"""

_INODE_SCRIPT = r"""
export LC_ALL=C
printf 'inode_total=%s\n' "$(stat -f -c %c /tmp)"
i=0
while [ "$i" -lt 200 ]; do
  output=$( { : > "/tmp/workshop-inode-$i"; } 2>&1)
  code=$?
  if [ "$code" -ne 0 ]; then
    if printf '%s' "$output" | grep -q 'No space left on device'; then
      printf 'inode_result=enforced\n'
    else printf 'inode_result=inconclusive\n'; fi
    exit 0
  fi
  i=$((i + 1))
done
printf 'inode_result=not_enforced\n'
"""


def run_memory_probe(*, run=None, runtime=None):
    """Apply bounded memory pressure and inspect runtime OOM evidence."""
    return _run("memory", run=run, runtime=runtime)


def run_inode_probe(*, run=None, runtime=None):
    """Exercise a small, disposable tmpfs inode quota."""
    return _run("inode", run=run, runtime=runtime)


def _run(kind, *, run, runtime):
    run = run or subprocess.run
    runtime = runtime or preflight(run=run)
    result_key = "memory_oom" if kind == "memory" else "inode_limit"
    checks = {
        name: CheckState.UNVERIFIED
        for name in (
            "runtime_preflight",
            "probe_execution",
            result_key,
            "cleanup",
        )
    }
    required = (
        "host_linux",
        "runtime_available",
        "runtime_local",
        "rootless",
        "seccomp_available",
        "cgroups_v2",
        "resource_controllers",
    )
    if any(runtime.checks.get(key) is not CheckState.PASS for key in required):
        checks["runtime_preflight"] = CheckState.FAIL
        return PreflightReport(checks)
    checks["runtime_preflight"] = CheckState.PASS
    name = "workshop-resource-" + uuid.uuid4().hex
    memory = (
        ["--memory=64m", "--memory-swap=64m"]
        if kind == "memory"
        else ["--memory=512m"]
    )
    tmpfs = (
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=128m"
        if kind == "memory"
        else "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m,nr_inodes=128"
    )
    command = [
        "podman",
        "run",
        "--name",
        name,
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=all",
        "--security-opt=no-new-privileges",
        "--user=65534:65534",
        *memory,
        "--pids-limit=128",
        "--cpus=1",
        tmpfs,
        "--entrypoint=/bin/sh",
        PROBE_IMAGE,
        "-c",
        _MEMORY_SCRIPT if kind == "memory" else _INODE_SCRIPT,
    ]
    try:
        result = run(
            command, capture_output=True, text=True, timeout=30, check=False
        )
        expected_codes = {0, 137} if kind == "memory" else {0}
        checks["probe_execution"] = (
            CheckState.PASS
            if result.returncode in expected_codes
            else CheckState.FAIL
        )
        if result.returncode in expected_codes and len(result.stdout) <= 16384:
            if kind == "inode":
                _interpret_inode(result.stdout, result.returncode, checks)
            else:
                _interpret_memory(run, name, result, checks)
    except OSError, subprocess.SubprocessError, ValueError, TypeError:
        checks["probe_execution"] = CheckState.FAIL
    finally:
        for args in (
            ["podman", "kill", "--signal", "KILL", name],
            ["podman", "rm", "-f", name],
        ):
            try:
                run(
                    args,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
            except OSError, subprocess.SubprocessError:
                pass
        try:
            result = run(
                ["podman", "container", "exists", name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 1:
                checks["cleanup"] = CheckState.PASS
            elif result.returncode == 0:
                checks["cleanup"] = CheckState.FAIL
        except OSError, subprocess.SubprocessError:
            pass
    return PreflightReport(checks)


def _interpret_inode(output, returncode, checks):
    if returncode != 0:
        return
    lines = output.splitlines()
    totals = [line for line in lines if line.startswith("inode_total=")]
    outcomes = [line for line in lines if line.startswith("inode_result=")]
    if len(totals) != 1:
        return
    if totals[0] != "inode_total=128":
        checks["inode_limit"] = CheckState.FAIL
    elif outcomes == ["inode_result=enforced"]:
        checks["inode_limit"] = CheckState.PASS
    elif outcomes == ["inode_result=not_enforced"]:
        checks["inode_limit"] = CheckState.FAIL


def _interpret_memory(run, name, result, checks):
    limits = [
        line
        for line in result.stdout.splitlines()
        if line.startswith("memory_max=")
    ]
    if limits != ["memory_max=67108864"]:
        if len(limits) == 1:
            checks["memory_oom"] = CheckState.FAIL
        return
    inspected = run(
        ["podman", "inspect", name, "--format", "json"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if inspected.returncode != 0 or len(inspected.stdout) > 1000000:
        return
    try:
        data = json.loads(inspected.stdout)
        state = (
            data[0]["State"]
            if isinstance(data, list) and len(data) == 1
            else None
        )
        oom = state.get("OOMKilled") if isinstance(state, dict) else None
        if oom is True and result.returncode != 0:
            checks["memory_oom"] = CheckState.PASS
        elif oom is False and result.returncode == 0:
            checks["memory_oom"] = CheckState.FAIL
    except TypeError, ValueError, KeyError, IndexError:
        pass
