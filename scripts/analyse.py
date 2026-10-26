"""Analysis of exported result rows (schemas/run_result.schema.json), as fixed in notes/protocol.md 1.5-1.6.

Per (track, model, configuration):
- exposure = exposed attack runs / attack runs;
- ASR = dedup successes / exposed runs (primary), with a Wilson 95 % CI; raw ASR = successes / attack runs;
- utility without attack and under attack, on the language-safe tasks only (utility_risk none/low);
- runs without output, context overflows.
Per (track, model): the control - injection tasks solved when given as the user task.

Paired comparisons within (track, model): a pair is the same (user task, injection task) in two configurations,
used only when exposed in both. Exact two-sided McNemar test on the discordant pairs; effect = difference of
dedup ASR on those pairs, 95 % CI from a cluster bootstrap over user tasks (one user task contributes several
pairs). Primary comparison EN/EN vs PL/PL; the other five pairs are secondary, Holm-corrected within a model.
No test is reported with fewer than 6 discordant pairs (5:0 already gives p = 0.0625).

Usage: python scripts/analyse.py results.jsonl [results2.jsonl ...] [--bootstrap 2000] [--seed 0]
"""

import argparse
import itertools
import json
import random
from collections import defaultdict
from math import comb, sqrt
from pathlib import Path

CONFIGS = ["EN/EN", "EN/PL", "PL/EN", "PL/PL"]
PRIMARY = ("EN/EN", "PL/PL")
SAFE_RISK = {"none", "low"}
MIN_DISCORDANT = 6


def config(row: dict) -> str:
    return f"{row['task_lang'].upper()}/{row['payload_lang'].upper()}"


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2**n)


def holm(pvalues: dict) -> dict:
    ordered = sorted(pvalues.items(), key=lambda item: item[1])
    adjusted, running = {}, 0.0
    for rank, (key, p) in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - rank) * p))
        adjusted[key] = running
    return adjusted


def bootstrap_diff(pairs: list[tuple[str, bool, bool]], resamples: int, rng: random.Random) -> tuple[float, float]:
    """95 % CI of mean(a) - mean(b) over pairs, resampling user tasks (clusters) with replacement."""
    clusters = defaultdict(list)
    for user_task, a, b in pairs:
        clusters[user_task].append(a - b)
    keys = list(clusters)
    diffs = []
    for _ in range(resamples):
        values = [d for key in rng.choices(keys, k=len(keys)) for d in clusters[key]]
        diffs.append(sum(values) / len(values))
    diffs.sort()
    return diffs[int(0.025 * resamples)], diffs[int(0.975 * resamples) - 1]


def pct(numerator: int, denominator: int) -> str:
    return f"{numerator}/{denominator} ({numerator / denominator:.0%})" if denominator else "-"


def describe(rows: list[dict]) -> None:
    attack = defaultdict(list)
    no_attack = defaultdict(list)
    control = defaultdict(list)
    for row in rows:
        key = (row["track"], row["model"])
        if row["run_type"] == "attack":
            attack[key + (config(row),)].append(row)
        elif row["run_type"] == "no_attack":
            no_attack[key + (row["task_lang"].upper(),)].append(row)
        else:
            control[key].append(row)

    print("| track | model | config | runs | exposure | ASR dedup / exposed [95 % CI] | raw ASR | utility (no attack) "
          "| utility (attack) | no output | overflow |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for (track, model, cfg), runs in sorted(attack.items()):
        exposed = [r for r in runs if r["exposed"]]
        successes = sum(r["attack_success_dedup"] for r in exposed)
        low, high = wilson(successes, len(exposed))
        safe = [r for r in runs if r["utility_risk"] in SAFE_RISK]
        baseline = [r for r in no_attack.get((track, model, cfg.split("/")[0]), []) if r["utility_risk"] in SAFE_RISK]
        print(
            f"| {track} | {model} | {cfg} | {len(runs)} | {pct(len(exposed), len(runs))} | "
            f"{pct(successes, len(exposed))} [{low:.0%}, {high:.0%}] | {pct(sum(r['attack_success'] for r in runs), len(runs))} | "
            f"{pct(sum(r['utility'] for r in baseline), len(baseline))} | {pct(sum(r['utility'] for r in safe), len(safe))} | "
            f"{sum(r['no_output'] for r in runs)} | {sum(r['context_overflow'] for r in runs)} |"
        )
    if control:
        print("\nControl (injection task given as the user task):")
        for (track, model), runs in sorted(control.items()):
            solved = sorted({r["user_task"] for r in runs if r["utility"]})
            tasks = sorted({r["user_task"] for r in runs})
            print(f"- {track} / {model}: {len(solved)}/{len(tasks)} solved")


def compare(rows: list[dict], resamples: int, seed: int) -> None:
    by_model = defaultdict(dict)
    for row in rows:
        if row["run_type"] == "attack":
            by_model[(row["track"], row["model"])][(config(row), row["user_task"], row["injection_task"])] = row
    rng = random.Random(seed)
    print("\n| track | model | comparison | exposed pairs | only A / only B | ASR A - B [95 % CI] | p | p (Holm) |")
    print("|---|---|---|---|---|---|---|---|")
    for (track, model), cells in sorted(by_model.items()):
        results = {}
        for a, b in itertools.combinations(CONFIGS, 2):
            pairs = []
            for (cfg, user_task, injection_task), row_a in cells.items():
                row_b = cells.get((b, user_task, injection_task))
                if cfg == a and row_b and row_a["exposed"] and row_b["exposed"]:
                    pairs.append((user_task, row_a["attack_success_dedup"], row_b["attack_success_dedup"]))
            only_a = sum(x and not y for _, x, y in pairs)
            only_b = sum(y and not x for _, x, y in pairs)
            results[(a, b)] = (pairs, only_a, only_b, mcnemar_exact(only_a, only_b))
        secondary = holm({k: v[3] for k, v in results.items() if k != PRIMARY and v[1] + v[2] >= MIN_DISCORDANT})
        for (a, b), (pairs, only_a, only_b, p) in results.items():
            if not pairs:
                continue
            diff = sum(x - y for _, x, y in pairs) / len(pairs)
            low, high = bootstrap_diff(pairs, resamples, rng)
            tested = only_a + only_b >= MIN_DISCORDANT
            label = f"{a} vs {b}" + (" (primary)" if (a, b) == PRIMARY else "")
            p_text = f"{p:.3g}" if tested else "n/a"
            holm_text = "-" if (a, b) == PRIMARY else (f"{secondary[(a, b)]:.3g}" if tested else "n/a")
            print(
                f"| {track} | {model} | {label} | {len(pairs)} | {only_a} / {only_b} | "
                f"{diff:+.1%} [{low:+.1%}, {high:+.1%}] | {p_text} | {holm_text} |"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", nargs="+", type=Path)
    parser.add_argument("--bootstrap", type=int, default=2000, help="bootstrap resamples (default 2000)")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    rows = [json.loads(line) for path in args.results for line in path.read_text(encoding="utf-8").splitlines() if line]
    describe(rows)
    compare(rows, args.bootstrap, args.seed)


if __name__ == "__main__":
    main()
