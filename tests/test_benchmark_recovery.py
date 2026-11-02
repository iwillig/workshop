import json
import subprocess
from types import SimpleNamespace

import pytest

from workshop.agent_benchmark.preflight import CheckState, PreflightReport
from workshop.agent_benchmark.recovery import recover_probe


ID = "a" * 64
TOKEN = "b" * 32
NAME = "workshop-crash-" + "c" * 32


@pytest.fixture(autouse=True)
def trusted_runtime(monkeypatch):
    report = PreflightReport(
        {
            "host_linux": CheckState.PASS,
            "runtime_local": CheckState.PASS,
            "runtime_available": CheckState.PASS,
            "rootless": CheckState.PASS,
        }
    )
    monkeypatch.setattr(
        "workshop.agent_benchmark.recovery.preflight", lambda: report
    )


def inspected(*, container_id=ID, name=NAME, token=TOKEN):
    return json.dumps(
        [
            {
                "Id": container_id,
                "Name": name,
                "Config": {"Labels": {"io.workshop.probe": token}},
            }
        ]
    )


def test_recover_only_exact_labelled_diagnostic_container():
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[1] == "inspect":
            return SimpleNamespace(returncode=0, stdout=inspected())
        if args[1:3] == ["container", "exists"]:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    assert recover_probe(ID, NAME, TOKEN, run=run) is CheckState.PASS
    assert calls == [
        ["podman", "inspect", ID, "--format", "json"],
        ["podman", "kill", "--signal", "KILL", ID],
        ["podman", "rm", "-f", ID],
        ["podman", "container", "exists", ID],
    ]


@pytest.mark.parametrize(
    "payload",
    [
        inspected(container_id="d" * 64),
        inspected(name="someone-else"),
        inspected(token="d" * 32),
        "[]",
        "invalid",
    ],
)
def test_recovery_never_removes_unmatched_container(payload):
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=payload)

    assert recover_probe(ID, NAME, TOKEN, run=run) is CheckState.UNVERIFIED
    assert len(calls) == 1 and calls[0][1] == "inspect"


@pytest.mark.parametrize(
    "container_id,name,token",
    [
        ("short", NAME, TOKEN),
        (ID, "workshop-crash-*", TOKEN),
        (ID, NAME, ""),
        ("--all", NAME, TOKEN),
    ],
)
def test_recovery_rejects_unsafe_identifiers(container_id, name, token):
    def run(*args, **kwargs):
        pytest.fail("must not invoke podman")

    with pytest.raises(ValueError):
        recover_probe(container_id, name, token, run=run)


def test_recovery_refuses_unverified_runtime(monkeypatch):
    monkeypatch.setattr(
        "workshop.agent_benchmark.recovery.preflight",
        lambda: PreflightReport({}),
    )

    def unexpected(*args, **kwargs):
        pytest.fail("must not invoke removal")

    assert (
        recover_probe(ID, NAME, TOKEN, run=unexpected) is CheckState.UNVERIFIED
    )


def test_recovery_reports_unverified_cleanup():
    def run(args, **kwargs):
        if args[1] == "inspect":
            return SimpleNamespace(returncode=0, stdout=inspected())
        if args[1] == "rm":
            raise subprocess.TimeoutExpired(args, 10)
        if args[1:3] == ["container", "exists"]:
            return SimpleNamespace(returncode=125, stdout="")
        return SimpleNamespace(returncode=0, stdout="")

    assert recover_probe(ID, NAME, TOKEN, run=run) is CheckState.UNVERIFIED
