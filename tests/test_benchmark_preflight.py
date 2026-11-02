import json
import subprocess
from types import SimpleNamespace

import pytest

from workshop.agent_benchmark.preflight import CheckState, preflight


def info(**changes):
    host = {
        "os": "linux",
        "serviceIsRemote": False,
        "cgroupVersion": "v2",
        "cgroupControllers": ["cpu", "memory", "pids"],
        "security": {"rootless": True, "seccompEnabled": True},
    }
    host.update(changes)
    return json.dumps({"host": host})


def result(stdout):
    return SimpleNamespace(returncode=0, stdout=stdout)


def test_preflight_never_grants_execution_even_when_runtime_passes():
    calls = []

    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return result(info())

    report = preflight(run=run, platform="linux")
    assert calls[0][0][0] == ["podman", "info", "--format", "json"]
    assert report.checks["rootless"] is CheckState.PASS
    assert report.checks["seccomp_available"] is CheckState.PASS
    assert report.checks["effective_sandbox"] is CheckState.UNVERIFIED
    assert report.checks["security_review"] is CheckState.UNVERIFIED
    assert report.ready is False


@pytest.mark.parametrize(
    "host",
    [
        {"security": {"rootless": False, "seccompEnabled": True}},
        {"serviceIsRemote": True},
        {"cgroupVersion": "v1"},
        {"cgroupControllers": ["cpu"]},
        {"security": {"rootless": True, "seccompEnabled": False}},
    ],
)
def test_preflight_reports_failed_capabilities(host):
    report = preflight(
        run=lambda *a, **kw: result(info(**host)), platform="linux"
    )
    assert CheckState.FAIL in report.checks.values()
    assert not report.ready


def test_non_linux_does_not_invoke_runtime():
    def unexpected(*args, **kwargs):
        raise AssertionError("must not invoke podman")

    report = preflight(run=unexpected, platform="darwin")
    assert report.checks["host_linux"] is CheckState.FAIL
    assert report.checks["rootless"] is CheckState.UNVERIFIED
    assert not report.ready


@pytest.mark.parametrize(
    "failure",
    [
        FileNotFoundError(),
        subprocess.TimeoutExpired("podman", 5),
        ValueError("bad"),
    ],
)
def test_preflight_fails_closed_on_runtime_errors(failure):
    def fail(*args, **kwargs):
        raise failure

    report = preflight(run=fail, platform="linux")
    assert report.checks["runtime_available"] is CheckState.FAIL
    assert report.checks["rootless"] is CheckState.UNVERIFIED
    assert not report.ready


@pytest.mark.parametrize(
    "stdout", ["not-json", "{}", '{"host": []}', info(security={})]
)
def test_malformed_or_missing_capabilities_are_never_passed(stdout):
    report = preflight(run=lambda *a, **kw: result(stdout), platform="linux")
    assert report.checks["rootless"] is not CheckState.PASS
    assert not report.ready


def test_runtime_failure_does_not_report_sensitive_stderr():
    def run(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="secret-token")

    report = preflight(run=run, platform="linux")
    assert report.checks["runtime_available"] is CheckState.FAIL
    assert "secret-token" not in repr(report)
