"""Disposable systemd user-service cgroup diagnostic, not a sandbox."""

import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from workshop.agent_benchmark.preflight import CheckState, PreflightReport


@dataclass(frozen=True)
class CgroupProbeReport(PreflightReport):
    unit: str | None = None


def run_cgroup_probe(
    *, run=None, read=None, exists=None, platform=None, uid=None
):
    """Inspect limits and freeze/thaw one unique transient user service."""
    run = run or subprocess.run
    read = read or (lambda path: path.read_text(encoding="utf-8"))
    exists = exists or _exists
    platform = sys.platform if platform is None else platform
    uid = os.geteuid() if uid is None else uid
    names = (
        "host",
        "unit_started",
        "delegation",
        "cgroup_path",
        "memory",
        "pids",
        "cpu",
        "freeze",
        "thaw",
        "cleanup",
    )
    checks = {name: CheckState.UNVERIFIED for name in names}
    if platform != "linux" or type(uid) is not int or uid <= 0:
        checks["host"] = CheckState.FAIL
        return CgroupProbeReport(checks)
    checks["host"] = CheckState.PASS
    unit = "workshop-cgroup-" + uuid.uuid4().hex + ".service"
    command = [
        "systemd-run",
        "--user",
        "--quiet",
        "--collect",
        "--unit=" + unit,
        "--property=Type=exec",
        "--property=Delegate=yes",
        "--property=MemoryMax=64M",
        "--property=TasksMax=32",
        "--property=CPUQuota=50%",
        "--property=RuntimeMaxSec=15s",
        "/usr/bin/sleep",
        "15",
    ]
    cgroup = None
    freeze_attempted = False
    try:
        started = _invoke(run, command)
        if started is None or started.returncode != 0:
            checks["unit_started"] = CheckState.FAIL
            return CgroupProbeReport(checks, unit)
        checks["unit_started"] = CheckState.PASS
        group = _show(run, unit, "ControlGroup")
        if not _valid_group(group, uid, unit):
            checks["cgroup_path"] = CheckState.FAIL
            return CgroupProbeReport(checks, unit)
        checks["cgroup_path"] = CheckState.PASS
        cgroup = Path("/sys/fs/cgroup") / group.lstrip("/")
        delegated = _show(run, unit, "Delegate")
        if delegated in {"yes", "no"}:
            checks["delegation"] = (
                CheckState.PASS if delegated == "yes" else CheckState.FAIL
            )
        for check, filename, expected in (
            ("memory", "memory.max", "67108864"),
            ("pids", "pids.max", "32"),
            ("cpu", "cpu.max", "50000 100000"),
        ):
            try:
                value = read(cgroup / filename).strip()
                checks[check] = (
                    CheckState.PASS if value == expected else CheckState.FAIL
                )
            except OSError, ValueError:
                pass
        freeze_attempted = True
        response = _invoke(run, ["systemctl", "--user", "freeze", unit])
        if response is None or response.returncode != 0:
            checks["freeze"] = CheckState.FAIL
        else:
            checks["freeze"] = _event_state(read, cgroup, "1")
    finally:
        if freeze_attempted:
            response = _invoke(run, ["systemctl", "--user", "thaw", unit])
            if response is None or response.returncode != 0:
                checks["thaw"] = CheckState.FAIL
            elif cgroup is not None:
                checks["thaw"] = _event_state(read, cgroup, "0")
        _invoke(run, ["systemctl", "--user", "stop", unit])
        deadline = time.monotonic() + 3
        while True:
            state = _show(run, unit, "LoadState")
            if state == "not-found":
                if (
                    checks["unit_started"] is CheckState.PASS
                    and cgroup is not None
                ):
                    try:
                        checks["cleanup"] = (
                            CheckState.FAIL
                            if exists(cgroup)
                            else CheckState.PASS
                        )
                    except OSError:
                        pass
                break
            if time.monotonic() >= deadline:
                if state in {"loaded", "masked"}:
                    checks["cleanup"] = CheckState.FAIL
                break
            time.sleep(0.05)
    return CgroupProbeReport(checks, unit)


def _exists(path):
    try:
        os.stat(path)
        return True
    except FileNotFoundError:
        return False


def _invoke(run, args):
    try:
        return run(
            args, capture_output=True, text=True, timeout=5, check=False
        )
    except OSError, subprocess.SubprocessError:
        return None


def _show(run, unit, prop):
    result = _invoke(
        run,
        ["systemctl", "--user", "show", unit, "--property", prop, "--value"],
    )
    if result is None or result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value if "\n" not in value else None


def _valid_group(value, uid, unit):
    if not isinstance(value, str) or not value.startswith("/"):
        return False
    parts = PurePosixPath(value).parts
    return (
        ".." not in parts
        and len(parts) >= 4
        and parts[1] == "user.slice"
        and parts[2] == f"user-{uid}.slice"
        and parts[-1] == unit
    )


def _event_state(read, cgroup, expected):
    deadline = time.monotonic() + 2
    observed = False
    while True:
        try:
            lines = read(cgroup / "cgroup.events").splitlines()
            values = [
                line.split() for line in lines if line.startswith("frozen ")
            ]
            if (
                len(values) == 1
                and len(values[0]) == 2
                and values[0][1] in {"0", "1"}
            ):
                observed = True
                if values[0][1] == expected:
                    return CheckState.PASS
        except OSError, ValueError:
            pass
        if time.monotonic() >= deadline:
            return CheckState.FAIL if observed else CheckState.UNVERIFIED
        time.sleep(0.05)
