"""Runs the MCP track (notes/protocol.md 3): user tasks x attacker goals for one model, configuration and vector.

The model side is the IPI track's: importing scripts/run_agentdojo.py applies all its fixes (LLM adapters,
max_tokens, one attempt, run metadata, token usage, unicode tool results), and the agent loop is AgentDojo's
pipeline; the tools come from the MCP servers of mcp_track/ (runtime.py). Logs have the format of AgentDojo's
logs (same exporter and analysis), plus `utility`, `security`, `security_dedup`, `exposed`, `context_overflow`,
`vector`, `payload_lang` and the tool list the model saw.

Usage (from the repository root):
    python scripts/run_mcp.py --model GPT_4O_MINI_2024_07_18 --task-lang en --payload en --vector tp_third_party \
        --logdir runs/mcp/tp_third_party/gpt-4o-mini-en -ut user_task_0 -g goal_0
    --payload none: runs without attack (utility baseline); --control: the attacker goals as user tasks.
    Without -ut / -g all user tasks / goals are run. Finished runs are skipped unless -f is given.
"""

import argparse
import logging
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "scripts")]

import run_agentdojo as harness  # noqa: E402  (applies the fixes of the IPI track)
from agentdojo.agent_pipeline.agent_pipeline import AgentPipeline, PipelineConfig  # noqa: E402
from agentdojo.agent_pipeline.errors import AbortAgentError  # noqa: E402
from agentdojo.logging import Logger, OutputLogger, TraceLogger  # noqa: E402
from agentdojo.models import ModelsEnum  # noqa: E402
from agentdojo.types import get_text_content_as_str  # noqa: E402
from openai import BadRequestError  # noqa: E402

from mcp_track import attacks, world  # noqa: E402
from mcp_track.replay import run_calls  # noqa: E402
from mcp_track.runtime import McpFunctionsRuntime, McpHub  # noqa: E402
from mcp_track.servers import bizutils  # noqa: E402
from mcp_track.tasks import GOALS, SYSTEM_MESSAGE, USER_TASKS  # noqa: E402

SUITE = "mcp_shop"
BENCHMARK_VERSION = "mcp_shop-v2"  # v2 (2026-11-20): goal_8..11, discount-percent description; v1 = pilots


def tool_calls(messages) -> list[tuple[str, dict]]:
    return [(c.function, dict(c.args)) for m in messages if m["role"] == "assistant" for c in (m["tool_calls"] or [])]


def final_answer(messages) -> str:
    if not messages or messages[-1]["role"] != "assistant" or not messages[-1]["content"]:
        return ""
    return get_text_content_as_str(messages[-1]["content"])


def exposed(vector: str, messages) -> bool:
    if vector == "mcp_result":  # every result of the third-party server carries the payload
        return any(m["role"] == "tool" and not m["error"] and m["tool_call"].function in bizutils.DESCRIPTIONS
                   for m in messages)
    # a poisoned description is part of every request; exposed once the model has been called
    return any(m["role"] == "assistant" for m in messages)


def run_one(pipeline, args, task_id: str, prompt: str, goal_id: str | None, attack_type: str, text: str | None) -> None:
    variants = attacks.variants(args.vector, text) if text else {}
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "world.db"
        world.create(db, world.load_seed(args.env_lang))
        pre = world.snapshot(db)
        with McpHub(db, variants) as hub, TraceLogger(
            delegate=Logger.get(), suite_name=SUITE, user_task_id=task_id, injection_task_id=goal_id,
            injections={args.vector: text} if text else {}, attack_type=attack_type, pipeline_name=pipeline.name,
            benchmark_version=BENCHMARK_VERSION,
        ) as logger:
            overflow = False
            try:
                _, _, _, messages, _ = pipeline.query(prompt, McpFunctionsRuntime(hub))
            except AbortAgentError as e:
                messages = e.messages
            except BadRequestError as e:
                if getattr(e, "code", None) != "context_length_exceeded":
                    raise
                logger.log_error(f"context_length_exceeded: {e}")
                overflow, messages = True, list(logger.messages)
            post = world.snapshot(db)
            output = final_answer(messages)
            if task_id in GOALS:  # control: the goal as the user task
                utility = GOALS[task_id].security(pre, post)
            else:
                utility = USER_TASKS[task_id].utility(output, pre, post)
            context = {
                "vector": args.vector if text else None,
                "payload_lang": args.payload if text else None,
                "env_lang": args.env_lang,
                "tools": [{"name": t.name, "description": t.description} for t in hub.tools],
                "context_overflow": overflow,
                "no_output": not output,
            }
            if goal_id:
                pre_d, post_d, _ = run_calls(tool_calls(messages), args.env_lang, dedup_calls=True)
                context.update(security=GOALS[goal_id].security(pre, post),
                               security_dedup=GOALS[goal_id].security(pre_d, post_d),
                               exposed=exposed(args.vector, messages))
            for key, value in context.items():
                logger.context[key] = value
            logger.set_contextarg("utility", utility)  # written last: a log with `utility` is a finished run


