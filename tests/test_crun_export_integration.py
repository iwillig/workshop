"""Opt-in fixed crun/tmpfs/cgroup feasibility test; not a sandbox."""

import json
import os
import select
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from workshop.agent_benchmark.crun_cgroup_probe import _show, _valid_group
from workshop.agent_benchmark.crun_child_cgroup_probe import (
    _SCRIPT as CHILD_SCRIPT,
    _populated_event_state,
)
from workshop.agent_benchmark.crun_export_probe import read_synthetic
from workshop.agent_benchmark.preflight import CheckState


@pytest.mark.skipif(
    os.environ.get("WORKSHOP_CRUN_EXPORT_PROBE") != "1",
    reason="set WORKSHOP_CRUN_EXPORT_PROBE=1 for disposable crun test",
)
def test_frozen_synthetic_tmpfs_export_from_rootless_crun(tmp_path):
    """Exercise a fixed diagnostic, not an agent artifact collector."""
    assert os.geteuid() != 0 and hasattr(os, "pidfd_open")
    root = tmp_path / "rootfs"
    (root / "tmp").mkdir(parents=True)
    (root / "dev").mkdir()
    (root / "lib64").mkdir()
    state_root = tmp_path / "state"
    state_root.mkdir(mode=0o700)
    source = tmp_path / "probe.c"
    source.write_text("""\
#include <fcntl.h>
#include <unistd.h>
int main(void) {
    const char data[] = "synthetic benchmark artifact\\n";
    int fd = open("/tmp/artifact.txt", O_CREAT|O_EXCL|O_WRONLY, 0600);
    if (fd < 0 || write(fd, data, sizeof(data)-1) != sizeof(data)-1) return 2;
    if (close(fd)) return 3;
    sleep(25);
    return 0;
}
""")
    subprocess.run(
        ["gcc", "-O2", "-o", str(root / "probe"), str(source)],
        capture_output=True,
        timeout=15,
        check=True,
    )
    for filename in ("libc.so.6", "ld-linux-x86-64.so.2"):
        shutil.copyfile(Path("/lib64") / filename, root / "lib64" / filename)
    (root / "lib64" / "ld-linux-x86-64.so.2").chmod(0o755)
    config = {
        "ociVersion": "1.0.0",
        "process": {
            "terminal": False,
            "user": {"uid": 0, "gid": 0},
            "args": ["/probe"],
            "env": ["PATH=/bin"],
            "cwd": "/",
            "noNewPrivileges": True,
            "capabilities": {
                key: []
                for key in (
                    "bounding",
                    "effective",
                    "inheritable",
                    "permitted",
                    "ambient",
                )
            },
        },
        "root": {"path": "rootfs", "readonly": True},
        "mounts": [
            {
                "destination": "/tmp",
                "type": "tmpfs",
                "source": "tmpfs",
                "options": [
                    "rw",
                    "nosuid",
                    "nodev",
                    "noexec",
                    "size=1m",
                    "nr_inodes=128",
                    "mode=0700",
                ],
            }
        ],
        "linux": {
            "namespaces": [
                {"type": kind}
                for kind in ("user", "mount", "pid", "network", "ipc", "uts")
            ]
        },
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    unit = "workshop-export-" + uuid.uuid4().hex + ".service"
    container_id = "workshop-export-" + uuid.uuid4().hex
    script = CHILD_SCRIPT.replace(
        "/usr/bin/sleep 30 &\nwait",
        'exec /usr/bin/crun --root "$3" --rootless=true '
        '--cgroup-manager=disabled run --bundle "$2" "$4"',
    )
    assert script != CHILD_SCRIPT
    command = [
        "systemd-run",
        "--user",
        "--quiet",
        "--collect",
        "--unit=" + unit,
        "--property=Type=exec",
        "--property=Delegate=yes",
        "--property=KillMode=control-group",
        "--property=MemoryMax=64M",
        "--property=TasksMax=32",
        "--property=CPUQuota=50%",
        "--property=TimeoutStopSec=2s",
        "--property=RuntimeMaxSec=30s",
        "/usr/bin/bash",
        "-c",
        script,
        "--",
        unit,
        str(tmp_path),
        str(state_root),
        container_id,
    ]
    group = None
    child = None
    frozen = False
    pidfd = None
    try:
        subprocess.run(
            command, capture_output=True, text=True, timeout=5, check=True
        )
        group = _show(subprocess.run, unit, "ControlGroup")
        assert _valid_group(group, os.geteuid(), unit)
        child = Path("/sys/fs/cgroup") / group.lstrip("/") / "workload"
        deadline = time.monotonic() + 12
        pid = None
        while time.monotonic() < deadline:
            result = subprocess.run(
                [
                    "crun",
                    "--root",
                    str(state_root),
                    "--rootless=true",
                    "state",
                    container_id,
                ],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if result.returncode == 0:
                state = json.loads(result.stdout)
                candidate = state.get("pid")
                if type(candidate) is int and candidate > 0:
                    pid = candidate
                    try:
                        stat = Path(
                            f"/proc/{pid}/root/tmp/artifact.txt"
                        ).stat()
                        if stat.st_size:
                            break
                    except FileNotFoundError:
                        pass
            time.sleep(0.05)
        assert pid is not None, "crun did not start the diagnostic init"
        pidfd = os.pidfd_open(pid)
        member = Path(f"/proc/{pid}/cgroup").read_text().strip()
        assert member == "0::" + group + "/workload"
        assert str(pid) in (child / "cgroup.procs").read_text().split()
        frozen = True
        child.joinpath("cgroup.freeze").write_text("1")
        assert (
            _populated_event_state(lambda p: p.read_text(), child, "1")
            is CheckState.PASS
        )
        fd = os.open(
            f"/proc/{pid}/root/tmp",
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        try:
            assert read_synthetic(fd) == b"synthetic benchmark artifact\n"
        finally:
            os.close(fd)
        assert (
            _populated_event_state(lambda p: p.read_text(), child, "1")
            is CheckState.PASS
        )
        assert not select.select([pidfd], [], [], 0)[0], (
            "diagnostic init exited"
        )
    finally:
        if pidfd is not None:
            os.close(pidfd)
        if frozen and child is not None:
            try:
                child.joinpath("cgroup.freeze").write_text("0")
            except OSError:
                pass
        try:
            subprocess.run(
                [
                    "systemctl",
                    "--user",
                    "kill",
                    "--kill-whom=all",
                    "--signal=KILL",
                    unit,
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except OSError, subprocess.SubprocessError:
            pass
        try:
            subprocess.run(
                ["systemctl", "--user", "stop", unit],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except OSError, subprocess.SubprocessError:
            pass
        try:
            subprocess.run(
                [
                    "crun",
                    "--root",
                    str(state_root),
                    "--rootless=true",
                    "delete",
                    "--force",
                    container_id,
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except OSError, subprocess.SubprocessError:
            pass
        assert _show(subprocess.run, unit, "LoadState") == "not-found"
        if group and _valid_group(group, os.geteuid(), unit):
            assert not (Path("/sys/fs/cgroup") / group.lstrip("/")).exists()
        listed = subprocess.run(
            [
                "crun",
                "--root",
                str(state_root),
                "--rootless=true",
                "list",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        assert listed.returncode == 0
        assert container_id not in listed.stdout
