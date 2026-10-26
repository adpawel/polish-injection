"""Static checks of the translations in data/<lang>/ - no model needed.

For every translated user prompt and injection goal:
- the stored English source must equal AgentDojo's text (benchmark v1.2.2);
- every literal of the English text must appear unchanged in the translation: quoted strings, email
  addresses, URLs and numbers. The checkers compare such values exactly, so a translated title or
  subject would silently break utility or security. Unquoted values that must stay (e.g. an event description
  the checker compares) are listed in the entry's optional `keep` field; false literals (e.g. text between two
  quotes when the English original misses a closing quote) in `ignore`.
For the attack template: the English source must equal AgentDojo's and the placeholders must match.

Usage: python scripts/check_translations.py [lang]   (default: pl)
"""

import json
import re
import string
import sys
from pathlib import Path

from agentdojo.attacks.important_instructions_attacks import ImportantInstructionsAttack
from agentdojo.task_suite.load_suites import get_suites

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BENCHMARK_VERSION = "v1.2.2"

LITERALS = [
    re.compile(r"(?<!\w)'([^']+?)'(?!\w)"),  # quoted strings (not apostrophes such as "I'm")
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),  # email addresses
    re.compile(r"https?://\S+"),  # URLs
    re.compile(r"\d(?:[\d:./-]*\d)?"),  # numbers, dates, times
]


def literals(text: str) -> set[str]:
    found = set()
    for pattern in LITERALS:
        for match in pattern.finditer(text):
            found.add(match.group(match.lastindex or 0))
    return found


def placeholders(template: str) -> set[str]:
    return {field for _, field, _, _ in string.Formatter().parse(template) if field}


def check_entry(key: str, entry: dict, lang: str, en_text: str) -> list[str]:
    errors = []
    if entry["en"] != en_text:
        errors.append(f"{key}: English source differs from AgentDojo's text")
    required = (literals(entry["en"]) | set(entry.get("keep", []))) - set(entry.get("ignore", []))
    missing = sorted(lit for lit in required if lit not in entry[lang])
    if missing:
        errors.append(f"{key}: literals missing from the translation: {missing}")
    return errors


def main(lang: str) -> int:
    errors, checked = [], 0
    for suite_name, suite in get_suites(BENCHMARK_VERSION).items():
        path = DATA_DIR / lang / f"{suite_name}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for task_id, entry in data.get("user_tasks", {}).items():
            errors += check_entry(f"{suite_name}/{task_id}", entry, lang, suite.get_user_task_by_id(task_id).PROMPT)
            checked += 1
        for task_id, entry in data.get("injection_tasks", {}).items():
            errors += check_entry(f"{suite_name}/{task_id}", entry, lang, suite.get_injection_task_by_id(task_id).GOAL)
            checked += 1

    attacks_path = DATA_DIR / lang / "attacks.json"
    if attacks_path.exists():
        template = json.loads(attacks_path.read_text(encoding="utf-8"))["important_instructions"]
        if template["en"] != ImportantInstructionsAttack._JB_STRING:
            errors.append("important_instructions: English source differs from AgentDojo's template")
        if placeholders(template[lang]) != placeholders(template["en"]):
            errors.append(f"important_instructions: placeholders differ: {placeholders(template[lang])}")
        checked += 1

    for error in errors:
        print("ERROR", error)
    print(f"checked {checked} entries, {len(errors)} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "pl"))