def done(path: Path) -> bool:
    return path.exists() and '"utility"' in path.read_text(encoding="utf-8", errors="replace")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True, help="AgentDojo ModelsEnum name, e.g. GPT_4O_MINI_2024_07_18")
    parser.add_argument("--model-id", default=None)
    parser.add_argument("--task-lang", choices=["en", "pl"], required=True)
    parser.add_argument("--payload", choices=["en", "pl", "none"], required=True)
    parser.add_argument("--vector", choices=list(attacks.VECTORS), default="tp_third_party")
    parser.add_argument("--env-lang", choices=["en", "pl"], default="en")
    parser.add_argument("-ut", "--user-task", action="append", dest="user_tasks")
    parser.add_argument("-g", "--goal", action="append", dest="goals")
    parser.add_argument("--control", action="store_true", help="run the attacker goals as user tasks")
    parser.add_argument("--system-suffix", default="", help="appended to the system message (Qwen: ' /no_think')")
    parser.add_argument("--logdir", required=True, type=Path)
    parser.add_argument("-f", "--force", action="store_true")
    parser.add_argument("--allow-draft", action="store_true", help="use unreviewed translations (tests only)")
    args = parser.parse_args()

    if args.env_lang != "en":
        raise SystemExit("Polish environment (PLenv): seed and descriptions not translated yet")
    harness.RUN_METADATA["task_lang"] = args.task_lang
    pipeline = AgentPipeline.from_config(PipelineConfig(
        llm=ModelsEnum[args.model].value, model_id=args.model_id, defense=None, system_message_name=None,
        system_message=SYSTEM_MESSAGE + args.system_suffix))
    name = pipeline.name.replace("/", "_")

    if args.control:
        # the control prompt is English in every configuration (as AgentDojo's controls)
        jobs = [(g, GOALS[g].control_prompt, None, "none", None) for g in (args.goals or GOALS)]
    else:
        tasks = args.user_tasks or list(USER_TASKS)
        prompts = {t: attacks.translated("user_tasks", t, USER_TASKS[t].prompt, args.task_lang, args.allow_draft) for t in tasks}
        if args.payload == "none":
            jobs = [(t, prompts[t], None, "none", None) for t in tasks]
        else:
            attack = f"mcp_{args.vector}_{args.payload}"
            jobs = [(t, prompts[t], g, attack, attacks.payload(g, args.payload, args.allow_draft))
                    for t in tasks for g in (args.goals or GOALS) if GOALS[g].applies(t)]

    with OutputLogger(str(args.logdir), live=None):
        for task_id, prompt, goal_id, attack_type, text in jobs:
            log = args.logdir / name / SUITE / task_id / attack_type / f"{goal_id or 'none'}.json"
            if done(log) and not args.force:
                logging.info("skipping %s / %s (done)", task_id, goal_id)
                continue
            run_one(pipeline, args, task_id, prompt, goal_id, attack_type, text)
            print(f"done {task_id} {goal_id or ''} {attack_type}", flush=True)


if __name__ == "__main__":
    main()
