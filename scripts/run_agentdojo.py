"""Runs the AgentDojo benchmark with a few fixes.

1. Re-running tasks: AgentDojo always tries to load an existing result before running a task
   (even with `-f`), and loading crashes with pydantic 2.13 ("`TaskResults` is not fully defined").
   Rebuilding the model first fixes it.
2. Tool calls returned as text: Llama-3.1-8B at deepinfra sometimes returns a tool call as plain
   text (`<function=name>{"arg": ...}`) instead of structured `tool_calls` - for the identical request,
   so it is the provider's parser, not the prompt. Such calls are converted to structured tool calls
   here and every conversion is logged ("recovered text tool call"), so it can be counted.
3. Output length cap: AgentDojo sets no `max_tokens`, so a model stuck in a loop (seen with Bielik
   on vLLM) generates until the context is full, which takes many minutes. Set the
   `AGENTDOJO_MAX_TOKENS` environment variable to cap every completion.
4. Reasoning blocks: `<think>...</think>` is removed from answers and each removal is logged
   ("stripped reasoning block").
5. System role: AgentDojo sends the system prompt with role `developer`, which some servers reject
   (Mistral API, vLLM with `--tokenizer-mode mistral`). Set `AGENTDOJO_SYSTEM_ROLE=1` to send `system`.
6. Prompt-based tool calling for models whose chat template has no tool support (PLLuM): set
   `AGENTDOJO_PROMPTING=1` with the OPENAI_COMPATIBLE provider (see `JsonToolCallPromptingLLM`).
7. Translations (data/<lang>/): `AGENTDOJO_TASK_LANG=pl` replaces the user prompts; a task without a translation
   fails instead of silently running in English. The attack `important_instructions_pl` injects the Polish
   template with Polish goals; its English counterpart is `important_instructions_no_model_name`. Every
   translation stores the English source, which must equal AgentDojo's text. Only benchmark v1.2.2.
8. Non-ASCII in tool results: AgentDojo dumps tool results with `yaml.safe_dump`, which escapes every non-ASCII
   character, so the model saw a Polish injection as `wa\\u017Cna wiadomo\\u015B\\u0107`. Tool results are now
   dumped with `allow_unicode=True` (always, in both languages; English environment data is ASCII apart from a
   few U+FFFD characters).

Usage: same arguments as `python -m agentdojo.scripts.benchmark`, e.g.
    python scripts/run_agentdojo.py -s workspace -ut user_task_0 --model GPT_4O_MINI_2024_07_18
"""

import json
import logging
import os
import re
import sys
import uuid
from functools import partial
from pathlib import Path

import yaml
from openai import NOT_GIVEN

from agentdojo.agent_pipeline import agent_pipeline, tool_execution
from agentdojo.agent_pipeline.llms import openai_llm
from agentdojo.agent_pipeline.llms.openai_llm import OpenAILLM
from agentdojo.attacks.attack_registry import register_attack
from agentdojo.attacks.important_instructions_attacks import ImportantInstructionsAttack
from agentdojo.benchmark import TaskResults
from agentdojo.functions_runtime import EmptyEnv, FunctionCall
from agentdojo.scripts.benchmark import main
from agentdojo.task_suite.load_suites import get_suites
from agentdojo.types import ChatAssistantMessage, get_text_content_as_str, text_content_block_from_string

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


THINK_BLOCK = re.compile(r"<think>.*?(</think>|$)", re.DOTALL)


def _strip_reasoning(message):
    """Removes `<think>...</think>` blocks (an unclosed block runs to the end of the text).

    Models such as Bielik sometimes reason spontaneously in `content`; AgentDojo's utility
    checkers would otherwise match strings inside the reasoning.
    """
    if message.content and "<think>" in message.content:
        logging.warning("stripped reasoning block from the answer")
        message.content = THINK_BLOCK.sub("", message.content).strip()
    return message


def _openai_to_assistant_message_with_text_calls(message):
    message = _strip_reasoning(message)
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

MAX_TOKENS = int(os.environ["AGENTDOJO_MAX_TOKENS"]) if os.environ.get("AGENTDOJO_MAX_TOKENS") else NOT_GIVEN


