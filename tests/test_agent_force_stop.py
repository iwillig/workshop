import os
import subprocess
import sys
import threading
import time

import pytest

from workshop.agent.supervised import SupervisedAgent


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_textual_ctrl_c_stops_supervised_worker(tmp_path):
    import asyncio
    from workshop.agent.live_view import AgentLiveView

    started = tmp_path / "started"
    script = tmp_path / "worker.py"
    script.write_text(
        "import pathlib,sys,time\npathlib.Path(sys.argv[1]).touch()\ntime.sleep(60)\n"
    )
    agent = SupervisedAgent({}, command=[sys.executable, str(script), str(started)])

    async def run():
        app = AgentLiveView(agent, "task")
        async with app.run_test() as pilot:
            for _ in range(100):
                if started.exists():
                    break
                await pilot.pause(0.05)
            assert started.exists()
            now = time.monotonic()
            await pilot.press("ctrl+c")
            for _ in range(60):
                if app.return_value is not None:
                    break
                await pilot.pause(0.05)
            assert app.return_value["result"]["exit_status"] == "UserInterruption"
            assert time.monotonic() - now < 3

    try:
        asyncio.run(run())
    finally:
        agent.cancel()


@pytest.mark.skipif(os.name != "posix", reason="POSIX pseudo-terminal")
def test_ctrl_c_in_real_tty_stops_worker_and_restores_terminal(tmp_path):
    import fcntl
    import pty
    import termios

    started = tmp_path / "started"
    module = tmp_path / "blocking_model.py"
    module.write_text(f"""\
import os, pathlib, time
from types import SimpleNamespace
class Model:
    config = SimpleNamespace(protocol="native")
    def __init__(self, **kwargs): pass
    def reset(self): pass
    def get_template_vars(self): return {{}}
    def format_message(self, **kwargs): return kwargs
    def serialize(self): return {{}}
    def query(self, messages):
        pathlib.Path({str(started)!r}).write_text(str(os.getpid()))
        time.sleep(60)
""")
    config = tmp_path / "agent.yaml"
    config.write_text("model:\n  model_class: blocking_model.Model\n")
    master, slave = pty.openpty()
    original = termios.tcgetattr(slave)
    env = os.environ | {
        "PYTHONPATH": str(tmp_path) + os.pathsep + os.getcwd(),
        "TERM": "xterm-256color",
    }

    def attach_tty():
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from workshop.cli import cli; cli()",
            "agent",
            "run",
            "--task",
            "test",
            "--config",
            str(config),
        ],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
        preexec_fn=attach_tty,
        pass_fds=(slave,),
    )
    import select

    captured = bytearray()
    done = threading.Event()

    def drain():
        while not done.is_set():
            ready, _, _ = select.select([master], [], [], 0.1)
            if ready:
                try:
                    captured.extend(os.read(master, 4096))
                except OSError:
                    break

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    try:
        deadline = time.monotonic() + 10
        while (
            not started.exists()
            and time.monotonic() < deadline
            and process.poll() is None
        ):
            time.sleep(0.05)
        assert started.exists(), "agent did not start"
        while b"Ctrl+C: stop now" not in captured and time.monotonic() < deadline:
            time.sleep(0.05)
        assert b"Ctrl+C: stop now" in captured, "live view did not render"
        now = time.monotonic()
        os.write(master, bytes([3]))
        try:
            code = process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pytest.fail(f"timed out; tty output: {bytes(captured)[-500:]!r}")
        assert code == 130
        assert time.monotonic() - now < 5
        assert termios.tcgetattr(slave) == original
    finally:
        if process.poll() is None:
            if started.exists():
                try:
                    os.killpg(int(started.read_text()), 9)
                except ProcessLookupError:
                    pass
            process.kill()
            process.wait(timeout=5)
        done.set()
        reader.join(timeout=1)
        os.close(master)
        os.close(slave)


def test_worker_runs_agent_and_forwards_progress(tmp_path, monkeypatch):
    module = tmp_path / "fake_agent_model.py"
    module.write_text("""\
from types import SimpleNamespace
class Model:
    config = SimpleNamespace(protocol="native")
    def __init__(self, **kwargs): pass
    def reset(self): pass
    def get_template_vars(self): return {}
    def format_message(self, **kwargs): return kwargs
    def serialize(self): return {}
    def query(self, messages):
        return {"role": "assistant", "content": "done", "extra": {"native_final": True, "actions": [], "usage": {"input": 10, "output": 2}}}
""")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path) + os.pathsep + os.getcwd())
    agent = SupervisedAgent(
        {
            "agent": {"agent_class": "interactive"},
            "model": {"model_class": "fake_agent_model.Model"},
        }
    )
    events = []
    agent.progress_sink = events.append
    result = agent.run("task")
    assert result["exit_status"] == "Submitted"
    assert result["submission"] == "done"
    assert any("input 10" in event for event in events)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_force_stop_interrupts_blocked_worker(tmp_path):
    started = tmp_path / "started"
    script = tmp_path / "worker.py"
    script.write_text(
        "import pathlib, sys, time\npathlib.Path(sys.argv[1]).write_text('started')\ntime.sleep(60)\n"
    )
    agent = SupervisedAgent({}, command=[sys.executable, str(script), str(started)])
    result = []
    thread = threading.Thread(target=lambda: result.append(agent.run("task")))
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert started.exists()
        now = time.monotonic()
        agent.cancel()
        thread.join(timeout=3)
        assert not thread.is_alive()
        assert time.monotonic() - now < 3
        assert result[0]["exit_status"] == "UserInterruption"
    finally:
        agent.cancel()
        thread.join(timeout=3)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_force_stop_attempts_docker_cleanup(tmp_path):
    marker = tmp_path / "cleanup"
    executable = tmp_path / "docker"
    executable.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > '{marker}'\n")
    executable.chmod(0o755)
    started = tmp_path / "started"
    script = tmp_path / "worker.py"
    script.write_text(
        "import pathlib,sys,time\npathlib.Path(sys.argv[1]).touch()\ntime.sleep(60)\n"
    )
    agent = SupervisedAgent(
        {"environment": {"environment_class": "docker", "executable": str(executable)}},
        command=[sys.executable, str(script), str(started)],
    )
    thread = threading.Thread(target=lambda: agent.run("task"))
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert started.exists()
        agent.cancel()
        thread.join(timeout=3)
        deadline = time.monotonic() + 3
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.read_text().splitlines() == ["rm", "-f", agent._container_name]
    finally:
        agent.cancel()
        thread.join(timeout=3)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_force_stop_kills_detached_child(tmp_path):
    started = tmp_path / "child"
    script = tmp_path / "worker.py"
    script.write_text("""\
import pathlib, subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
pathlib.Path(sys.argv[1]).write_text(str(child.pid))
time.sleep(60)
""")
    agent = SupervisedAgent({}, command=[sys.executable, str(script), str(started)])
    thread = threading.Thread(target=lambda: agent.run("task"))
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not started.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert started.exists()
        pid = int(started.read_text())
        agent.cancel()
        thread.join(timeout=3)
        assert not thread.is_alive()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = subprocess.run(
                ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True
            ).stdout.strip()
            if not state or state.startswith("Z"):
                break
            time.sleep(0.05)
        assert not state or state.startswith("Z")
    finally:
        agent.cancel()
        thread.join(timeout=3)
