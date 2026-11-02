import subprocess
from types import SimpleNamespace

from workshop.agent_benchmark.crun_child_cgroup_probe import run_child_probe
from workshop.agent_benchmark.preflight import CheckState


def ok(stdout=""):
    return SimpleNamespace(returncode=0, stdout=stdout)


def test_child_delegation_limits_freeze_thaw_and_cleanup():
    calls, writes = [], []
    events = iter(["populated 1\nfrozen 1", "populated 1\nfrozen 0"])

    def run(args, **kwargs):
        calls.append(args)
        if args[0] == "systemd-run":
            script = args[args.index("-c") + 1]
            assert "</proc/self/stat" in script
            assert '"$$"' not in script
            assert "--property=Delegate=yes" in args
            assert "--property=RuntimeMaxSec=30s" in args
            return ok()
        if "ControlGroup" in args:
            return ok(
                f"/user.slice/user-1000.slice/user@1000.service/{args[3]}\n"
            )
        if "MainPID" in args:
            return ok("4321\n")
        if "LoadState" in args:
            return ok("not-found\n")
        return ok()

    def read(path):
        if path.name == "cgroup.events":
            return next(events)
        if str(path) == "/proc/4322/status":
            return "Name:\tsleep\nPPid:\t4321\n"
        return {
            "cgroup.subtree_control": "cpu memory pids",
            "cgroup.procs": "4321\n4322\n",
            "memory.max": "33554432",
            "memory.swap.max": "0",
            "pids.max": "16",
            "cpu.max": "25000 100000",
        }[path.name]

    def write(path, value):
        writes.append((path.name, value))

    report = run_child_probe(
        run=run,
        read=read,
        write=write,
        exists=lambda path: False,
        platform="linux",
        uid=1000,
    )
    assert all(state is CheckState.PASS for state in report.checks.values())
    assert report.checks["workload_identity"] is CheckState.PASS
    assert report.checks["swap"] is CheckState.PASS
    assert report.checks["descendant"] is CheckState.PASS
    assert report.checks["frozen_members"] is CheckState.PASS
    assert report.checks["thawed_members"] is CheckState.PASS
    assert writes == [("cgroup.freeze", "1"), ("cgroup.freeze", "0")]
    assert any("stop" in call for call in calls)
    assert not report.ready


def test_unknown_workload_is_never_frozen():
    def run(args, **kwargs):
        if args[0] == "systemd-run":
            return ok()
        if "ControlGroup" in args:
            return ok(
                f"/user.slice/user-1000.slice/user@1000.service/{args[3]}\n"
            )
        if "MainPID" in args:
            return ok("4321\n")
        if "LoadState" in args:
            return ok("not-found\n")
        return ok()

    def read(path):
        return {
            "cgroup.subtree_control": "cpu memory pids",
            "cgroup.procs": "9999",
            "memory.max": "33554432",
            "memory.swap.max": "0",
            "pids.max": "16",
            "cpu.max": "25000 100000",
        }[path.name]

    def forbidden(*args):
        raise AssertionError("must not freeze unknown workload")

    report = run_child_probe(
        run=run,
        read=read,
        write=forbidden,
        exists=lambda path: False,
        platform="linux",
        uid=1000,
    )
    assert report.checks["workload_identity"] is CheckState.FAIL
    assert report.checks["freeze"] is CheckState.UNVERIFIED
    assert report.checks["cleanup"] is CheckState.PASS
    assert not report.ready


def test_membership_change_is_not_reported_as_pass():
    from pathlib import Path

    from workshop.agent_benchmark.crun_child_cgroup_probe import _same_members

    assert (
        _same_members(
            lambda path: "4321\n9999\n", Path("/unused"), {"4321", "4322"}
        )
        is CheckState.FAIL
    )
    assert (
        _same_members(
            lambda path: "4321\n4321\n", Path("/unused"), {"4321", "4322"}
        )
        is CheckState.FAIL
    )


def test_bad_path_never_reads_or_writes_cgroup():
    def run(args, **kwargs):
        if args[0] == "systemd-run":
            return ok()
        if "ControlGroup" in args:
            return ok("/../../etc\n")
        if "LoadState" in args:
            return ok("not-found\n")
        return ok()

    def forbidden(*args):
        raise AssertionError("unsafe access")

    report = run_child_probe(
        run=run, read=forbidden, write=forbidden, platform="linux", uid=1000
    )
    assert report.checks["cgroup_path"] is CheckState.FAIL
    assert report.checks["cleanup"] is CheckState.UNVERIFIED
    assert not report.ready


def test_start_timeout_stops_only_unique_test_service():
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[0] == "systemd-run":
            raise subprocess.TimeoutExpired(args, 5)
        if "LoadState" in args:
            return ok("not-found\n")
        return ok()

    report = run_child_probe(run=run, platform="linux", uid=1000)
    assert report.checks["unit_started"] is CheckState.FAIL
    assert report.checks["cleanup"] is CheckState.UNVERIFIED
    assert any("stop" in c and report.unit in c for c in calls)
    assert not report.ready


def test_other_platform_refused_before_side_effects():
    def forbidden(*args, **kwargs):
        raise AssertionError("must not run")

    report = run_child_probe(run=forbidden, platform="darwin", uid=1000)
    assert report.checks["host"] is CheckState.FAIL
    assert report.unit is None
