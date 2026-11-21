"""Checks that the MCP payload reaches a model's prompt (notes/protocol.md 3.4), before the runs of that model.

For every vector and payload language, the request the harness would send is captured exactly (the pipeline of
scripts/run_mcp.py is built with the model's settings and stopped at the first model call), with the longest goal
as the payload:
- V1/V3 (poisoned description): the first request; V2 (poisoned result): the request after one `bizutils` call,
  with the real poisoned result of the server (searched for as that result's YAML, whose `notice` is checked to
  be the payload).
Client side: the payload text must be in the request (in the tool list for native tool calling, in the system
prompt for prompt-based tool calling). Server side (vLLM): the request is rendered by the served chat template
(`/tokenize` with the messages and tools, then `/detokenize`); the payload must be in the rendered prompt, verbatim
or JSON-escaped (a template that dumps the tools with `tojson` escapes non-ASCII letters, which is reported), and
the prompt plus the completion cap must fit into the model's context.

Usage (from the repository root, Git Bash; the vLLM server of the model must be running, see notes/runpod.md):
    .venv/Scripts/python.exe scripts/check_mcp_delivery.py bielik-11b-v3
    .venv/Scripts/python.exe scripts/check_mcp_delivery.py pllum-12b --offline   # client side only, no server
Exit code 1 if any check fails.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO), str(REPO / "scripts")]

# the model settings of scripts/run_mcp_experiment.sh (they are read when the harness is imported)
MODELS = {
    "gpt-4o-mini": {"enum": "GPT_4O_MINI_2024_07_18", "env": {}, "suffix": ""},
    "bielik-11b-v3": {"enum": "OPENAI_COMPATIBLE", "env": {}, "suffix": ""},
    "pllum-12b": {"enum": "OPENAI_COMPATIBLE", "env": {"AGENTDOJO_PROMPTING": "1"}, "suffix": ""},
    "mistral-nemo": {"enum": "OPENAI_COMPATIBLE", "env": {"AGENTDOJO_PROMPTING": "1"}, "suffix": ""},
    "qwen3-8b": {"enum": "OPENAI_COMPATIBLE", "env": {"AGENTDOJO_SYSTEM_ROLE": "1"}, "suffix": " /no_think"},
}
VECTORS = ["tp_third_party", "mcp_result", "tp_trusted"]
MAX_TOKENS = 4096  # AGENTDOJO_MAX_TOKENS of the runs


class Captured(Exception):
    pass


def server_root() -> str:
    return re.sub(r"/v1/?$", "", os.environ["VLLM_BASE_URL"])


def post(path: str, body: dict) -> dict:
    request = urllib.request.Request(
        server_root() + path, data=json.dumps(body).encode(), method="POST",
        # the RunPod proxy rejects urllib's default User-Agent (403)
        headers={"Authorization": f"Bearer {os.environ['VLLM_API_KEY']}", "Content-Type": "application/json",
                 "User-Agent": "mcp-delivery-check"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def found(payload: str, text: str) -> str | None:
    """How the payload appears in the text: 'verbatim', 'json-escaped', 'ascii-escaped' or None."""
    squash = lambda s: re.sub(r"\s+", " ", s)  # noqa: E731  (templates may re-wrap the text)
    text = squash(text)
    for how, form in (("verbatim", payload), ("json-escaped", json.dumps(payload, ensure_ascii=False)[1:-1]),
                      ("ascii-escaped", json.dumps(payload)[1:-1])):
        if squash(form) in text:
            return how
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model", choices=list(MODELS))
    parser.add_argument("--offline", action="store_true", help="client-side checks only (no server)")
    args = parser.parse_args()
    settings = MODELS[args.model]
    os.environ.update(settings["env"])
    if settings["enum"] == "OPENAI_COMPATIBLE":
        os.environ.setdefault("OPENAI_COMPATIBLE_BASE_URL", os.environ.get("VLLM_BASE_URL", "http://localhost/v1"))
        os.environ.setdefault("OPENAI_COMPATIBLE_API_KEY", os.environ.get("VLLM_API_KEY", "none"))
    offline = args.offline or settings["enum"] != "OPENAI_COMPATIBLE"

    import run_agentdojo as harness  # noqa: E402  (after the environment: it reads the adapter switches)
    from agentdojo.agent_pipeline.agent_pipeline import AgentPipeline, PipelineConfig
    from agentdojo.agent_pipeline.llms import openai_llm
    from agentdojo.models import ModelsEnum

    from mcp_track import attacks, world
    from mcp_track.runtime import McpFunctionsRuntime, McpHub
    from mcp_track.tasks import GOALS, SYSTEM_MESSAGE, USER_TASKS

    captured = {}

    def capture(client, model, messages, tools, *rest, **kwargs):
        captured.update(messages=list(messages), tools=list(tools or []))
        raise Captured

    openai_llm.chat_completion_request = capture  # native tool calling
    harness._chat_completion_request_with_max_tokens = capture  # prompt-based tool calling
    prompting = os.environ.get("AGENTDOJO_PROMPTING") == "1"
    pipeline = AgentPipeline.from_config(PipelineConfig(
        llm=ModelsEnum[settings["enum"]].value, model_id=args.model if settings["enum"] == "OPENAI_COMPATIBLE" else None,
        defense=None, system_message_name=None, system_message=SYSTEM_MESSAGE + settings["suffix"]))

    task = USER_TASKS["user_task_0"]  # calls get_exchange_rate (bizutils) as its second step
    goal_id = max(GOALS, key=lambda g: len(GOALS[g].goal))
    failures = 0
    print(f"model {args.model} ({'prompt-based' if prompting else 'native'} tool calling), payload = {goal_id}, "
          f"{'client side only' if offline else 'server ' + server_root()}\n")
    for vector in VECTORS:
        for lang in ("en", "pl"):
            text = needle = attacks.payload(goal_id, lang)
            with tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp) / "world.db"
                world.create(db, world.load_seed("en"))
                with McpHub(db, attacks.variants(vector, text)) as hub:
                    captured.clear()
                    try:
                        pipeline.query(task.prompt, McpFunctionsRuntime(hub))
                    except Captured:
                        pass
                    messages, tools = captured["messages"], captured["tools"]
                    if vector == "mcp_result":
                        call_args = {"base": "EUR", "quote": "PLN"}
                        result, _ = hub.call_tool("get_exchange_rate", call_args)
                        # the payload arrives as the YAML of the result (re-wrapped, quotes doubled)
                        assert yaml.safe_load(result)["notice"] == text, "notice of the result is not the payload"
                        needle = result
                        call = {"name": "get_exchange_rate", "arguments": call_args}
                        if prompting:  # as JsonToolCallPromptingLLM sends a call and its result
                            messages = [*messages, {"role": "assistant", "content": f"<tool_call>{json.dumps(call)}</tool_call>"},
                                        {"role": "user", "content": f"<tool_response>\n{result}\n</tool_response>"}]
                        else:
                            messages = [*messages,
                                        {"role": "assistant", "content": None, "tool_calls": [
                                            {"id": "call_0", "type": "function",
                                             "function": {"name": call["name"], "arguments": json.dumps(call_args)}}]},
                                        {"role": "tool", "tool_call_id": "call_0", "content": result}]
            client = found(needle, json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False))
            line = f"{vector:15} {lang}: request {client or 'MISSING'}"
            ok = client is not None
            if not offline:
                body = {"model": args.model, "messages": messages, "add_generation_prompt": True}
                if tools:
                    body["tools"] = tools
                try:
                    tokens = post("/tokenize", body)
                    prompt = post("/detokenize", {"model": args.model, "tokens": tokens["tokens"]})["prompt"]
                    rendered = found(needle, prompt)
                    fits = tokens["count"] + MAX_TOKENS <= tokens["max_model_len"]
                    names = all(t["function"]["name"] in prompt for t in tools) if tools else True
                    line += (f"; rendered {rendered or 'MISSING'}; {tokens['count']} tokens of "
                             f"{tokens['max_model_len']} ({'fits' if fits else 'TOO LONG'} with {MAX_TOKENS} output)"
                             f"{'' if names else '; TOOL NAMES MISSING'}")
                    ok = ok and rendered is not None and fits and names
                except Exception as e:  # noqa: BLE001  (reported, counts as a failure)
                    line += f"; server check FAILED: {e}"
                    ok = False
            failures += not ok
            print(("ok   " if ok else "FAIL ") + line)
    print("\nall checks passed" if not failures else f"\n{failures} check(s) failed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
