import subprocess
from types import SimpleNamespace

from workshop.agent_benchmark.crun_cgroup_probe import run_cgroup_probe
from workshop.agent_benchmark.preflight import CheckState


def ok(stdout=""):
    return SimpleNamespace(returncode=0, stdout=stdout)


def test_cgroup_probe_verifies_limits_freeze_thaw_and_cleanup():
    calls = []
    events = iter(["populated 1\nfrozen 1\n", "populated 1\nfrozen 0\n"])

    def run(args, **kwargs):
        calls.append(args)
        if args[0] == "systemd-run":
            assert "--user" in args
            assert "--property=MemoryMax=64M" in args
            assert "--property=TasksMax=32" in args
            assert "--property=CPUQuota=50%" in args
            return ok()
        if "ControlGroup" in args:
            unit = args[3]
            return ok(f"/user.slice/user-1000.slice/{unit}\n")
        if "Delegate" in args:
            return ok("yes\n")
        if "LoadState" in args:
            return ok("not-found\n")
        return ok()

    def read(path):
        if path.name == "memory.max":
            return "67108864\n"
        if path.name == "pids.max":
            return "32\n"
        if path.name == "cpu.max":
            return "50000 100000\n"
        if path.name == "cgroup.events":
            return next(events)
        raise AssertionError(path)

    report = run_cgroup_probe(
        run=run,
        read=read,
        exists=lambda path: False,
        platform="linux",
        uid=1000,
    )
    assert all(value is CheckState.PASS for value in report.checks.values())
    assert not report.ready
    assert any("freeze" in c for c in calls)
    assert any("thaw" in c for c in calls)
    assert any("stop" in c for c in calls)


def test_cgroup_probe_rejects_unsafe_platform_without_commands():
    def unexpected(*args, **kwargs):
        raise AssertionError("must not invoke systemd")

    report = run_cgroup_probe(run=unexpected, platform="darwin", uid=1000)
    assert report.checks["host"] is CheckState.FAIL
    assert not report.ready


def test_unit_disappearance_does_not_hide_remaining_cgroup():
    events = iter(["frozen 1", "frozen 0"])

    def run(args, **kwargs):
        if args[0] == "systemd-run":
            return ok()
        if "ControlGroup" in args:
            return ok(f"/user.slice/user-1000.slice/{args[3]}\n")
        if "Delegate" in args:
            return ok("yes\n")
        if "LoadState" in args:
            return ok("not-found\n")
        return ok()

    def read(path):
        if path.name == "cgroup.events":
            return next(events)
        return {
            "memory.max": "unlimited",
            "pids.max": "32",
            "cpu.max": "50000 100000",
        }[path.name]

    report = run_cgroup_probe(
        run=run,
        read=read,
        exists=lambda path: True,
        platform="linux",
        uid=1000,
    )
    assert report.checks["memory"] is CheckState.FAIL
    assert report.checks["cleanup"] is CheckState.FAIL
    assert not report.ready


def test_untrusted_cgroup_path_cannot_be_read():
    def run(args, **kwargs):
        if args[0] == "systemd-run":
            return ok()
        if "ControlGroup" in args:
            return ok("/../../etc/passwd\n")
        if "LoadState" in args:
            return ok("not-found\n")
        return ok("yes\n")

    def read(path):
        raise AssertionError("must not read an unsafe path")

    report = run_cgroup_probe(run=run, read=read, platform="linux", uid=1000)
    assert report.checks["cgroup_path"] is CheckState.FAIL
    assert report.checks["freeze"] is CheckState.UNVERIFIED
    assert report.checks["cleanup"] is CheckState.UNVERIFIED


def test_start_timeout_still_attempts_stop_and_checks_cleanup():
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[0] == "systemd-run":
            raise subprocess.TimeoutExpired(args, 5)
        if "LoadState" in args:
            return ok("not-found\n")
        return ok()

    report = run_cgroup_probe(run=run, platform="linux", uid=1000)
    assert report.checks["unit_started"] is CheckState.FAIL
    assert report.checks["cleanup"] is CheckState.UNVERIFIED
    assert any("stop" in c for c in calls)
    assert not report.ready


def test_freeze_failure_still_thaws_and_removes_service():
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[0] == "systemd-run":
            return ok()
        if "ControlGroup" in args:
            return ok(f"/user.slice/user-1000.slice/{args[3]}\n")
        if "Delegate" in args:
            return ok("yes\n")
        if "freeze" in args:
            return SimpleNamespace(returncode=1, stdout="")
        if "LoadState" in args:
            return ok("not-found\n")
        return ok()

    def read(path):
        return {
            "memory.max": "67108864",
            "pids.max": "32",
            "cpu.max": "50000 100000",
            "cgroup.events": "frozen 0",
        }[path.name]

    report = run_cgroup_probe(
        run=run,
        read=read,
        exists=lambda path: False,
        platform="linux",
        uid=1000,
    )
    assert report.checks["freeze"] is CheckState.FAIL
    assert any("thaw" in c for c in calls)
    assert report.checks["cleanup"] is CheckState.PASS