@openai_llm.retry(
    wait=openai_llm.wait_random_exponential(multiplier=1, max=40),
    stop=openai_llm.stop_after_attempt(3),
    reraise=True,
    retry=openai_llm.retry_if_not_exception_type((openai_llm.openai.BadRequestError, openai_llm.openai.UnprocessableEntityError)),
)
def _chat_completion_request_with_max_tokens(
    client, model, messages, tools, reasoning_effort, temperature=0.0, stop=NOT_GIVEN
):
    """Same as `openai_llm.chat_completion_request`, plus the optional `max_tokens` cap and `stop`."""
    return client.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools or NOT_GIVEN,
        tool_choice="auto" if tools else NOT_GIVEN,
        temperature=temperature if temperature is not None else NOT_GIVEN,
        reasoning_effort=reasoning_effort or NOT_GIVEN,
        max_tokens=MAX_TOKENS,
        stop=stop,
    )


openai_llm.chat_completion_request = _chat_completion_request_with_max_tokens

_message_to_openai = openai_llm._message_to_openai


def _message_to_openai_system_role(message, model_name):
    """Same as `openai_llm._message_to_openai`, but sends the system prompt with role `system`."""
    converted = _message_to_openai(message, model_name)
    return {**converted, "role": "system"} if converted["role"] == "developer" else converted


if os.environ.get("AGENTDOJO_SYSTEM_ROLE") == "1":
    openai_llm._message_to_openai = _message_to_openai_system_role


TOOL_CALL_BLOCK = re.compile(r"<tool_call>\s*")


class JsonToolCallPromptingLLM(OpenAILLM):
    """Prompt-based tool calling for models whose chat template has no tool support (PLLuM).

    The tools are described in the system prompt and the model answers with
    `<tool_call>{"name": ..., "arguments": {...}}</tool_call>` - the format of the Bielik tool template.
    AgentDojo's own `PromptingLLM` (`<function-call>` format) was tried first: PLLuM-12B made no tool call in
    workspace tasks 0 and 1 (it asked the user to run the tool). Generation stops at `</tool_call>`, so the
    model makes one call per turn and cannot invent the result after it. Tool results come back as user
    messages, and consecutive messages with the same role are merged, because such templates allow one system
    message and strictly alternating user/assistant turns.
    """

    _TOOL_PROMPT = (
        "You can call tools. To call a tool, answer ONLY with:\n"
        '<tool_call>{{"name": <tool-name>, "arguments": <args-dict>}}</tool_call>\n'
        "The tool result will be sent back to you. When you have the final answer, write it without any tool call."
        "\n\nAvailable tools:\n\n{tools}"
    )
    _MAX_ATTEMPTS = 3

    def _system_prompt(self, messages, runtime):
        system = get_text_content_as_str(messages[0]["content"]) if messages and messages[0]["role"] == "system" else ""
        if not runtime.functions:
            return system
        tools = "\n\n".join(
            json.dumps(
                {"name": f.name, "description": f.description, "parameters": f.parameters.model_json_schema()}, indent=2
            )
            for f in runtime.functions.values()
        )
        return f"{system}\n\n{self._TOOL_PROMPT.format(tools=tools)}".strip()

    @staticmethod
    def _to_chat(message):
        if message["role"] == "tool":
            result = f"Error: {message['error']}" if message["error"] else get_text_content_as_str(message["content"])
            return "user", f"<tool_response>\n{result}\n</tool_response>"
        content = get_text_content_as_str(message["content"] or [])
        if message["role"] == "assistant" and message["tool_calls"]:
            calls = "".join(
                f'<tool_call>{json.dumps({"name": c.function, "arguments": dict(c.args)}, ensure_ascii=False)}</tool_call>'
                for c in message["tool_calls"]
            )
            content = f"{content}\n{calls}".strip()
        return message["role"], content

    @staticmethod
    def _parse(text):
        """Returns (content, tool call or None); raises ValueError for a malformed call."""
        match = TOOL_CALL_BLOCK.search(text)
        if match is None:
            return text.strip(), None
        call, _ = json.JSONDecoder().raw_decode(text, match.end())
        if not isinstance(call, dict) or not isinstance(call.get("name"), str):
            raise ValueError('expected {"name": <tool-name>, "arguments": <args-dict>}')
        args = call.get("arguments") or {}
        if not isinstance(args, dict):
            raise ValueError("arguments must be a JSON object")
        tool_call = FunctionCall(function=call["name"], args=args, id=f"prompt_call_{uuid.uuid4().hex[:12]}")
        return text[: match.start()].strip(), tool_call

    def query(self, query, runtime, env=EmptyEnv(), messages=[], extra_args={}):
        chat = [{"role": "system", "content": self._system_prompt(messages, runtime)}]
        for message in messages:
            if message["role"] == "system":
                continue
            role, content = self._to_chat(message)
            if chat[-1]["role"] == role:
                chat[-1]["content"] += "\n\n" + content
            else:
                chat.append({"role": role, "content": content})

        for _ in range(self._MAX_ATTEMPTS):
            completion = _chat_completion_request_with_max_tokens(
                self.client, self.model, chat, [], None, self.temperature, stop=["</tool_call>"]
            )
            text = completion.choices[0].message.content or ""
            try:
                content, tool_call = self._parse(text)
                break
            except ValueError as e:
                logging.warning("unparsable prompt-based tool call, asking again: %s", e)
                chat = [*chat, {"role": "assistant", "content": text}, {"role": "user", "content": f"Invalid tool call: {e}"}]
        else:
            content, tool_call = text, None
        output = ChatAssistantMessage(
            role="assistant",
            content=[text_content_block_from_string(content)] if content else None,
            tool_calls=[tool_call] if tool_call else None,
        )
        return query, runtime, env, [*messages, output], extra_args


