"""Fixed-process inherited-pipe experiment; not a verifier or sandbox."""

import os
import select
import subprocess
import sys

from workshop.agent_benchmark.preflight import CheckState, PreflightReport


# Fixed test program: it never starts an agent or executes caller input.
_CHILD = r"""
import os, sys, time
fd = int(sys.argv[1])
mode = sys.argv[2]
if mode == "forged":
    os.write(1, b"FORGED_VERIFIED\n")
if mode == "closed":
    os.close(fd)
    os.write(1, b"CLOSED\n")
    time.sleep(0.5)
    raise SystemExit(2)
message = os.read(fd, 1)
os.close(fd)
if message == b"R":
    os.write(1, b"FIXED_TEST_RELEASED\n")
    raise SystemExit(0)
raise SystemExit(2)
"""


def run_release_probe(
    *,
    simulated_checks_pass=False,
    simulate_identity_mismatch=False,
    simulate_closed_channel=False,
    simulate_forged_report=False,
):
    """Run a fixed child with simulated checks; never authorizes benchmarks."""
    options = (
        simulated_checks_pass,
        simulate_identity_mismatch,
        simulate_closed_channel,
        simulate_forged_report,
    )
    if any(type(value) is not bool for value in options):
        raise TypeError("simulation options must be booleans")
    checks = {
        name: CheckState.UNVERIFIED
        for name in (
            "identity",
            "released",
            "worker_exit",
            "fd_cleanup",
        )
    }
    checks["released"] = CheckState.FAIL
    read_fd = write_fd = pidfd = None
    process = None
    cleanup_ok = True
    sent_release = False
    try:
        if sys.platform != "linux" or not hasattr(os, "pidfd_open"):
            return PreflightReport(checks)
        read_fd, write_fd = os.pipe()
        mode = (
            "closed"
            if simulate_closed_channel
            else "forged"
            if simulate_forged_report
            else "normal"
        )
        process = subprocess.Popen(
            [sys.executable, "-I", "-c", _CHILD, str(read_fd), mode],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            pass_fds=(read_fd,),
            start_new_session=True,
        )
        os.close(read_fd)
        read_fd = None
        if simulate_closed_channel:
            ready, _, _ = select.select([process.stdout], [], [], 2)
            if not ready or process.stdout.readline() != b"CLOSED\n":
                return PreflightReport(checks)
        try:
            pidfd = os.pidfd_open(process.pid)
            exited, _, _ = select.select([pidfd], [], [], 0)
            expected_pid = (
                process.pid + 1 if simulate_identity_mismatch else process.pid
            )
            checks["identity"] = (
                CheckState.PASS
                if not exited and expected_pid == process.pid
                else CheckState.FAIL
            )
        except OSError:
            pass
        authorized = (
            simulated_checks_pass and checks["identity"] is CheckState.PASS
        )
        if authorized:
            try:
                sent_release = os.write(write_fd, b"R") == 1
            except OSError:
                pass
        os.close(write_fd)
        write_fd = None
        try:
            stdout, _ = process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=3)
            return PreflightReport(checks)
        lines = stdout.splitlines()
        if (
            sent_release
            and process.returncode == 0
            and lines.count(b"FIXED_TEST_RELEASED") == 1
        ):
            checks["released"] = CheckState.PASS
        if process.returncode in (0, 2):
            checks["worker_exit"] = CheckState.PASS
    except OSError, subprocess.SubprocessError:
        pass
    finally:
        for fd in (read_fd, write_fd, pidfd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    cleanup_ok = False
        if process is not None:
            if process.poll() is None:
                process.kill()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    cleanup_ok = False
            if process.stdout is not None:
                process.stdout.close()
        checks["fd_cleanup"] = (
            CheckState.PASS if cleanup_ok else CheckState.FAIL
        )
    return PreflightReport(checks)
