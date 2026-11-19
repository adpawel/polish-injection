"""Checks of the MCP track's tasks before any model run (notes/protocol.md 3).

1. the ground truth of every user task completes it (utility True) and triggers no attacker goal;
2. the ground truth of every attacker goal is detected (security True), also when every call is made twice and
   when the goal's calls are replayed with dedup;
3. every user task's ground truth uses the third-party server (V2 can reach the model in every task);
4. every ground-truth call succeeds (no tool error);
5. an empty run passes neither a utility nor a security checker;
6. utility and security are independent: for every (user task, side-action goal) pair, the task's ground truth
   followed by the goal's ground truth passes both checkers (the attacker's side effects do not break the user's
   task); a tampering goal changes the user's own action, so it is checked by its ground truth (2) and by its
   tampered version of every task it applies to;
7. the Polish translations cover every task and goal and their English sources equal tasks.py.

Usage: python -m mcp_track.check
"""

import sys

from mcp_track.attacks import translations
from mcp_track.replay import run_calls
from mcp_track.runtime import SERVERS
from mcp_track.tasks import GOALS, USER_TASKS


def main() -> int:
    problems = []
    for task in USER_TASKS.values():
        pre, post, results = run_calls(task.ground_truth)
        problems += [f"{task.id}: {name} failed: {error}" for (name, _), (_, error) in zip(task.ground_truth, results) if error]
        if not task.utility(task.answer, pre, post):
            problems.append(f"{task.id}: ground truth does not pass the utility checker")
        problems += [f"{task.id}: ground truth triggers {g.id}" for g in GOALS.values() if g.security(pre, post)]
        if not any(name in SERVERS["bizutils"].DESCRIPTIONS for name, _ in task.ground_truth):
            problems.append(f"{task.id}: ground truth does not call bizutils")
        if task.risk not in ("none", "low", "medium", "high"):
            problems.append(f"{task.id}: unknown risk {task.risk!r}")

    # 5. an empty run (no calls, empty answer) passes no checker
    pre, post, _ = run_calls([])
    problems += [f"{t.id}: utility True on an empty run" for t in USER_TASKS.values() if t.utility("", pre, post)]
    problems += [f"{g.id}: security True on an empty run" for g in GOALS.values() if g.security(pre, post)]

    for g in GOALS.values():
        for label, calls, dedup in (("once", g.ground_truth, False), ("twice", g.ground_truth * 2, False),
                                    ("twice, dedup", g.ground_truth * 2, True)):
            pre, post, results = run_calls(calls, dedup_calls=dedup)
            problems += [f"{g.id} ({label}): {name} failed: {error}" for (name, _), (_, error) in zip(calls, results) if error and label == "once"]
            if not g.security(pre, post):
                problems.append(f"{g.id} ({label}): ground truth not detected")

    for task in USER_TASKS.values():
        for g in GOALS.values():
            if g.applies_to is not None:
                continue
            pre, post, _ = run_calls(task.ground_truth + g.ground_truth)
            if not task.utility(task.answer, pre, post):
                problems.append(f"{task.id} + {g.id}: utility False when the goal is also carried out")
            if not g.security(pre, post):
                problems.append(f"{task.id} + {g.id}: goal not detected after the user task")

    # tampering goals: the user task's ground truth with the tampered action is detected
    from mcp_track.tasks import _to_clearing, _with_archive
    tamper = {"goal_6": _with_archive, "goal_7": _to_clearing}
    for goal_id, change in tamper.items():
        g = GOALS[goal_id]
        if not g.applies_to:
            problems.append(f"{goal_id}: applies to no task")
        for task_id in sorted(g.applies_to or []):
            pre, post, _ = run_calls(change(USER_TASKS[task_id].ground_truth))
            if not g.security(pre, post):
                problems.append(f"{goal_id} on {task_id}: tampered ground truth not detected")

    pl = translations("pl", allow_draft=True)
    from mcp_track.attacks import FRAME
    if pl.get("frame", {}).get("payload", {}).get("en") != FRAME["en"]:
        problems.append("pl frame: missing or English source differs from attacks.FRAME")
    for section, items, text in (("user_tasks", USER_TASKS, lambda t: t.prompt), ("goals", GOALS, lambda g: g.goal)):
        if set(pl[section]) != set(items):
            problems.append(f"pl {section}: ids differ from tasks.py")
        problems += [f"pl {section}/{i}: English source differs" for i, item in items.items()
                     if i in pl[section] and pl[section][i]["en"] != text(item)]
    if "DRAFT" in pl["_meta"]["status"]:
        print("note: the Polish translations are a draft (not reviewed)")

    print(f"{len(USER_TASKS)} user tasks, {len(GOALS)} attacker goals")
    for problem in problems:
        print("PROBLEM", problem)
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
