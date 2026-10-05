"""Minimal check that a model behind an OpenAI-compatible API returns native tool calls.

Sends one prompt (EN and PL) with a single weather tool and prints whether the answer
came back as structured `tool_calls` or as plain text.

Usage:
    python scripts/smoke_tool_calling.py speakleash/Bielik-11B-v3.0-Instruct:publicai
Uses OPENAI_COMPATIBLE_BASE_URL and OPENAI_COMPATIBLE_API_KEY from .env.
"""

import os
import sys

import openai
from dotenv import load_dotenv

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "City name"}},
                "required": ["city"],
            },
        },
    }
]

PROMPTS = {
    "en": "What is the weather in Krakow right now?",
    "pl": "Jaka jest teraz pogoda w Krakowie?",
}


def main(model: str) -> None:
    load_dotenv(".env")
    client = openai.OpenAI(
        base_url=os.environ["OPENAI_COMPATIBLE_BASE_URL"],
        api_key=os.environ["OPENAI_COMPATIBLE_API_KEY"],
    )
    for lang, prompt in PROMPTS.items():
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Use tools when needed."},
                {"role": "user", "content": prompt},
            ],
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.0,
        )
        message = completion.choices[0].message
        print(f"--- {lang}")
        print("tool_calls:", [(c.function.name, c.function.arguments) for c in message.tool_calls or []])
        print("content:", message.content)
        print("usage:", completion.usage)


if __name__ == "__main__":
    main(sys.argv[1])
