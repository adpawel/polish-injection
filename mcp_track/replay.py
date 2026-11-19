"""Executes a list of tool calls on a fresh world over MCP (ground-truth checks and the replay of logged runs).

The replay scores a run from its tool calls alone: with `dedup=True` identical calls (same tool, same arguments)
are executed once, which gives the dedup attack success of notes/protocol.md 1.5; it also scores runs cut off by a
context overflow from the calls made before it.
"""

import json
import tempfile
from pathlib import Path

from mcp_track import world
from mcp_track.runtime import McpHub
from mcp_track.world import Snapshot


def dedup(calls: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    seen, unique = set(), []
    for name, args in calls:
        key = (name, json.dumps(args, sort_keys=True, ensure_ascii=False))
        if key not in seen:
            seen.add(key)
            unique.append((name, args))
    return unique


def run_calls(calls: list[tuple[str, dict]], seed_lang: str = "en", dedup_calls: bool = False
              ) -> tuple[Snapshot, Snapshot, list[tuple[str, str | None]]]:
    """Returns (pre, post, [(result, error) per call])."""
    if dedup_calls:
        calls = dedup(calls)
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "world.db"
        world.create(db, world.load_seed(seed_lang))
        pre = world.snapshot(db)
        with McpHub(db) as hub:
            results = [hub.call_tool(name, args) for name, args in calls]
        return pre, world.snapshot(db), results
