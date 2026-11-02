"""Fixed negative tests for disposable Podman diagnostics, not a sandbox."""

import json
import socket
import subprocess
import uuid

from workshop.agent_benchmark.preflight import (
    CheckState,
    PreflightReport,
    preflight,
)
from workshop.agent_benchmark.probe import PROBE_IMAGE


_SCRIPT = r"""
export LC_ALL=C
probe_route() {
  output=$(timeout 2 bash -c 'exec 3<>/dev/tcp/'"$1"'/443' 2>&1)
  code=$?
  if [ "$code" -eq 0 ]; then printf '%s=reachable\n' "$2"
  elif printf '%s' "$output" | grep -q 'Network is unreachable'; then
    printf '%s=unreachable\n' "$2"
  else printf '%s=inconclusive\n' "$2"; fi
}
probe_route 192.0.2.1 ipv4
probe_route 2001:db8::1 ipv6
if timeout 2 getent ahosts workshop-boundary-probe.invalid >/dev/null 2>&1
then
  printf 'dns=resolved\n'
else printf 'dns=inconclusive\n'; fi
output=$(timeout 2 bash -c 'exec 3<>/dev/tcp/127.0.0.1/'"$PROBE_PORT" 2>&1)
code=$?
if [ "$code" -eq 0 ]; then printf 'host_loopback=reachable\n'
elif printf '%s' "$output" | grep -q 'Connection refused'; then
  printf 'host_loopback=refused\n'
else printf 'host_loopback=inconclusive\n'; fi
if touch /workshop-boundary-probe 2>/dev/null; then
  printf 'root_write=writable\n'; rm -f /workshop-boundary-probe
else printf 'root_write=blocked\n'; fi
sockets=absent
for path in /run/docker.sock /var/run/docker.sock /run/podman/podman.sock; do
  if [ -e "$path" ] || [ -L "$path" ]; then sockets=present; fi
done
printf 'runtime_sockets=%s\n' "$sockets"
output=$(dd if=/dev/zero of=/tmp/workshop-quota bs=1048576 count=65 2>&1)
code=$?
size=$(stat -c %s /tmp/workshop-quota 2>/dev/null || printf 0)
if [ "$code" -ne 0 ] && [ "$size" -ge 66000000 ] &&
   [ "$size" -le 67108864 ] &&
   printf '%s' "$output" | grep -q 'No space left on device'
then
  printf 'tmpfs_quota=enforced\n'
elif [ "$code" -eq 0 ]; then printf 'tmpfs_quota=not_enforced\n'
else printf 'tmpfs_quota=inconclusive\n'; fi
rm -f /tmp/workshop-quota
before=$(awk '$1 == "max" {print $2}' /sys/fs/cgroup/pids.events)
timeout 8 bash -c 'for ((i=0; i<200; i++)); do sleep 4 & done; wait' \
  >/dev/null 2>&1 || :
after=$(awk '$1 == "max" {print $2}' /sys/fs/cgroup/pids.events)
case "$before:$after" in
  *[!0-9:]*|:*) printf 'pids_exhaustion=inconclusive\n' ;;
  *) if [ "$after" -gt "$before" ]; then
       printf 'pids_exhaustion=enforced\n'
     else printf 'pids_exhaustion=inconclusive\n'; fi ;;
esac
"""


class _LoopbackListener:
    def __enter__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.bind(("127.0.0.1", 0))
            self.sock.listen(2)
            self.sock.settimeout(1)
            self.port = self.sock.getsockname()[1]
            with socket.create_connection(("127.0.0.1", self.port), timeout=1):
                connection, _ = self.sock.accept()
                connection.close()
            return self
        except BaseException:
            self.sock.close()
            raise

    def __exit__(self, *args):
        self.sock.close()