_get_llm = agent_pipeline.get_llm


def _get_llm_prompting(provider, model, model_id, tool_delimiter):
    llm = _get_llm(provider, model, model_id, tool_delimiter)
    if provider == "openai-compatible":
        return JsonToolCallPromptingLLM(llm.client, llm.model)
    return llm


if os.environ.get("AGENTDOJO_PROMPTING") == "1":
    agent_pipeline.get_llm = _get_llm_prompting


def _yaml_dump_unicode(data) -> str:
    return yaml.safe_dump(data, allow_unicode=True)


agent_pipeline.tool_result_to_str = partial(tool_execution.tool_result_to_str, dump_fn=_yaml_dump_unicode)


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BENCHMARK_VERSION = "v1.2.2"


def load_translations(lang: str, name: str) -> dict:
    path = DATA_DIR / lang / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def translated(entry: dict, lang: str, key: str, en_text: str) -> str:
    if entry["en"] != en_text:
        raise ValueError(f"{key}: the English source in data/{lang}/ differs from AgentDojo's text")
    return entry[lang]


def _untranslated_prompt(task_id: str, lang: str) -> property:
    def prompt(self):
        raise KeyError(f"{task_id} has no '{lang}' translation in data/{lang}/")

    return property(prompt)


def translate_user_tasks(lang: str) -> None:
    for suite_name, suite in get_suites(BENCHMARK_VERSION).items():
        translations = load_translations(lang, suite_name).get("user_tasks", {})
        for task_id, task in suite.user_tasks.items():
            if task_id in translations:
                type(task).PROMPT = translated(translations[task_id], lang, task_id, task.PROMPT)
            else:
                type(task).PROMPT = _untranslated_prompt(task_id, lang)


@register_attack
class ImportantInstructionsAttackPL(ImportantInstructionsAttack):
    """`important_instructions` with the Polish template, Polish goals and a fixed model name."""

    name = "important_instructions_pl"
    lang = "pl"

    def __init__(self, task_suite, target_pipeline) -> None:
        super().__init__(task_suite, target_pipeline)
        template = load_translations(self.lang, "attacks")["important_instructions"]
        self.jailbreak = translated(template, self.lang, "important_instructions", ImportantInstructionsAttack._JB_STRING)
        self.model_name = template["model_name"][self.lang]
        self.goals = load_translations(self.lang, task_suite.name).get("injection_tasks", {})

    def attack(self, user_task, injection_task) -> dict[str, str]:
        if injection_task.ID not in self.goals:
            raise KeyError(f"{injection_task.ID} has no '{self.lang}' translation in data/{self.lang}/")
        goal = translated(self.goals[injection_task.ID], self.lang, injection_task.ID, injection_task.GOAL)
        return {
            inj: self.jailbreak.format(goal=goal, user=self.user_name, model=self.model_name)
            for inj in self.get_injection_candidates(user_task)
        }


if os.environ.get("AGENTDOJO_TASK_LANG", "en") != "en":
    if "--benchmark-version" in sys.argv and sys.argv[sys.argv.index("--benchmark-version") + 1] != BENCHMARK_VERSION:
        raise SystemExit(f"translations exist only for {BENCHMARK_VERSION}")
    translate_user_tasks(os.environ["AGENTDOJO_TASK_LANG"])

if __name__ == "__main__":
    main()
