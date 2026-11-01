"""Run the interactive agent in a killable POSIX subprocess."""

import json
import os
import signal
import subprocess
import sys
import threading
import uuid


class SupervisedAgent:
    """Adapt a subprocess worker to the interface consumed by the live view."""

    def __init__(self, config, *, command=None):
        self.config = config
        self.command = command or [
            sys.executable,
            "-m",
            "workshop.agent.live_worker",
        ]
        self.progress_sink = None
        self.stop_event = None
        self._process = None
        self._lock = threading.Lock()
        self._cancelled = False
        self._container_name = f"workshop-agent-{uuid.uuid4().hex}"

    def run(self, task):
        with self._lock:
            if self._cancelled:
                return {"exit_status": "UserInterruption", "submission": ""}
            self._process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                start_new_session=True,
            )
            process = self._process
        try:
            try:
                process.stdin.write(
                    json.dumps(
                        {
                            "config": self.config,
                            "task": task,
                            "container_name": self._container_name,
                        },
                        default=str,
                    )
                    + "\n"
                )
                process.stdin.close()
            except BrokenPipeError:
                pass
            result = None
            error = None
            for line in process.stdout:
                try:
                    event = json.loads(line)
                except ValueError, TypeError:
                    continue
                if event.get("type") == "progress" and self.progress_sink:
                    self.progress_sink(event.get("text", ""))
                elif event.get("type") == "result":
                    result = event.get("result")
                elif event.get("type") == "error":
                    error = event.get("message", "Agent worker failed")
            code = process.wait()
            if self._cancelled:
                return {"exit_status": "UserInterruption", "submission": ""}
            if error:
                raise RuntimeError(error)
            if code != 0 or not isinstance(result, dict):
                raise RuntimeError(
                    f"Agent worker exited without a result (exit {code})"
                )
            return result
        finally:
            process.stdout.close()
            with self._lock:
                self._process = None

    def cancel(self):
        with self._lock:
            self._cancelled = True
            process = self._process
            if process is None or process.poll() is not None:
                return
            pid = process.pid
            # Freeze the worker group before enumerating descendants so the
            # agent cannot start another action while cancellation is underway.
            self._signal_group(pid, signal.SIGSTOP)
            groups = self._descendant_groups(pid)
            for group in groups:
                self._signal_group(group, signal.SIGKILL)
            self._signal_group(pid, signal.SIGKILL)
            environment = self.config.get("environment") or {}
            if environment.get("environment_class") in {
                "docker",
                "workshop.agent.environments.DockerEnvironment",
            }:
                executable = environment.get("executable") or os.environ.get(
                    "WORKSHOP_DOCKER_EXECUTABLE", "docker"
                )
                try:
                    subprocess.Popen(
                        [executable, "rm", "-f", self._container_name],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                except OSError:
                    pass

    @staticmethod
    def _signal_group(group, sig):
        if group == os.getpgrp():
            return
        try:
            os.killpg(group, sig)
        except OSError:
            pass

    @staticmethod
    def _descendant_groups(root):
        try:
            output = subprocess.run(
                ["ps", "-A", "-o", "pid=", "-o", "ppid=", "-o", "pgid="],
                capture_output=True,
                text=True,
                timeout=1,
                check=True,
            ).stdout
        except OSError, subprocess.SubprocessError:
            return set()
        rows = []
        for line in output.splitlines():
            try:
                pid, parent, group = map(int, line.split())
            except ValueError:
                continue
            rows.append((pid, parent, group))
        descendants = {root}
        while True:
            updated = descendants | {
                pid for pid, parent, _ in rows if parent in descendants
            }
            if updated == descendants:
                break
            descendants = updated
        return {
            group
            for pid, _, group in rows
            if pid in descendants and group != root and group != os.getpgrp()
        }
