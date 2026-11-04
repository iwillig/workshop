"""Synthetic localhost integration; not proof of network isolation."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from llm.default_plugins.openai_models import Chat

from workshop.agent_benchmark.local import run_suite
from workshop.agent_eval.review_runner import review_trace


def test_review_uses_real_llm_client_against_synthetic_loopback(
    tmp_path, monkeypatch
):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            request = json.loads(self.rfile.read(length))
            requests.append((self.path, request))
            if request.get("stream"):
                chunk = {
                    "id": "synthetic-completion",
                    "object": "chat.completion.chunk",
                    "created": 0,
                    "model": "synthetic-model",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "content": json.dumps(
                                    {
                                        "observations": [
                                            "The agent read the file."
                                        ]
                                    }
                                )
                            },
                            "finish_reason": "stop",
                        }
                    ],
                }
                payload = (
                    "data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n"
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            payload = json.dumps(
                {
                    "id": "synthetic-completion",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "synthetic-model",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(
                                    {
                                        "observations": [
                                            "The agent read the file."
                                        ]
                                    }
                                ),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        backend = Chat(
            model_id="synthetic-reviewer",
            model_name="synthetic-model",
            api_base=f"http://127.0.0.1:{port}/v1",
            key="synthetic-key",
            can_stream=False,
            supports_tools=True,
        )
        monkeypatch.setattr("llm.get_model", lambda name: backend)
        root = tmp_path / "private"
        report = run_suite(
            "review-v1",
            {},
            "reviewer",
            root,
            local=True,
            capture_trace=True,
            execute=lambda *args: {
                "exit_status": "Submitted",
                "submission": "done",
                "benchmark_trajectory": {
                    "messages": [
                        {"role": "user", "content": "synthetic trace only"}
                    ]
                },
            },
        )
        review = review_trace(
            root,
            report["run"]["id"],
            {
                "model": {
                    "model_name": "synthetic-reviewer",
                    "protocol": "native",
                    "retry_attempts": 1,
                }
            },
        )
        assert review["status"] == "completed", review["diagnostic"]
        assert review["observations"][0]["text"] == "The agent read the file."
        assert len(requests) == 1
        path, request = requests[0]
        assert path == "/v1/chat/completions"
        assert "synthetic trace only" in json.dumps(request)
        assert not request.get("tools")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
