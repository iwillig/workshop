import subprocess
from types import SimpleNamespace

from workshop.agent_benchmark.dns_probe import run_dns_probe
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
    observed = False
    baseline_ok = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def wait_observation(self):
        return self.observed


def fake_run(output):
    def run(args, **kwargs):
        if args[1] == "run":
            return SimpleNamespace(returncode=0, stdout=output)
        if args[1:3] == ["container", "exists"]:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    return run


def test_controlled_dns_listener_has_working_host_baseline():
    from workshop.agent_benchmark.dns_probe import _DnsListener

    with _DnsListener() as listener:
        assert listener.baseline_ok
        assert not listener.wait_observation()


def test_dns_negative_requires_baseline_and_confirmed_attempt():
    report = run_dns_probe(
        run=fake_run("dns_attempt=sent\ndns=no_response\n"),
        runtime=runtime_ready(),
        listener_factory=Listener,
    )
    assert report.checks["host_baseline"] is CheckState.PASS
    assert report.checks["host_loopback_dns"] is CheckState.PASS
    assert report.checks["cleanup"] is CheckState.PASS
    assert not report.ready


def test_dns_server_observation_is_failure_even_when_response_lost():
    class Seen(Listener):
        observed = True

    report = run_dns_probe(
        run=fake_run("dns_attempt=sent\ndns=no_response\n"),
        runtime=runtime_ready(),
        listener_factory=Seen,
    )
    assert report.checks["host_loopback_dns"] is CheckState.FAIL


def test_dns_missing_attempt_or_failed_baseline_are_unverified():
    report = run_dns_probe(
        run=fake_run("dns=no_response\n"),
        runtime=runtime_ready(),
        listener_factory=Listener,
    )
    assert report.checks["host_loopback_dns"] is CheckState.UNVERIFIED

    class NoBaseline(Listener):
        baseline_ok = False

    report = run_dns_probe(
        run=fake_run("dns_attempt=sent\ndns=no_response\n"),
        runtime=runtime_ready(),
        listener_factory=NoBaseline,
    )
    assert report.checks["host_baseline"] is CheckState.FAIL
    assert report.checks["host_loopback_dns"] is CheckState.UNVERIFIED


def test_dns_ambiguous_or_duplicate_output_is_not_a_pass():
    output = "dns_attempt=sent\ndns_attempt=failed\ndns=no_response\n"
    report = run_dns_probe(
        run=fake_run(output),
        runtime=runtime_ready(),
        listener_factory=Listener,
    )
    assert report.checks["host_loopback_dns"] is CheckState.UNVERIFIED


def test_dns_timeout_kills_and_verifies_cleanup():
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[1] == "run":
            raise subprocess.TimeoutExpired(args, 30)
        if args[1:3] == ["container", "exists"]:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    report = run_dns_probe(
        run=run, runtime=runtime_ready(), listener_factory=Listener
    )
    assert report.checks["probe_execution"] is CheckState.FAIL
    assert report.checks["cleanup"] is CheckState.PASS
    assert any(c[1:4] == ["kill", "--signal", "KILL"] for c in calls)
    assert not report.ready


def test_dns_no_probe_without_runtime_preflight():
    def unexpected(*args, **kwargs):
        raise AssertionError("must not run")

    report = run_dns_probe(
        run=unexpected,
        runtime=PreflightReport({}),
        listener_factory=unexpected,
    )
    assert report.checks["runtime_preflight"] is CheckState.FAIL
