"""Exports AgentDojo run logs as result rows (JSONL) following schemas/run_result.schema.json.

One row per log file under each log directory:
- `<user_task>/<attack>/<injection_task>.json` -> run_type "attack" (scored as in attack_summary.py: exposure,
  raw and dedup success, context overflows re-scored from the replay);
- `<user_task>/none/none.json` -> "no_attack" (utility baseline);
- `<injection_task>/none/none.json` -> "injection_as_user_task" (control: the attacker's goal as the user task).
  AgentDojo gives the model the English goal here in every configuration, so a control run in a Polish-task
  log directory repeats the English one; only controls from English-task directories are exported.

Only logs written with fix 11 of run_agentdojo.py (run metadata) are accepted, and only from a clean harness
(`harness_dirty: false`) unless --allow-dirty is given. Every row is validated against the schema; any invalid row
stops the export.

Usage: python scripts/export_results.py <logdir> [<logdir> ...] -o results.jsonl [--allow-dirty]
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

import jsonschema

from attack_summary import summarise_run, text

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schemas" / "run_result.schema.json").read_text(encoding="utf-8"))
UTILITY_RISK = json.loads((ROOT / "data" / "utility_risk.json").read_text(encoding="utf-8"))
PAYLOAD_LANG = {"important_instructions_no_model_name": "en", "important_instructions_pl": "pl"}
SERVER = {
    "gpt-4o-mini": "OpenAI API",
    "qwen3-8b": "HF router (nscale)",
    "pllum-12b": "vllm 0.24.0",
    "bielik-11b-v3": "vllm 0.24.0",
    "mistral-nemo": "vllm 0.24.0",
}


def run_type(path: Path) -> str:
    if path.parent.name != "none":
        return "attack"
    return "injection_as_user_task" if path.parent.parent.name.startswith("injection_task_") else "no_attack"


def timestamp(log: dict) -> str:
    local = datetime.datetime.strptime(log["evaluation_timestamp"], "%Y-%m-%d %H:%M:%S")
    return local.astimezone().isoformat()


def export_row(path: Path, allow_dirty: bool) -> dict | None:
    log = json.loads(path.read_text(encoding="utf-8"))
    if "harness_commit" not in log:
        raise ValueError(f"{path}: no run metadata - written before fix 11 of run_agentdojo.py")
    if log["harness_dirty"] and not allow_dirty:
        raise ValueError(f"{path}: produced with uncommitted harness changes (use --allow-dirty for tests)")
    if "security" not in log and "context_length_exceeded" not in (log.get("error") or ""):
        raise ValueError(f"{path}: no `security` - the run crashed; rerun it with -f")
    kind = run_type(path)
    if kind == "injection_as_user_task" and log["task_lang"] != "en":
        return None
    messages = log["messages"]
    last = messages[-1] if messages else {}
    row = {
        "schema_version": SCHEMA["properties"]["schema_version"]["const"],
        "track": "ipi",
        "run_type": kind,
        "model": log["model"],
        "task_lang": log["task_lang"],
        "payload_lang": None,
        "suite": log["suite_name"],
        "user_task": log["user_task_id"],
        "injection_task": None,
        "attack": None,
        "exposed": None,
        "attack_success": None,
        "attack_success_dedup": None,
        "utility": bool(log.get("utility")),
        "utility_risk": None,
        "no_output": not (last.get("role") == "assistant" and text(last).strip()),
        "context_overflow": "context_length_exceeded" in (log.get("error") or ""),
        "refused": None,
        "steps": sum(m["role"] == "assistant" for m in messages),
        "tool_calls": sum(len(m.get("tool_calls") or []) for m in messages if m["role"] == "assistant"),
        "input_tokens": log.get("input_tokens"),
        "output_tokens": log.get("output_tokens"),
        "error": log.get("error"),
        "log_path": path.resolve().relative_to(ROOT).as_posix(),
        "settings": {
            "temperature": log["temperature"],
            "max_tokens": log["max_tokens"],
            "max_steps": log["max_steps"],
            "attempts": log["attempts"],
            "tool_calling": log["tool_calling"],
        },
        "provenance": {
            "harness_commit": log["harness_commit"],
            "timestamp": timestamp(log),
            "benchmark_version": log.get("benchmark_version"),
            "agentdojo_version": log.get("agentdojo_package_version"),
            "server_version": SERVER.get(log["model"]),
        },
    }
    if kind != "injection_as_user_task":
        row["utility_risk"] = UTILITY_RISK[log["suite_name"]][log["user_task_id"]][0]
    if kind == "attack":
        if log["attack_type"] not in PAYLOAD_LANG:
            raise ValueError(f"{path}: unknown attack {log['attack_type']}")
        run = summarise_run(path)
        row.update(
            payload_lang=PAYLOAD_LANG[log["attack_type"]],
            injection_task=log["injection_task_id"],
            attack=log["attack_type"],
            exposed=run["exposed"],
            attack_success=run["attack_success"],
            attack_success_dedup=run["attack_success_dedup"],
            context_overflow=run["context_overflow"],
            utility=run["utility"],
        )
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("logdirs", nargs="+", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--allow-dirty", action="store_true", help="accept logs from uncommitted harness changes")
    args = parser.parse_args()

    validator = jsonschema.Draft202012Validator(SCHEMA, format_checker=jsonschema.FormatChecker())
    rows = []
    for logdir in args.logdirs:
        for path in sorted(logdir.glob("*/*/*/*/*.json")):
            try:
                row = export_row(path, args.allow_dirty)
            except ValueError as e:
                sys.exit(str(e))
            if row is None:
                continue
            errors = sorted(validator.iter_errors(row), key=lambda e: list(e.path))
            if errors:
                sys.exit(f"{path}: invalid row: {errors[0].message} (at {list(errors[0].path)})")
            rows.append(row)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    counts = {}
    for row in rows:
        counts[row["run_type"]] = counts.get(row["run_type"], 0) + 1
    print(f"wrote {len(rows)} rows to {args.output}: {counts}")


if __name__ == "__main__":
    main()
