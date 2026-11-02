"""Opt-in fixed inherited-FD experiment; not a verifier security boundary."""

import json
import os
import select
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest


_HELPER = """\
import os, sys
fd = int(sys.argv[1])
os.dup2(fd, 3, inheritable=True)
if fd != 3: os.close(fd)
os.execv('/usr/bin/crun', ['/usr/bin/crun', '--root', sys.argv[2],
         '--rootless=true', '--cgroup-manager=disabled', 'run',
         '--preserve-fds=1', '--bundle', sys.argv[3], sys.argv[4]])
"""

_SOURCE = r"""
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
int main(int argc, char **argv) {
    if (argc > 1 && strcmp(argv[1], "after") == 0) {
        if (fcntl(3, F_GETFD) != -1 || errno != EBADF) return 5;
        write(1, "RELEASED_CLOSED\n", 16);
        return 0;
    }
    if (argc > 1 && strcmp(argv[1], "forged") == 0)
        write(1, "FORGED_VERIFIED\n", 16);
    write(1, "READY\n", 6);
    char byte = 0;
    int n = read(3, &byte, 1);
    close(3);
    if (n != 1 || byte != 'R') {
        write(1, "DENIED\n", 7);
        return 0;
    }
    execl("/verifier", "/verifier", "after", (char *)0);
    return 6;
}
"""


def _read_prelude(fd, line_count, timeout):
    deadline = time.monotonic() + timeout
    data = bytearray()
    while data.count(b"\n") < line_count:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("verifier prelude timed out")
        ready, _, _ = select.select([fd], [], [], remaining)
        if not ready:
            raise TimeoutError("verifier prelude timed out")
        chunk = os.read(fd, 4097 - len(data))
        if not chunk:
            raise RuntimeError("verifier closed before prelude")
        data.extend(chunk)
        if len(data) > 4096:
            raise ValueError("verifier prelude too large")
    return data.splitlines(keepends=True)


def test_prelude_reader_times_out_on_partial_line():
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, b"PARTIAL")
        with pytest.raises(TimeoutError):
            _read_prelude(read_fd, 1, timeout=0.05)
    finally:
        os.close(read_fd)
        os.close(write_fd)


@pytest.mark.skipif(
    os.environ.get("WORKSHOP_CRUN_RELEASE_PROBE") != "1",
    reason="set WORKSHOP_CRUN_RELEASE_PROBE=1 for disposable crun test",
)
@pytest.mark.parametrize(
    "scenario", ["denied", "approved", "mismatch", "invalid", "forged"]
)
def test_fixed_crun_verifier_inherited_fd(tmp_path, scenario):
    """Observe a fixed pipe protocol, not actual policy authentication."""
    assert os.geteuid() != 0 and hasattr(os, "pidfd_open")
    root = tmp_path / "rootfs"
    (root / "dev").mkdir(parents=True)
    (root / "lib64").mkdir()
    state_root = tmp_path / "state"
    state_root.mkdir(mode=0o700)
    source = tmp_path / "verifier.c"
    source.write_text(_SOURCE)
    subprocess.run(
        ["gcc", "-O2", "-o", str(root / "verifier"), str(source)],
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
            "args": ["/verifier", "forged"]
            if scenario == "forged"
            else ["/verifier"],
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
        "mounts": [],
        "linux": {
            "namespaces": [
                {"type": kind}
                for kind in ("user", "mount", "pid", "network", "ipc", "uts")
            ]
        },
    }
    (tmp_path / "config.json").write_text(json.dumps(config))
    container_id = "workshop-release-" + uuid.uuid4().hex
    read_fd, write_fd = os.pipe()
    process = None
    pidfd = None
    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-c",
                _HELPER,
                str(read_fd),
                str(state_root),
                str(tmp_path),
                container_id,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(read_fd,),
            start_new_session=True,
        )
        os.close(read_fd)
        read_fd = None
        expected_prelude = (
            [b"FORGED_VERIFIED\n", b"READY\n"]
            if scenario == "forged"
            else [b"READY\n"]
        )
        prelude = _read_prelude(
            process.stdout.fileno(), len(expected_prelude), 8
        )
        assert prelude == expected_prelude
        state = subprocess.run(
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
            timeout=5,
            check=True,
        )
        pid = json.loads(state.stdout)["pid"]
        assert type(pid) is int and pid > 0
        pidfd = os.pidfd_open(pid)
        assert not select.select([pidfd], [], [], 0)[0]
        # Simulated only: this is not a host policy or process identity check.
        expected_pid = pid + 1 if scenario == "mismatch" else pid
        simulated_approval = scenario in {"approved", "mismatch"}
        if simulated_approval and expected_pid == pid:
            os.write(write_fd, b"R")
        elif scenario == "invalid":
            os.write(write_fd, b"X")
        os.close(write_fd)
        write_fd = None
        output, errors = process.communicate(timeout=8)
        assert process.returncode == 0, errors.decode(errors="replace")
        assert output == (
            b"RELEASED_CLOSED\n" if scenario == "approved" else b"DENIED\n"
        )
    finally:
        for fd in (read_fd, write_fd):
            if fd is not None:
                os.close(fd)
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
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
        init_exited = True
        if pidfd is not None:
            init_exited = bool(select.select([pidfd], [], [], 3)[0])
            os.close(pidfd)
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
        assert init_exited, "fixed verifier process still alive"
