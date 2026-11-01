"""Manage MCP sessions for a synchronous agent run."""

import asyncio
import threading
from concurrent.futures import Future
from contextlib import AsyncExitStack

from workshop.agent.mcp_client import MCPConnection, MCPToolAdapter


class MCPRuntime:
    def __init__(self, servers):
        self.servers = dict(servers)
        self.tools = []
        self.adapters = {}
        self._ready = Future()
        self._thread = None
        self._loop = None
        self._stop = None

    def __enter__(self):
        self._ready = Future()
        self.tools = []
        self.adapters = {}
        self._loop = None
        self._stop = None
        self._thread = threading.Thread(
            target=self._run, name="workshop-mcp", daemon=True
        )
        self._thread.start()
        try:
            self._ready.result(timeout=60)
        except BaseException:
            if self._loop and self._stop:
                self._loop.call_soon_threadsafe(self._stop.set)
            self._thread.join(timeout=5)
            raise
        return self

    def _run(self):
        try:
            asyncio.run(self._serve())
        except BaseException as exc:
            if not self._ready.done():
                self._ready.set_exception(exc)

    async def _serve(self):
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        async with AsyncExitStack() as stack:
            for name, config in self.servers.items():
                connection = await stack.enter_async_context(
                    MCPConnection(config)
                )
                adapter = MCPToolAdapter(name, connection)
                tools = await adapter.discover()
                self.tools.extend(tools)
                self.adapters[name] = adapter
            self._ready.set_result(None)
            await self._stop.wait()

    def execute(self, action):
        name = action.get("tool", "")
        adapter = next(
            (a for a in self.adapters.values() if name.startswith(a.prefix)),
            None,
        )
        if adapter is None:
            return {
                "output": f"Unknown tool: {name}",
                "returncode": 1,
                "exception_info": "",
            }
        future = asyncio.run_coroutine_threadsafe(
            adapter.call(name, action.get("arguments", {})), self._loop
        )
        try:
            output = future.result(timeout=60)
            return {"output": output, "returncode": 0, "exception_info": ""}
        except Exception as exc:
            future.cancel()
            return {
                "output": f"MCP tool failed: {type(exc).__name__}: {exc}",
                "returncode": 1,
                "exception_info": "",
            }

    def __exit__(self, *args):
        self._loop.call_soon_threadsafe(self._stop.set)
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            raise RuntimeError("MCP session did not close")
