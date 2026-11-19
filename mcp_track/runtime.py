"""Connects AgentDojo's agent pipeline to the MCP servers.

The model side (LLM adapters, agent loop, fixes of scripts/run_agentdojo.py) is AgentDojo's, exactly as in the IPI
track; only the tools come from MCP: their names, descriptions and input schemas are read with `tools/list` and
every call goes through `tools/call`. The servers run in-process over the SDK's in-memory transport (real
JSON-RPC messages, no subprocesses); a background event loop serves the synchronous pipeline.
"""

import asyncio
import logging
import threading
from contextlib import AsyncExitStack
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import BaseModel

from agentdojo.functions_runtime import Function, FunctionsRuntime

from mcp_track.servers import bizutils, docs, mail, shop
from mcp_track.servers.common import Variant

logging.getLogger("mcp").setLevel(logging.WARNING)

SERVERS = {"shop": shop, "docs": docs, "mail": mail, "bizutils": bizutils}  # order of the tool list
TRUSTED = ("shop", "docs", "mail")
THIRD_PARTY = ("bizutils",)


def _schema_model(name: str, schema: dict) -> type[BaseModel]:
    """A pydantic model that reports the MCP input schema as its JSON schema (what the LLM adapters send)."""

    def model_json_schema(cls, *args, **kwargs):
        return schema

    return type(f"{name}_arguments", (BaseModel,), {"model_json_schema": classmethod(model_json_schema)})


class McpHub:
    """All servers of one run, connected over MCP; use as a context manager."""

    def __init__(self, db_path: Path, variants: dict[str, Variant] | None = None):
        self.db_path = db_path
        self.variants = variants or {}
        self.tools = []  # mcp.types.Tool, in server order
        self._route: dict[str, object] = {}

    def __enter__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._ready = threading.Event()
        self._serving = asyncio.run_coroutine_threadsafe(self._serve(), self._loop)
        while not self._ready.wait(0.05):
            if self._serving.done():
                self._serving.result()  # raises the connection error
        return self

    def __exit__(self, *exc):
        self._loop.call_soon_threadsafe(self._stop.set)
        try:
            self._serving.result(timeout=60)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join()
            self._loop.close()

    def _call(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result(timeout=120)

    async def _serve(self):
        """Opens the sessions, keeps them open until __exit__, closes them in the same task (anyio requires it)."""
        self._stop = asyncio.Event()
        async with AsyncExitStack() as stack:
            for name, module in SERVERS.items():
                server = module.build(self.db_path, self.variants.get(name, Variant()))
                session = await stack.enter_async_context(create_connected_server_and_client_session(server.mcp._mcp_server))
                for tool in (await session.list_tools()).tools:
                    if tool.name in self._route:
                        raise RuntimeError(f"tool name {tool.name} is used by two servers")
                    self._route[tool.name] = session
                    self.tools.append(tool)
            self._ready.set()
            await self._stop.wait()

    def server_of(self, tool_name: str) -> str | None:
        for name, module in SERVERS.items():
            if tool_name in module.DESCRIPTIONS:
                return name
        return None

    def call_tool(self, name: str, arguments: dict) -> tuple[str, str | None]:
        """Returns (result text, error text or None)."""
        session = self._route.get(name)
        if session is None:
            return "", f"ToolNotFoundError: The requested function `{name}` is not available."
        result = self._call(session.call_tool(name, arguments))
        text = "\n".join(block.text for block in result.content if block.type == "text")
        return ("", text or "error") if result.isError else (text, None)


class McpFunctionsRuntime(FunctionsRuntime):
    """AgentDojo runtime whose functions are the MCP tools of a hub."""

    def __init__(self, hub: McpHub):
        super().__init__([])
        self.hub = hub
        for tool in hub.tools:
            self.functions[tool.name] = Function(
                name=tool.name,
                description=tool.description or "",
                parameters=_schema_model(tool.name, tool.inputSchema),
                dependencies={},
                run=lambda **kwargs: None,
                full_docstring=tool.description or "",
                return_type=None,
            )

    def run_function(self, env, function, kwargs, raise_on_error=False):
        result, error = self.hub.call_tool(function, dict(kwargs))
        if error and raise_on_error:
            raise RuntimeError(error)
        return result, error
