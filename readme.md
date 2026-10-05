# Project

Research context, questions and design: see [context.md](context.md).
AgentDojo findings: see [notes/agentdojo.md](notes/agentdojo.md).

## Setup

Requires Python 3.10+ and git.

```
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux/macOS
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your API key. Run all commands from the repo root,
because AgentDojo loads `.env` from the current directory.

## AgentDojo - example commands

`--model` is always required and takes the enum **name** (e.g. `GPT_4O_MINI_2024_07_18`);
`python -m agentdojo.scripts.benchmark --help` lists all options and models.

One user task, no attack (baseline utility):
```
python scripts/run_agentdojo.py -s workspace -ut user_task_0 --model GPT_4O_MINI_2024_07_18
```

One user task with one injection task:
```
python scripts/run_agentdojo.py -s workspace -ut user_task_0 -it injection_task_0 --model GPT_4O_MINI_2024_07_18 --attack important_instructions
```

Useful options:
- `-s` suite: `workspace`, `travel`, `banking`, `slack` (repeatable)
- `-ut` / `-it` user / injection task (repeatable)
- `--logdir` output directory (default `./runs`)
- `-f` re-run even if results already exist (otherwise existing runs are skipped)

Always run through `scripts/run_agentdojo.py` (same options as `python -m agentdojo.scripts.benchmark`):
plain AgentDojo crashes when a result for the task already exists in the log directory, even with `-f`,
and the script also recovers tool calls that a provider returns as plain text (see its docstring).

Results are written to `runs/<model>/<suite>/<user_task>/<attack|none>/<injection_task|none>.json`.
`utility: true` = the user task was completed; `security: true` = **the attack succeeded**.
