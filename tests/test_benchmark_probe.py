import subprocess
from types import SimpleNamespace

from workshop.agent_benchmark.preflight import CheckState, PreflightReport
from workshop.agent_benchmark.probe import run_probe


PASS_OUTPUT = """\
uid=65534
caps=0000000000000000
seccomp=2
nonewprivs=1
root_readonly=yes
interfaces=lo
memory=536870912
pids=128
cpu=100000 100000
tmpfs_bytes=67108864
"""


def runtime_ready():
    return PreflightReport(
        {
            "host_linux": CheckState.PASS,
            "runtime_available": CheckState.PASS,
            "runtime_local": CheckState.PASS,
            "rootless": CheckState.PASS,
            "seccomp_available": CheckState.PASS,
            "cgroups_v2": CheckState.PASS,
            "resource_controllers": CheckState.PASS,
        }
    )


def test_probe_uses_fixed_policy_and_does_not_enable_benchmarks():
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        if args[1] == "run":
            return SimpleNamespace(returncode=0, stdout=PASS_OUTPUT)
        if args[1:3] == ["container", "exists"]:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    report = run_probe(run=run, runtime=runtime_ready())
    command = calls[0][0]
    assert "--pull=never" in command and "--network=none" in command
    assert "--read-only" in command and "--cap-drop=all" in command
    assert "--user=65534:65534" in command
    assert "--memory=512m" in command and "--pids-limit=128" in command
    assert "--cpus=1" in command
    assert "--security-opt=no-new-privileges" in command
    assert "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m" in command
    assert not any(arg.startswith("--volume") for arg in command)
    assert all(check is CheckState.PASS for check in report.checks.values())
    assert report.ready is False
    assert calls[-1][0][1:3] == ["container", "exists"]


def test_probe_refuses_unverified_preflight():
    calls = []
    report = run_probe(
        run=lambda *a, **k: calls.append(a), runtime=PreflightReport({})
    )
    assert not calls
    assert report.checks["runtime_preflight"] is CheckState.FAIL
    assert not report.ready


def test_probe_timeout_attempts_cleanup_and_never_grants_readiness():
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[1] == "run":
            raise subprocess.TimeoutExpired(args, 30)
        if args[1:3] == ["container", "exists"]:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    report = run_probe(run=run, runtime=runtime_ready())
    assert report.checks["probe_execution"] is CheckState.FAIL
    assert report.checks["cleanup"] is CheckState.PASS
    assert any(call[1:4] == ["kill", "--signal", "KILL"] for call in calls)
    assert any(call[1:3] == ["rm", "-f"] for call in calls)
    assert not report.ready


def test_probe_reports_container_left_after_failed_cleanup():
    def run(args, **kwargs):
        if args[1] == "run":
            return SimpleNamespace(returncode=0, stdout=PASS_OUTPUT)
        if args[1] == "rm":
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    report = run_probe(run=run, runtime=runtime_ready())
    assert report.checks["cleanup"] is CheckState.FAIL
    assert not report.ready


def test_duplicate_output_never_satisfies_a_check():
    def run(args, **kwargs):
        if args[1] == "run":
            return SimpleNamespace(
                returncode=0, stdout=PASS_OUTPUT + "uid=0\n"
            )
        if args[1:3] == ["container", "exists"]:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    report = run_probe(run=run, runtime=runtime_ready())
    assert report.checks["non_root"] is CheckState.UNVERIFIED
    assert not report.ready


def test_probe_missing_or_malformed_output_never_passes():
    def run(args, **kwargs):
        if args[1] == "run":
            return SimpleNamespace(returncode=0, stdout="uid=0\n")
        if args[1:3] == ["container", "exists"]:
            return SimpleNamespace(returncode=125, stdout="")
        return SimpleNamespace(returncode=1, stdout="")

    report = run_probe(run=run, runtime=runtime_ready())
    assert report.checks["non_root"] is CheckState.FAIL
    assert report.checks["seccomp"] is CheckState.UNVERIFIED
    assert report.checks["cleanup"] is CheckState.UNVERIFIED
    assert not report.ready
