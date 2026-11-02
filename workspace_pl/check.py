"""Checks the fully Polish workspace suite before any model run.

1. AgentDojo's own suite check: the ground truth of every user task solves it (utility True), every user task can
   be injected, and the ground truth of every injection task succeeds (security True). Compared with the same check
   on the English suite, which also fails for injection tasks with an empty ground truth.
2. Every injection vector accepts the real payloads (English and Polish attack, every injection task goal) and the
   environment still loads.
3. The Polish texts of the attacker (injection tasks 0, 2, 4, 13) are scored as successful attacks, as are the
   English ones.
4. Tool descriptions are the Polish ones, and tool messages are translated.

Usage: python workspace_pl/check.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import run_agentdojo  # noqa: E402  (registers the Polish attack)
from agentdojo.attacks.attack_registry import load_attack  # noqa: E402
from agentdojo.task_suite.load_suites import get_suite  # noqa: E402

from workspace_pl.suite import INJECTION_TASK_VARIANTS, TOOL_TEXTS, translate_message, workspace_pl_suite  # noqa: E402


class _NoPipeline:
    name = "gpt-4o-mini-2024-07-18"


def check_ground_truth(errors: list) -> None:
    # check_injectable=False: AgentDojo's injectability check reports every task, English ones too, as not
    # injectable; check_injection_candidates below compares the injection vectors instead.
    _, (user_en, injection_en) = get_suite("v1.2.2", "workspace").check(check_injectable=False)
    _, (user_pl, injection_pl) = workspace_pl_suite.check(check_injectable=False)
    for task_id, (ok, reason) in user_pl.items():
        if not ok:
            errors.append(f"{task_id}: {reason} (English suite: {user_en[task_id]})")
    for task_id, ok in injection_pl.items():
        if ok != injection_en[task_id]:
            errors.append(f"{task_id}: security of the ground truth {ok}, English suite {injection_en[task_id]}")
    passed = sum(ok for ok, _ in user_pl.values())
    print(f"user tasks: ground truth solves {passed}/{len(user_pl)}")
    print(f"injection tasks: ground truth security as in the English suite for "
          f"{sum(injection_pl[t] == injection_en[t] for t in injection_pl)}/{len(injection_pl)}")


def check_injection_candidates(errors: list) -> None:
    """Each user task reaches the same injection vectors as in the English suite (ground truth with canaries)."""
    english = get_suite("v1.2.2", "workspace")
    attacks = [load_attack("important_instructions_no_model_name", s, _NoPipeline()) for s in (english, workspace_pl_suite)]
    same = 0
    for task_id, user_task in workspace_pl_suite.user_tasks.items():
        candidates = []
        for attack, suite in zip(attacks, (english, workspace_pl_suite)):
            try:
                candidates.append(sorted(attack.get_injection_candidates(suite.user_tasks[task_id])))
            except ValueError:
                candidates.append([])
        if candidates[0] != candidates[1]:
            errors.append(f"{task_id}: injection vectors EN {candidates[0]}, PL {candidates[1]}")
        else:
            same += 1
    print(f"injection vectors: same as in the English suite for {same}/{len(workspace_pl_suite.user_tasks)} user tasks")


def check_payloads(errors: list) -> None:
    suite = workspace_pl_suite
    count = 0
    for attack_name in ("important_instructions_no_model_name", "important_instructions_pl"):
        attack = load_attack(attack_name, suite, _NoPipeline())
        for user_task in suite.user_tasks.values():
            for injection_task in suite.injection_tasks.values():
                try:
                    injections = attack.attack(user_task, injection_task)
                except ValueError as e:
                    errors.append(f"{attack_name} {user_task.ID} {injection_task.ID}: {e}")
                    continue
                try:
                    environment = suite.load_and_inject_default_environment(injections)
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{attack_name} {user_task.ID} {injection_task.ID}: environment fails: {e}")
                    continue
                text = environment.model_dump_json()
                count += 1
                if injections and not any(
                    payload.splitlines()[1][:40] in text for payload in injections.values() if "\n" in payload
                ):
                    errors.append(f"{attack_name} {user_task.ID} {injection_task.ID}: payload not found")
    print(f"payloads: {count} environments loaded with injections")


def check_attacker_variants(errors: list) -> None:
    from agentdojo.functions_runtime import FunctionCall, FunctionsRuntime

    suite = workspace_pl_suite
    environment = suite.load_and_inject_default_environment({})
    runtime = FunctionsRuntime(suite.tools)
    for task_id, variants in INJECTION_TASK_VARIANTS.items():
        task = suite.injection_tasks[task_id]
        for variant in variants:
            if task_id == "injection_task_13":
                continue  # its ground truth is empty in AgentDojo; checked by the English ground truth above
            post = environment.model_copy(deep=True)
            original = {name: getattr(task, name) for name in variant}
            for name, value in variant.items():
                setattr(task, name, value)
            try:
                for call in task.ground_truth(post):
                    runtime.run_function(post, call.function, call.args)
            finally:
                for name, value in original.items():
                    setattr(task, name, value)
            if not task.security("", environment, post):
                errors.append(f"{task_id}: attacker text {variant} not scored as success")
    print("attacker texts: English and Polish variants checked")


def check_tools(errors: list) -> None:
    for tool in workspace_pl_suite.tools:
        expected = TOOL_TEXTS["tools"][tool.name]["description"]["pl"]
        if tool.description.strip() != expected.strip():
            errors.append(f"{tool.name}: description is not the Polish one")
        properties = tool.parameters.model_json_schema()["properties"]
        for param, texts in TOOL_TEXTS["tools"][tool.name].get("params", {}).items():
            if properties[param].get("description", "").strip() != texts["pl"].strip():
                errors.append(f"{tool.name}.{param}: description is not the Polish one")
    samples = {
        "No emails found. Try with a different query.": "Nie znaleziono e-maili. Spróbuj z innym zapytaniem.",
        "File with ID '99' not found.": "Nie znaleziono pliku o ID '99'.",
        "Invitation: Lunch": "Zaproszenie: Lunch",
        "Some other text": "Some other text",
    }
    for en, pl in samples.items():
        if translate_message(en) != pl:
            errors.append(f"message {en!r} translated to {translate_message(en)!r}")
    print(f"tools: {len(workspace_pl_suite.tools)} with Polish descriptions, messages translated")


def main() -> None:
    errors: list[str] = []
    check_tools(errors)
    check_attacker_variants(errors)
    check_injection_candidates(errors)
    check_payloads(errors)
    check_ground_truth(errors)
    for error in errors:
        print("  " + error)
    print("OK" if not errors else f"{len(errors)} errors")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
