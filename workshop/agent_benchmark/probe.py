"""Run a fixed disposable Podman diagnostic, never a benchmark workload."""

import subprocess
import uuid

from workshop.agent_benchmark.preflight import (
    CheckState,
    PreflightReport,
    preflight,
)

# A locally available Fedora image, selected for this diagnostic only. This
# digest is not an approved benchmark image or a provenance guarantee.
PROBE_IMAGE = (
    "registry.fedoraproject.org/fedora@sha256:"
    "51092fec4f648f1771f50dbf15e87b67c172202d82dfdb92c9d9d758d7258869"
)

# Fixed script: no fixture, host mount, agent, or caller-supplied commands.
_SCRIPT = r"""
printf 'uid=%s\n' "$(id -u)"
printf 'caps=%s\n' "$(awk '/^CapEff:/ {print $2}' /proc/self/status)"
printf 'seccomp=%s\n' "$(awk '/^Seccomp:/ {print $2}' /proc/self/status)"
printf 'nonewprivs=%s\n' "$(awk '/^NoNewPrivs:/ {print $2}' /proc/self/status)"
printf 'root_readonly=%s\n' "$(awk '$5 == "/" {
  if ($6 ~ /^ro(,|$)/) print "yes"; else print "no"
}' /proc/self/mountinfo)"
printf 'interfaces='
for i in /sys/class/net/*; do printf '%s ' "${i##*/}"; done
printf '\n'
printf 'memory=%s\n' "$(cat /sys/fs/cgroup/memory.max)"
printf 'pids=%s\n' "$(cat /sys/fs/cgroup/pids.max)"
printf 'cpu=%s\n' "$(cat /sys/fs/cgroup/cpu.max)"
printf 'tmpfs_bytes=%s\n' "$(stat -f -c '%S %b' /tmp | awk '{print $1 * $2}')"
"""


class ProbeReport(PreflightReport):
    """Results of one fixed diagnostic; inherited readiness is always false."""


def run_probe(*, run=None, runtime=None):
    """Run only fixed diagnostics in a disposable rootless container."""
    if run is None:
        run = subprocess.run
    if runtime is None:
        runtime = preflight(run=run)
    checks = {
        name: CheckState.UNVERIFIED
        for name in (
            "runtime_preflight",
            "probe_execution",
            "non_root",
            "capabilities",
            "seccomp",
            "no_new_privileges",
            "root_readonly",
            "interfaces",
            "memory_limit",
            "process_limit",
            "cpu_limit",
            "tmpfs_limit",
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
        return ProbeReport(checks)
    checks["runtime_preflight"] = CheckState.PASS
    name = "workshop-probe-" + uuid.uuid4().hex
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
        "--memory=512m",
        "--pids-limit=128",
        "--cpus=1",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m",
        "--entrypoint=/bin/sh",
        PROBE_IMAGE,
        "-c",
        _SCRIPT,
    ]
    try:
        result = run(
            command, capture_output=True, text=True, timeout=30, check=False
        )
        checks["probe_execution"] = (
            CheckState.PASS if result.returncode == 0 else CheckState.FAIL
        )
        if result.returncode == 0 and len(result.stdout) <= 16384:
            _interpret(result.stdout, checks)
    except OSError, subprocess.SubprocessError, ValueError, TypeError:
        checks["probe_execution"] = CheckState.FAIL
    finally:
        try:
            run(
                ["podman", "kill", "--signal", "KILL", name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except OSError, subprocess.SubprocessError:
            pass
        try:
            run(
                ["podman", "rm", "-f", name],
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
    return ProbeReport(checks)


def _interpret(output, checks):
    values = {}
    duplicates = set()
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if not separator:
            continue
        if key in values:
            duplicates.add(key)
        values[key] = value.strip()
    expected = {
        "uid": ("non_root", "65534"),
        "caps": ("capabilities", "0000000000000000"),
        "seccomp": ("seccomp", "2"),
        "nonewprivs": ("no_new_privileges", "1"),
        "root_readonly": ("root_readonly", "yes"),
        "interfaces": ("interfaces", "lo"),
        "memory": ("memory_limit", "536870912"),
        "pids": ("process_limit", "128"),
        "cpu": ("cpu_limit", "100000 100000"),
        "tmpfs_bytes": ("tmpfs_limit", "67108864"),
    }
    for key, (check, expected_value) in expected.items():
        if key in values and key not in duplicates:
            checks[check] = (
                CheckState.PASS
                if values[key] == expected_value
                else CheckState.FAIL
            )
