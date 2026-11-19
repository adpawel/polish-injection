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


def translations(lang: str, allow_draft: bool = False) -> dict:
    """mcp_track/data/<lang>/tasks.json; a translation still marked DRAFT (not reviewed) is refused."""
    data = json.loads((Path(__file__).resolve().parent / "data" / lang / "tasks.json").read_text(encoding="utf-8"))
    if "DRAFT" in data["_meta"]["status"] and not allow_draft:
        raise SystemExit(f"mcp_track/data/{lang}/tasks.json is not reviewed yet (status DRAFT)")
    return data


def translated(section: str, item_id: str, english: str, lang: str, allow_draft: bool = False) -> str:
    if lang == "en":
        return english
    entry = translations(lang, allow_draft)[section].get(item_id)
    if entry is None:
        raise KeyError(f"{item_id} has no '{lang}' translation in mcp_track/data/{lang}/tasks.json")
    if entry["en"] != english:
        raise ValueError(f"{item_id}: the English source of the translation differs from tasks.py")
    return entry[lang]


def goal_text(goal_id: str, lang: str, allow_draft: bool = False) -> str:
    return translated("goals", goal_id, GOALS[goal_id].goal, lang, allow_draft)


def payload(goal_id: str, lang: str, allow_draft: bool = False) -> str:
    template = _ipi_template()
    if template["en"] != ImportantInstructionsAttack._JB_STRING:
        raise ValueError("data/pl/attacks.json: English source differs from AgentDojo's template")
    return template[lang].format(goal=goal_text(goal_id, lang, allow_draft), user=USER_NAME, model=template["model_name"][lang]).strip()


def variants(vector: str, text: str) -> dict[str, Variant]:
    server, tool, place = VECTORS[vector]
    if place == "description":
        return {server: Variant(extra_descriptions={tool: text})}
    return {server: Variant(result_notice=text)}
