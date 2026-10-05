"""Runs the AgentDojo benchmark with two fixes.

1. Re-running tasks: AgentDojo always tries to load an existing result before running a task
   (even with `-f`), and loading crashes with pydantic 2.13 ("`TaskResults` is not fully defined").
   Rebuilding the model first fixes it.
2. Tool calls returned as text: Llama-3.1-8B at deepinfra sometimes returns a tool call as plain
   text (`<function=name>{"arg": ...}`) instead of structured `tool_calls` - for the identical request,
   so it is the provider's parser, not the prompt. Such calls are converted to structured tool calls
   here and every conversion is logged ("recovered text tool call"), so it can be counted.

Usage: same arguments as `python -m agentdojo.scripts.benchmark`, e.g.
    python scripts/run_agentdojo.py -s workspace -ut user_task_0 --model GPT_4O_MINI_2024_07_18
"""

import json
import logging
import re
import uuid

from agentdojo.agent_pipeline.llms import openai_llm
from agentdojo.benchmark import TaskResults
from agentdojo.functions_runtime import FunctionCall
from agentdojo.scripts.benchmark import main
from agentdojo.types import text_content_block_from_string

TaskResults.model_rebuild()

TEXT_TOOL_CALL = re.compile(r"<function=([\w.-]+)>")
_openai_to_assistant_message = openai_llm._openai_to_assistant_message


def _parse_text_tool_calls(text: str) -> tuple[list[FunctionCall], str]:
    """Extracts `<function=name>{json}[</function>]` calls; returns the calls and the remaining text."""
    calls, rest, pos = [], [], 0
    for match in TEXT_TOOL_CALL.finditer(text):
        if match.start() < pos:
            continue
        try:
            args, end = json.JSONDecoder().raw_decode(text, match.end())
        except json.JSONDecodeError:
            continue
        if not isinstance(args, dict):
            continue
        calls.append(FunctionCall(function=match.group(1), args=args, id=f"text_call_{uuid.uuid4().hex[:12]}"))
        rest.append(text[pos : match.start()])
        pos = end + len("</function>") if text.startswith("</function>", end) else end
    rest.append(text[pos:])
    return calls, "".join(rest).strip()


def _openai_to_assistant_message_with_text_calls(message):
    converted = _openai_to_assistant_message(message)
    if converted["tool_calls"] or not message.content:
        return converted
    calls, rest = _parse_text_tool_calls(message.content)
    if not calls:
        return converted
    logging.warning("recovered text tool call(s): %s", [call.function for call in calls])
    content = [text_content_block_from_string(rest)] if rest else None
    return {**converted, "content": content, "tool_calls": calls}


openai_llm._openai_to_assistant_message = _openai_to_assistant_message_with_text_calls

if __name__ == "__main__":
    main()
