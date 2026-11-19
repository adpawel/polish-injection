#!/usr/bin/env bash
# MCP track (notes/protocol.md 3): one call runs one model in one configuration and vector.
#
#   scripts/run_mcp_experiment.sh <model> <task_lang> <payload_lang|none|control> [<vector>] [extra run_mcp.py args]
#
#   model:        gpt-4o-mini (others: added with their serving, as in run_experiment.sh)
#   task_lang:    en | pl
#   payload_lang: en | pl   -> attack runs (all user tasks x all goals) with <vector>
#                 none      -> utility baseline without attack (clean servers)
#                 control   -> the attacker goals as user tasks
#   vector:       tp_third_party | mcp_result | tp_trusted (attack runs only)
#
# Logs go to runs/mcp/<vector|none|control>/<model>-<task_lang>; finished runs are skipped, so an interrupted call can
# simply be repeated. The harness must be committed (the logs record the commit). Run from the repository root in
# Git Bash.
set -euo pipefail
PY=.venv/Scripts/python.exe

if [ $# -lt 3 ]; then
    sed -n '2,16p' "$0"
    exit 2
fi
model=$1 task_lang=$2 payload=$3
shift 3
vector=none
case $payload in
    en|pl) vector=${1:?vector needed for attack runs}; shift ;;
    none|control) ;;
    *) echo "payload_lang must be en, pl, none or control" >&2; exit 2 ;;
esac

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "uncommitted changes in tracked files - commit the harness first" >&2
    exit 1
fi

set -a
. ./.env
set +a
export AGENTDOJO_MAX_TOKENS=4096 PYTHONIOENCODING=utf-8

case $model in
    gpt-4o-mini) args=(--model GPT_4O_MINI_2024_07_18) ;;
    *) echo "unknown model: $model" >&2; exit 2 ;;
esac

case $payload in
    en|pl) args+=(--payload "$payload" --vector "$vector") ;;
    none) args+=(--payload none) ;;
    control) args+=(--payload none --control); vector=control ;;
esac

base=runs/mcp/$vector
mkdir -p "$base"
log="$base/$model-$task_lang-$payload.log"
echo "$(date '+%F %T') $model $task_lang/$payload $vector $*" >> "$log"
$PY scripts/run_mcp.py "${args[@]}" --task-lang "$task_lang" --logdir "$base/$model-$task_lang" "$@" >> "$log" 2>&1
echo "$model $task_lang/$payload $vector: done (log $log)"
