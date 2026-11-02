import json
import subprocess
from types import SimpleNamespace

from workshop.agent_benchmark.preflight import CheckState, PreflightReport
from workshop.agent_benchmark.resource_probe import (
    run_inode_probe,
    run_memory_probe,
)


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


def make_runner(stdout="", code=0, oom=False, exists=1):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[1] == "run":
            return SimpleNamespace(returncode=code, stdout=stdout)
        if args[1] == "inspect":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps([{"State": {"OOMKilled": oom}}]),
            )
        if args[1:3] == ["container", "exists"]:
            return SimpleNamespace(returncode=exists, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    return run, calls


def test_memory_probe_requires_runtime_oom_evidence():
    run, calls = make_runner(
        stdout="memory_max=67108864\n", code=137, oom=True
    )
    report = run_memory_probe(run=run, runtime=runtime_ready())
    assert report.checks["memory_oom"] is CheckState.PASS
    assert report.checks["cleanup"] is CheckState.PASS
    assert not report.ready
    assert "--memory=64m" in calls[0]
    assert "--memory-swap=64m" in calls[0]
    assert "--network=none" in calls[0]


def test_memory_exit_code_alone_does_not_prove_oom():
    run, _ = make_runner(stdout="memory_max=67108864\n", code=137, oom=False)
    report = run_memory_probe(run=run, runtime=runtime_ready())
    assert report.checks["memory_oom"] is CheckState.UNVERIFIED
    assert not report.ready


def test_memory_oom_without_verified_limit_is_not_a_pass():
    run, _ = make_runner(stdout="memory_max=unknown\n", code=137, oom=True)
    report = run_memory_probe(run=run, runtime=runtime_ready())
    assert report.checks["memory_oom"] is CheckState.FAIL
    assert not report.ready


def test_inode_probe_requires_limit_and_enospc():
    run, calls = make_runner(stdout="inode_total=128\ninode_result=enforced\n")
    report = run_inode_probe(run=run, runtime=runtime_ready())
    assert report.checks["inode_limit"] is CheckState.PASS
    assert (
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m,nr_inodes=128"
        in calls[0]
    )
    assert report.checks["cleanup"] is CheckState.PASS
    assert not report.ready


def test_inode_runtime_rejection_is_not_success():
    run, _ = make_runner(code=125)
    report = run_inode_probe(run=run, runtime=runtime_ready())
    assert report.checks["probe_execution"] is CheckState.FAIL
    assert report.checks["inode_limit"] is CheckState.UNVERIFIED
    assert report.checks["cleanup"] is CheckState.PASS


def test_inode_probe_reports_wrong_limit_and_missing_evidence():
    run, _ = make_runner(stdout="inode_total=999\ninode_result=enforced\n")
    assert (
        run_inode_probe(run=run, runtime=runtime_ready()).checks["inode_limit"]
        is CheckState.FAIL
    )
    run, _ = make_runner(stdout="inode_total=128\n")
    assert (
        run_inode_probe(run=run, runtime=runtime_ready()).checks["inode_limit"]
        is CheckState.UNVERIFIED
    )


def test_resource_probe_fails_closed_and_cleans_on_timeout():
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[1] == "run":
            raise subprocess.TimeoutExpired(args, 30)
        if args[1:3] == ["container", "exists"]:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    report = run_memory_probe(run=run, runtime=runtime_ready())
    assert report.checks["probe_execution"] is CheckState.FAIL
    assert report.checks["cleanup"] is CheckState.PASS
    assert any(c[1:4] == ["kill", "--signal", "KILL"] for c in calls)
    assert not report.ready
    calls.clear()
    report = run_inode_probe(run=run, runtime=PreflightReport({}))
    assert report.checks["runtime_preflight"] is CheckState.FAIL
    assert not calls
