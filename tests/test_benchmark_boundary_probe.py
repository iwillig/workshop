import json
import subprocess
from types import SimpleNamespace

from workshop.agent_benchmark.boundary_probe import (
    run_boundary_probe,
    run_timeout_probe,
)
from workshop.agent_benchmark.preflight import CheckState, PreflightReport


def runtime_ready():
    return PreflightReport(
        {
            name: CheckState.PASS
            for name in (
                "host_linux",
                "runtime_available",
                "runtime_local",
                "rootless",
                "seccomp_available",
                "cgroups_v2",
                "resource_controllers",
            )
        }
    )


class Listener:
    port = 12345

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_boundary_probe_preserves_uncertainty_and_checks_mounts():
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[1] == "run":
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    "ipv4=unreachable\nipv6=inconclusive\ndns=inconclusive\n"
                    "host_loopback=refused\nroot_write=blocked\n"
                    "runtime_sockets=absent\ntmpfs_quota=enforced\n"
                    "pids_exhaustion=enforced\n"
                ),
            )
        if args[1] == "inspect":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "Mounts": [],
                            "HostConfig": {"Binds": [], "NetworkMode": "none"},
                        }
                    ]
                ),
            )
        if args[1:3] == ["container", "exists"]:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    report = run_boundary_probe(
        run=run, runtime=runtime_ready(), listener_factory=Listener
    )
    assert report.checks["ipv4_route"] is CheckState.PASS
    assert report.checks["ipv6_route"] is CheckState.UNVERIFIED
    assert report.checks["dns"] is CheckState.UNVERIFIED
    assert report.checks["host_loopback"] is CheckState.PASS
    assert report.checks["host_mounts"] is CheckState.PASS
    assert report.checks["tmpfs_quota"] is CheckState.PASS
    assert report.checks["pids_exhaustion"] is CheckState.PASS
    assert report.checks["cleanup"] is CheckState.PASS
    assert not report.ready
    assert any("--env=PROBE_PORT=12345" in call for call in calls)


def test_boundary_probe_rejects_reachable_and_mounts():
    def run(args, **kwargs):
        if args[1] == "run":
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    "ipv4=reachable\nhost_loopback=reachable\n"
                    "root_write=writable\nruntime_sockets=present\n"
                    "tmpfs_quota=not_enforced\npids_exhaustion=not_enforced\n"
                ),
            )
        if args[1] == "inspect":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    [
                        {
                            "Mounts": [{"Source": "/host"}],
                            "HostConfig": {
                                "Binds": ["/host:/host"],
                                "NetworkMode": "host",
                            },
                        }
                    ]
                ),
            )
        if args[1:3] == ["container", "exists"]:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    report = run_boundary_probe(
        run=run, runtime=runtime_ready(), listener_factory=Listener
    )
    for name in (
        "ipv4_route",
        "host_loopback",
        "root_write",
        "runtime_sockets",
        "host_mounts",
        "network_mode",
        "tmpfs_quota",
        "pids_exhaustion",
    ):
        assert report.checks[name] is CheckState.FAIL
    assert not report.ready


def test_boundary_probe_timeout_attempts_cleanup():
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[1] == "run":
            raise subprocess.TimeoutExpired(args, 30)
        if args[1:3] == ["container", "exists"]:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    report = run_boundary_probe(
        run=run, runtime=runtime_ready(), listener_factory=Listener
    )
    assert report.checks["probe_execution"] is CheckState.FAIL
    assert report.checks["cleanup"] is CheckState.PASS
    assert any(call[1:4] == ["kill", "--signal", "KILL"] for call in calls)
    assert any(call[1:3] == ["rm", "-f"] for call in calls)
    assert not report.ready


def test_malformed_inspect_and_duplicate_observations_remain_unverified():
    def run(args, **kwargs):
        if args[1] == "run":
            return SimpleNamespace(
                returncode=0, stdout="ipv4=unreachable\nipv4=reachable\n"
            )
        if args[1] == "inspect":
            return SimpleNamespace(returncode=0, stdout="not-json")
        if args[1:3] == ["container", "exists"]:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    report = run_boundary_probe(
        run=run, runtime=runtime_ready(), listener_factory=Listener
    )
    assert report.checks["ipv4_route"] is CheckState.UNVERIFIED
    assert report.checks["host_mounts"] is CheckState.UNVERIFIED
    assert report.checks["network_mode"] is CheckState.UNVERIFIED
    assert not report.ready


def test_timeout_probe_checks_container_existed_then_cleanup():
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[1] == "run":
            raise subprocess.TimeoutExpired(args, 2)
        if args[1:3] == ["container", "exists"]:
            return SimpleNamespace(
                returncode=1 if any(c[1] == "rm" for c in calls) else 0,
                stdout="",
            )
        return SimpleNamespace(returncode=0, stdout="")

    report = run_timeout_probe(run=run, runtime=runtime_ready())
    assert report.checks["container_started"] is CheckState.PASS
    assert any(c[1:4] == ["kill", "--signal", "KILL"] for c in calls)
    assert report.checks["timeout"] is CheckState.PASS
    assert report.checks["cleanup"] is CheckState.PASS
    assert not report.ready


def test_timeout_probe_does_not_claim_success_without_container():
    def run(args, **kwargs):
        if args[1] == "run":
            raise subprocess.TimeoutExpired(args, 2)
        if args[1:3] == ["container", "exists"]:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    report = run_timeout_probe(run=run, runtime=runtime_ready())
    assert report.checks["container_started"] is CheckState.UNVERIFIED
    assert report.checks["timeout"] is CheckState.UNVERIFIED
    assert not report.ready


def test_boundary_probe_does_not_run_without_preflight():
    def unexpected(*args, **kwargs):
        raise AssertionError("must not run")

    report = run_boundary_probe(
        run=unexpected,
        runtime=PreflightReport({}),
        listener_factory=unexpected,
    )
    assert report.checks["runtime_preflight"] is CheckState.FAIL
    assert not report.ready