def run_boundary_probe(*, run=None, runtime=None, listener_factory=None):
    """Probe selected boundaries with fixed commands; never authorize runs."""
    run = run or subprocess.run
    runtime = runtime or preflight(run=run)
    listener_factory = listener_factory or _LoopbackListener
    names = (
        "runtime_preflight",
        "probe_execution",
        "ipv4_route",
        "ipv6_route",
        "dns",
        "host_loopback",
        "root_write",
        "runtime_sockets",
        "tmpfs_quota",
        "pids_exhaustion",
        "host_mounts",
        "network_mode",
        "cleanup",
    )
    checks = {name: CheckState.UNVERIFIED for name in names}
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
    name = "workshop-boundary-" + uuid.uuid4().hex
    try:
        with listener_factory() as listener:
            if (
                type(listener.port) is not int
                or not 1 <= listener.port <= 65535
            ):
                raise ValueError("invalid listener port")
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
                f"--env=PROBE_PORT={listener.port}",
                "--entrypoint=/bin/sh",
                PROBE_IMAGE,
                "-c",
                _SCRIPT,
            ]
            result = run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            checks["probe_execution"] = (
                CheckState.PASS if result.returncode == 0 else CheckState.FAIL
            )
            if result.returncode == 0 and len(result.stdout) <= 16384:
                _interpret(result.stdout, checks)
            _inspect(run, name, checks)
    except OSError, subprocess.SubprocessError, TypeError, ValueError:
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
    return PreflightReport(checks)


def run_timeout_probe(*, run=None, runtime=None):
    """Exercise client timeout and cleanup; never run agents."""
    run = run or subprocess.run
    runtime = runtime or preflight(run=run)
    checks = {
        key: CheckState.UNVERIFIED
        for key in (
            "runtime_preflight",
            "container_started",
            "timeout",
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
    name = "workshop-timeout-" + uuid.uuid4().hex
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
        "--entrypoint=/bin/sleep",
        PROBE_IMAGE,
        "30",
    ]
    timed_out = False
    try:
        run(command, capture_output=True, text=True, timeout=2, check=False)
        checks["timeout"] = CheckState.FAIL
    except subprocess.TimeoutExpired:
        timed_out = True
    except OSError, subprocess.SubprocessError:
        checks["timeout"] = CheckState.FAIL
    finally:
        if timed_out:
            try:
                observed = run(
                    ["podman", "container", "exists", name],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if observed.returncode == 0:
                    checks["container_started"] = CheckState.PASS
                    checks["timeout"] = CheckState.PASS
            except OSError, subprocess.SubprocessError:
                pass
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
            observed = run(
                ["podman", "container", "exists", name],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if observed.returncode == 1:
                checks["cleanup"] = CheckState.PASS
            elif observed.returncode == 0:
                checks["cleanup"] = CheckState.FAIL
        except OSError, subprocess.SubprocessError:
            pass
    return PreflightReport(checks)


def _interpret(output, checks):
    values = {}
    duplicates = set()
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            if key in values:
                duplicates.add(key)
            values[key] = value.strip()
    rules = {
        "ipv4": ("ipv4_route", "unreachable", "reachable"),
        "ipv6": ("ipv6_route", "unreachable", "reachable"),
        "host_loopback": ("host_loopback", "refused", "reachable"),
        "root_write": ("root_write", "blocked", "writable"),
        "runtime_sockets": ("runtime_sockets", "absent", "present"),
        "tmpfs_quota": ("tmpfs_quota", "enforced", "not_enforced"),
        "pids_exhaustion": ("pids_exhaustion", "enforced", "not_enforced"),
        "dns": ("dns", None, "resolved"),
    }
    for key, (check, passing, failing) in rules.items():
        if key in duplicates:
            continue
        value = values.get(key)
        if passing is not None and value == passing:
            checks[check] = CheckState.PASS
        elif value == failing:
            checks[check] = CheckState.FAIL


def _inspect(run, name, checks):
    result = run(
        ["podman", "inspect", name, "--format", "json"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0 or len(result.stdout) > 1_000_000:
        return
    try:
        data = json.loads(result.stdout)
        if (
            not isinstance(data, list)
            or len(data) != 1
            or not isinstance(data[0], dict)
        ):
            return
        item = data[0]
        host = item.get("HostConfig")
        if not isinstance(host, dict):
            return
        mounts, binds, network = (
            item.get("Mounts"),
            host.get("Binds"),
            host.get("NetworkMode"),
        )
        if isinstance(mounts, list) and isinstance(binds, list):
            checks["host_mounts"] = (
                CheckState.PASS
                if not mounts and not binds
                else CheckState.FAIL
            )
        if isinstance(network, str):
            checks["network_mode"] = (
                CheckState.PASS if network == "none" else CheckState.FAIL
            )
    except ValueError, TypeError:
        return
