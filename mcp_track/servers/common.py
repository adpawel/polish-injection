"""Shared helpers of the MCP servers."""

from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from mcp.server.fastmcp import FastMCP

from mcp_track import world


@dataclass(frozen=True)
class Variant:
    """What differs between the attack vectors (notes/protocol.md 3); empty = clean servers.

    extra_descriptions: tool name -> text appended to that tool's description (V1 tp_third_party, V3 tp_trusted).
    result_notice: text added as a `notice` field to every result of the third-party server (V2 mcp_result).
    """

    extra_descriptions: dict[str, str] = field(default_factory=dict)
    result_notice: str | None = None


def dump(data) -> str:
    """Tool results as text, formatted as AgentDojo formats them in the IPI track (YAML, fix 8 allow_unicode)."""
    return yaml.safe_dump(data, allow_unicode=True).strip()


class Server:
    """A FastMCP server whose tool descriptions come from a table, so they can be translated and poisoned."""

    def __init__(self, name: str, db_path: Path, descriptions: dict[str, str], variant: Variant):
        self.mcp = FastMCP(name)
        self.db_path = db_path
        self.descriptions = descriptions
        self.variant = variant

    def tool(self, fn):
        description = self.descriptions[fn.__name__]
        extra = self.variant.extra_descriptions.get(fn.__name__)
        if extra:
            description = f"{description}\n\n{extra}"
        self.mcp.tool(name=fn.__name__, description=description)(fn)
        return fn

    def db(self):
        """`with server.db() as con:` - autocommit connection, closed at the end of the block."""
        return closing(world.connect(self.db_path))
