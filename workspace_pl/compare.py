"""Checks a translated workspace data file against the AgentDojo original and writes a side-by-side review table.

The translation may change only the free-text fields (TEXT_FIELDS); everything else (ids, dates, addresses,
statuses, structure) must be identical, and every `{placeholder}` of an injection vector must survive unchanged.

`tools` is checked differently: data/tools.yaml holds en/pl pairs, and the `en` texts are compared with the
installed package (system prompt, tool and parameter descriptions, messages in the tool sources).

Usage: python workspace_pl/compare.py calendar|inbox|cloud_drive|injection_vectors|tools [-o review.md]
"""

import argparse
import re
import sys
from pathlib import Path

import yaml

import agentdojo

SUITE_DATA = Path(agentdojo.__file__).parent / "data" / "suites" / "workspace"
ORIGINAL = {
    "calendar": SUITE_DATA / "include" / "calendar.yaml",
    "inbox": SUITE_DATA / "include" / "inbox.yaml",
    "cloud_drive": SUITE_DATA / "include" / "cloud_drive.yaml",
    "injection_vectors": SUITE_DATA / "injection_vectors.yaml",
}
TOOL_SOURCES = Path(agentdojo.__file__).parent / "default_suites" / "v1" / "tools"
TRANSLATED = Path(__file__).parent / "data"
TEXT_FIELDS = {"title", "description", "location", "subject", "body", "filename", "content", "default"}
PLACEHOLDER = re.compile(r"\{[a-z0-9_]+\}")
FORMAT_FIELD = re.compile(r"\{[^{}]*\}")


def check_tools(pl_data: dict, errors: list, rows: list) -> None:
    from agentdojo.agent_pipeline.agent_pipeline import load_system_message
    from agentdojo.task_suite.load_suites import get_suite

    def pair(path, texts, original):
        if original is not None and texts["en"].strip() != original.strip():
            errors.append(f"{path}: `en` differs from the package")
        if sorted(FORMAT_FIELD.findall(texts["en"])) != sorted(FORMAT_FIELD.findall(texts["pl"])):
            errors.append(f"{path}: format fields differ")
        rows.append((path, texts["en"], texts["pl"]))

    pair("system_prompt", pl_data["system_prompt"], load_system_message(None))
    tools = {f.name: f for f in get_suite("v1.2.2", "workspace").tools}
    if set(tools) != set(pl_data["tools"]):
        errors.append(f"tools differ: {sorted(set(tools) ^ set(pl_data['tools']))}")
    for name, entry in pl_data["tools"].items():
        if name not in tools:
            continue
        pair(f"{name}.description", entry["description"], tools[name].description)
        properties = tools[name].parameters.model_json_schema()["properties"]
        if set(properties) != set(entry.get("params", {})):
            errors.append(f"{name}: parameters differ")
        for param, texts in entry.get("params", {}).items():
            pair(f"{name}.{param}", texts, properties.get(param, {}).get("description"))
    sources = "".join(p.read_text(encoding="utf-8") for p in TOOL_SOURCES.glob("*.py"))
    for i, texts in enumerate(pl_data["messages"]):
        pair(f"messages[{i}]", texts, None)
        if texts["en"] not in sources:
            errors.append(f"messages[{i}]: not found in the tool sources")


def walk(en, pl, path, errors, rows):
    if isinstance(en, dict):
        if not isinstance(pl, dict) or set(en) != set(pl):
            errors.append(f"{path}: different keys")
            return
        for key in en:
            walk(en[key], pl[key], f"{path}.{key}", errors, rows)
    elif isinstance(en, list):
        if not isinstance(pl, list) or len(en) != len(pl):
            errors.append(f"{path}: different list length")
            return
        for i, (a, b) in enumerate(zip(en, pl)):
            walk(a, b, f"{path}[{i}]", errors, rows)
    elif path.rsplit(".", 1)[-1] in TEXT_FIELDS and isinstance(en, str):
        if sorted(PLACEHOLDER.findall(en)) != sorted(PLACEHOLDER.findall(pl or "")):
            errors.append(f"{path}: placeholders differ")
        rows.append((path, en, pl))
    elif en != pl:
        errors.append(f"{path}: {en!r} changed to {pl!r}")


def cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", "<br>")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", choices=[*ORIGINAL, "tools"])
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--translated-only", action="store_true", help="leave unchanged fields out of the table")
    args = parser.parse_args()
    pl = yaml.safe_load((TRANSLATED / f"{args.name}.yaml").read_text(encoding="utf-8"))
    errors, rows = [], []
    if args.name == "tools":
        check_tools(pl, errors, rows)
    else:
        en = yaml.safe_load(ORIGINAL[args.name].read_text(encoding="utf-8"))
        walk(en, pl, args.name, errors, rows)
    if args.output:
        lines = ["| field | EN | PL |", "|---|---|---|"]
        lines += [
            f"| {cell(path)} | {cell(a)} | {cell(b)} |"
            for path, a, b in rows
            if not (args.translated_only and a == b)
        ]
        args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    untranslated = sum(a == b for _, a, b in rows)
    print(f"{len(rows)} text fields, {untranslated} left unchanged, {len(errors)} errors")
    if args.name == "cloud_drive":
        # "the largest file" tasks name the file in their checker; size is len(content) (placeholders included)
        ranking = [
            [f["id_"] for f in sorted(data["initial_files"], key=lambda f: -len(f["content"]))] for data in (en, pl)
        ]
        print(f"largest files EN {ranking[0][:6]}, PL {ranking[1][:6]}")
        if ranking[0][0] != ranking[1][0]:
            errors.append("the largest file is not the same")
    for error in errors:
        print("  " + error)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
