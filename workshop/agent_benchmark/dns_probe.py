"""Controlled loopback DNS diagnostic; not a sandbox readiness check."""

import os
import socket
import subprocess
import threading
import uuid

from workshop.agent_benchmark.preflight import (
    CheckState,
    PreflightReport,
    preflight,
)
from workshop.agent_benchmark.probe import PROBE_IMAGE


_QUERY = (
    b"WK\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
    b"\x08workshop\x05probe\x07invalid\x00\x00\x01\x00\x01"
)
_RESPONSE = (
    b"WK\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00"
    + _QUERY[12:]
    + b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x01"
    + b"\x00\x04\xc0\x00\x02\x07"
)

_SCRIPT = r"""
if ! exec 3<>/dev/udp/127.0.0.1/"$PROBE_DNS_PORT"; then
  printf 'dns_attempt=failed\ndns=inconclusive\n'; exit 0
fi
if printf '%b' 'WK\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00' \
  '\x08workshop\x05probe\x07invalid\x00\x00\x01\x00\x01' >&3
then
  printf 'dns_attempt=sent\n'
  if IFS= read -r -N 1 -t 1 reply <&3 && [ "$reply" = W ]; then
    printf 'dns=answered\n'
  else printf 'dns=no_response\n'; fi
else printf 'dns_attempt=failed\ndns=inconclusive\n'; fi
"""


class _DnsListener:
    """Answer exactly one fixed DNS query on a temporary host loopback port."""

    def __enter__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind(("127.0.0.1", 0))
            self.sock.settimeout(0.1)
        except BaseException:
            self.sock.close()
            raise
        self.port = self.sock.getsockname()[1]
        self._stop = threading.Event()
        self._baseline_seen = threading.Event()
        self._observed = threading.Event()
        self._monitor = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        self.baseline_ok = False
        try:
            result = subprocess.run(
                ["/bin/bash", "-c", _SCRIPT],
                env=os.environ | {"PROBE_DNS_PORT": str(self.port)},
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            lines = result.stdout.splitlines()
            self.baseline_ok = (
                result.returncode == 0
                and lines.count("dns_attempt=sent") == 1
                and lines.count("dns=answered") == 1
                and self._baseline_seen.is_set()
            )
        except OSError, subprocess.SubprocessError:
            pass
        self._monitor = True
        return self

    def wait_observation(self):
        """Allow a bounded interval for a queued request to arrive."""
        return self._observed.wait(timeout=0.2)

    def _serve(self):
        while not self._stop.is_set():
            try:
                data, peer = self.sock.recvfrom(512)
                if data == _QUERY:
                    if self._monitor:
                        self._observed.set()
                    else:
                        self._baseline_seen.set()
                    self.sock.sendto(_RESPONSE, peer)
            except socket.timeout:
                continue
            except OSError:
                break

    def __exit__(self, *args):
        self._stop.set()
        self.sock.close()
        self._thread.join(timeout=1)


def run_dns_probe(*, run=None, runtime=None, listener_factory=None):
    """Probe a controlled host-loopback DNS listener; never run agents."""
    run = run or subprocess.run
    runtime = runtime or preflight(run=run)
    listener_factory = listener_factory or _DnsListener
    checks = {
        key: CheckState.UNVERIFIED
        for key in (
            "runtime_preflight",
            "host_baseline",
            "probe_execution",
            "host_loopback_dns",
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
    name = "workshop-dns-" + uuid.uuid4().hex
    started = False
    try:
        with listener_factory() as listener:
            if not listener.baseline_ok:
                checks["host_baseline"] = CheckState.FAIL
                return PreflightReport(checks)
            checks["host_baseline"] = CheckState.PASS
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
                f"--env=PROBE_DNS_PORT={listener.port}",
                "--entrypoint=/bin/bash",
                PROBE_IMAGE,
                "-c",
                _SCRIPT,
            ]
            started = True
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
            output = (
                result.stdout
                if result.returncode == 0 and len(result.stdout) <= 16384
                else ""
            )
            lines = output.splitlines()
            sent = lines.count("dns_attempt=sent") == 1
            answered = lines.count("dns=answered") == 1
            no_response = lines.count("dns=no_response") == 1
            if listener.wait_observation() or answered:
                checks["host_loopback_dns"] = CheckState.FAIL
            elif (
                sent
                and no_response
                and lines == ["dns_attempt=sent", "dns=no_response"]
            ):
                checks["host_loopback_dns"] = CheckState.PASS
    except OSError, subprocess.SubprocessError, ValueError, TypeError:
        checks["probe_execution"] = CheckState.FAIL
    finally:
        if started:
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
