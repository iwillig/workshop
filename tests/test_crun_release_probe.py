import os

import pytest

from workshop.agent_benchmark.crun_release_probe import run_release_probe
from workshop.agent_benchmark.preflight import CheckState


def test_release_is_denied_by_default():
    report = run_release_probe()
    assert report.checks["released"] is CheckState.FAIL
    assert report.checks["worker_exit"] is CheckState.PASS
    assert report.checks["fd_cleanup"] is CheckState.PASS
    assert not report.ready


def test_simulated_valid_checks_release_only_fixed_test_program():
    report = run_release_probe(simulated_checks_pass=True)
    assert report.checks["released"] is CheckState.PASS
    assert report.checks["fd_cleanup"] is CheckState.PASS
    assert not report.ready


def test_simulated_identity_mismatch_denies_release():
    report = run_release_probe(
        simulated_checks_pass=True, simulate_identity_mismatch=True
    )
    assert report.checks["identity"] is CheckState.FAIL
    assert report.checks["released"] is CheckState.FAIL
    assert not report.ready


def test_forged_worker_report_does_not_authorize_release():
    report = run_release_probe(simulate_forged_report=True)
    assert report.checks["released"] is CheckState.FAIL
    assert report.checks["worker_exit"] is CheckState.PASS
    assert not report.ready


def test_forged_success_marker_cannot_override_denial(monkeypatch):
    monkeypatch.setattr(
        "workshop.agent_benchmark.crun_release_probe._CHILD",
        'import os; os.write(1, b"FIXED_TEST_RELEASED\\n")',
    )
    report = run_release_probe()
    assert report.checks["released"] is CheckState.FAIL
    assert not report.ready


def test_closed_channel_does_not_grant_release():
    report = run_release_probe(
        simulated_checks_pass=True, simulate_closed_channel=True
    )
    assert report.checks["released"] is CheckState.FAIL
    assert report.checks["worker_exit"] is CheckState.PASS
    assert not report.ready


def test_missing_pidfd_denies_even_simulated_approval(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("pidfd unavailable")

    monkeypatch.setattr(
        "workshop.agent_benchmark.crun_release_probe.os.pidfd_open", fail
    )
    report = run_release_probe(simulated_checks_pass=True)
    assert report.checks["identity"] is CheckState.UNVERIFIED
    assert report.checks["released"] is CheckState.FAIL
    assert report.checks["fd_cleanup"] is CheckState.PASS
    assert not report.ready


def test_reject_ambiguous_options():
    with pytest.raises(TypeError):
        run_release_probe(simulated_checks_pass="yes")


def test_pipe_descriptors_are_closed(monkeypatch):
    fds = []
    real_pipe = os.pipe

    def pipe():
        pair = real_pipe()
        fds.extend(pair)
        return pair

    monkeypatch.setattr(
        "workshop.agent_benchmark.crun_release_probe.os.pipe", pipe
    )
    report = run_release_probe(simulated_checks_pass=True)
    assert report.checks["fd_cleanup"] is CheckState.PASS
    for fd in fds:
        with pytest.raises(OSError):
            os.fstat(fd)
