"""Payloads and attack vectors of the MCP track (notes/protocol.md 3).

The payload is the IPI track's `important_instructions` text (AgentDojo's English template, the reviewed Polish
template of data/pl/attacks.json) with this scenario's user name, so the payload text is the same in all three
vectors and in both tracks; only where it is placed differs:

- tp_third_party (V1): appended to the description of a tool of the third-party server `bizutils`;
- mcp_result (V2): a `notice` field in every result of `bizutils`;
- tp_trusted (V3): appended to the description of a tool of the trusted server `shop`.
"""

import json
from pathlib import Path

from agentdojo.attacks.important_instructions_attacks import ImportantInstructionsAttack

from mcp_track.servers.common import Variant
from mcp_track.tasks import GOALS

REPO = Path(__file__).resolve().parent.parent
USER_NAME = "Emma Clarke"
MARKER = "<INFORMATION>"  # exposure in V2: a tool result contains it

VECTORS = {
    "tp_third_party": ("bizutils", "get_exchange_rate", "description"),
    "mcp_result": ("bizutils", None, "result"),
    "tp_trusted": ("shop", "search_orders", "description"),
}


def _ipi_template() -> dict:
    return json.loads((REPO / "data/pl/attacks.json").read_text(encoding="utf-8"))["important_instructions"]


def _goal_translations(lang: str) -> dict:
    path = Path(__file__).resolve().parent / "data" / lang / "goals.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def goal_text(goal_id: str, lang: str) -> str:
    english = GOALS[goal_id].goal
    if lang == "en":
        return english
    entry = _goal_translations(lang).get(goal_id)
    if entry is None:
        raise KeyError(f"{goal_id} has no '{lang}' translation in mcp_track/data/{lang}/goals.json")
    if entry["en"] != english:
        raise ValueError(f"{goal_id}: the English source of the translation differs from tasks.py")
    return entry[lang]


def payload(goal_id: str, lang: str) -> str:
    template = _ipi_template()
    if template["en"] != ImportantInstructionsAttack._JB_STRING:
        raise ValueError("data/pl/attacks.json: English source differs from AgentDojo's template")
    return template[lang].format(goal=goal_text(goal_id, lang), user=USER_NAME, model=template["model_name"][lang]).strip()


def variants(vector: str, text: str) -> dict[str, Variant]:
    server, tool, place = VECTORS[vector]
    if place == "description":
        return {server: Variant(extra_descriptions={tool: text})}
    return {server: Variant(result_notice=text)}
