"""Subprocess entry point for the Textual agent view; not a public CLI."""

import contextlib
import json
import sys
import threading


def main():
    protocol = sys.stdout
    lock = threading.Lock()

    def send(event):
        with lock:
            protocol.write(json.dumps(event, default=str) + "\n")
            protocol.flush()

    try:
        request = json.loads(sys.stdin.readline())
        with contextlib.redirect_stdout(sys.stderr):
            from workshop.agent_config import build_agent

            agent = build_agent(request["config"])
            from workshop.agent.environments import DockerEnvironment

            if isinstance(agent.env, DockerEnvironment):
                agent.env.supervised_container_name = request["container_name"]
            agent.progress_sink = lambda text: send(
                {"type": "progress", "text": text}
            )
            result = agent.run(request["task"])
        send({"type": "result", "result": result})
    except Exception as exc:
        notes = "\n".join(getattr(exc, "__notes__", []))
        message = f"{type(exc).__name__}: {exc}"
        send(
            {
                "type": "error",
                "message": f"{message}\n{notes}" if notes else message,
            }
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
