"""Disposable loopback server for synthetic GitHub API fixtures.

Trusted local testing only: the server binds to 127.0.0.1 and serves
canned, hash-pinned responses. This is not a network boundary.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FixtureServer:
    """Serve canned JSON responses by exact request path and query."""

    def __init__(self, responses):
        responses = dict(responses)

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = responses.get(self.path)
                status = 200 if body is not None else 404
                payload = json.dumps(
                    body if body is not None else {"message": "Not Found"}
                ).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )

    @property
    def base_url(self):
        host, port = self._server.server_address[:2]
        return f"http://127.0.0.1:{port}"

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def __enter__(self):
        return self.start()

    def __exit__(self, *args):
        self.stop()
