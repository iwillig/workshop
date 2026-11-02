"""Experimental fake-provider broker; not a sandbox security boundary."""

import asyncio
import hmac
import inspect
import json
import os
import re
import secrets
import stat
from pathlib import Path


class ModelBroker:
    """Run a bounded text protocol with an injected async test provider."""

    def __init__(
        self, directory, provider, *, max_requests=20, timeout_seconds=30
    ):
        if not 1 <= max_requests <= 20 or type(max_requests) is not int:
            raise ValueError("max_requests must be between 1 and 20")
        if not 0 < timeout_seconds <= 30:
            raise ValueError("timeout_seconds must be positive and at most 30")
        if not inspect.iscoroutinefunction(provider):
            raise TypeError("provider must be an async function")
        self.socket_path = Path(directory) / "broker.sock"
        self.provider = provider
        self.max_requests = max_requests
        self.timeout_seconds = timeout_seconds
        self.token = secrets.token_hex(32)
        self._requests = 0
        self._server = None
        self._started = False
        self._connections = set()
        self._providers = set()
        self._active = False
        self._socket_identity = None

    async def __aenter__(self):
        if self._started:
            raise RuntimeError("broker instances are single-use")
        self._started = True
        directory = self.socket_path.parent
        info = directory.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
        ):
            raise PermissionError("broker directory must be owner-only")
        if os.path.lexists(self.socket_path):
            raise FileExistsError(self.socket_path)
        self._server = await asyncio.start_unix_server(
            self._handle,
            path=str(self.socket_path),
            limit=256 * 1024 + 1,
            cleanup_socket=False,
        )
        try:
            info = self.socket_path.lstat()
            self._socket_identity = (info.st_dev, info.st_ino)
            os.chmod(self.socket_path, 0o600)
        except BaseException:
            await self.__aexit__(None, None, None)
            raise
        return self

    async def __aexit__(self, *args):
        self._server.close()
        for task in self._connections | self._providers:
            task.cancel()
        tasks = self._connections | self._providers
        pending = set()
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=0.2)
        if not pending:
            await self._server.wait_closed()
        try:
            info = self.socket_path.lstat()
            if (info.st_dev, info.st_ino) == self._socket_identity:
                self.socket_path.unlink()
        except FileNotFoundError:
            pass
        if pending:
            raise RuntimeError("broker tasks did not stop after cancellation")

    async def _handle(self, reader, writer):
        task = asyncio.current_task()
        if len(self._connections) >= 8:
            writer.close()
            await writer.wait_closed()
            return
        self._connections.add(task)
        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        try:
            try:
                line = await asyncio.wait_for(
                    reader.readline(), self.timeout_seconds
                )
                if len(line) > 256 * 1024 or not line.endswith(b"\n"):
                    raise ValueError("invalid frame")
                data = json.loads(line, object_pairs_hook=_unique_object)
                messages = self._validate(data)
            except ValueError, TypeError, UnicodeError, asyncio.TimeoutError:
                await self._send(
                    writer, {"ok": False, "error": "invalid request"}
                )
                return
            if self._active:
                await self._send(writer, {"ok": False, "error": "busy"})
                return
            if self._requests >= self.max_requests:
                await self._send(writer, {"ok": False, "error": "limit"})
                return
            self._requests += 1
            self._active = True
            provider_task = asyncio.create_task(self.provider(messages))
            self._providers.add(provider_task)

            def finished(done):
                self._providers.discard(done)
                self._active = False
                if not done.cancelled():
                    done.exception()

            provider_task.add_done_callback(finished)
            remaining = max(0, deadline - asyncio.get_running_loop().time())
            done, _ = await asyncio.wait({provider_task}, timeout=remaining)
            if not done:
                provider_task.cancel()
                await self._send(writer, {"ok": False, "error": "timeout"})
                return
            try:
                if provider_task.cancelled():
                    raise ValueError("provider cancelled")
                content = provider_task.result()
                if not isinstance(content, str) or len(content) > 1024 * 1024:
                    raise ValueError("invalid response")
                response = {"ok": True, "content": content}
                if len(json.dumps(response).encode()) + 1 > 1024 * 1024:
                    raise ValueError("invalid response")
            except Exception:
                response = {"ok": False, "error": "provider failure"}
            await self._send(writer, response)
        except ConnectionError, OSError:
            pass
        finally:
            self._connections.discard(task)
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError, OSError:
                pass

    def _validate(self, data):
        if not isinstance(data, dict) or set(data) != {
            "version",
            "token",
            "messages",
        }:
            raise ValueError("invalid fields")
        token = data["token"]
        if (
            type(data["version"]) is not int
            or data["version"] != 1
            or not isinstance(token, str)
            or not re.fullmatch(r"[0-9a-f]{64}", token)
            or not hmac.compare_digest(token, self.token)
        ):
            raise ValueError("invalid authentication")
        messages = data["messages"]
        if not isinstance(messages, list) or not messages:
            raise ValueError("invalid messages")
        for message in messages:
            if (
                not isinstance(message, dict)
                or set(message) != {"role", "content"}
                or message["role"] not in ("system", "user", "assistant")
                or not isinstance(message["content"], str)
            ):
                raise ValueError("invalid message")
        return messages

    async def _send(self, writer, data):
        writer.write(json.dumps(data).encode() + b"\n")
        await asyncio.wait_for(writer.drain(), self.timeout_seconds)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result
