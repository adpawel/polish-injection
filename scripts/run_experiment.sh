#!/usr/bin/env bash
# Full IPI experiment (notes/protocol.md): one call runs one model in one configuration.
#
#   scripts/run_experiment.sh <model> <task_lang> <payload_lang|none> [extra run_agentdojo.py args, e.g. -ut user_task_0]
#
#   model:        gpt-4o-mini | qwen3-8b | pllum-12b | bielik-11b-v3 | mistral-nemo
#   task_lang:    en | pl
#   payload_lang: en | pl   -> attack runs (40 user tasks x the 10 injection tasks) + the control runs
#                 none      -> utility baseline without attack (40 user tasks)
#
# Logs go to runs/full/<model>-<task_lang>; finished runs are skipped (no -f), so an interrupted call can simply be
# repeated. The harness must be committed: the logs record the commit and export_results.py rejects dirty runs.
# vLLM models read VLLM_BASE_URL / VLLM_API_KEY from .env; the matching server must be running (notes/runpod.md).
# Run from the repository root in Git Bash.
set -euo pipefail

# notes/protocol.md 2.2
INJECTION_TASKS=(0 1 2 3 4 5 6 10 11 13)
PY=.venv/Scripts/python.exe

if [ $# -lt 3 ]; then
    sed -n '2,15p' "$0"
    exit 2
fi
model=$1 task_lang=$2 payload=$3
shift 3

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "uncommitted changes in tracked files - commit the harness first" >&2
    exit 1
fi

set -a
. ./.env
set +a
export AGENTDOJO_MAX_TOKENS=1024 AGENTDOJO_TASK_LANG=$task_lang PYTHONIOENCODING=utf-8
args=(-s workspace --logdir "runs/full/$model-$task_lang")

case $model in
    gpt-4o-mini)
        args+=(--model GPT_4O_MINI_2024_07_18) ;;
    qwen3-8b)
        export AGENTDOJO_SYSTEM_ROLE=1
        system="$($PY -c 'from agentdojo.agent_pipeline.agent_pipeline import load_system_message; print(load_system_message(None)+" /no_think", end="")')"
        args+=(--model OPENAI_COMPATIBLE --model-id "Qwen/Qwen3-8B:nscale" --system-message "$system") ;;
    pllum-12b|mistral-nemo|bielik-11b-v3)
        export OPENAI_COMPATIBLE_BASE_URL="$VLLM_BASE_URL" OPENAI_COMPATIBLE_API_KEY="$VLLM_API_KEY"
        [ "$model" != bielik-11b-v3 ] && export AGENTDOJO_PROMPTING=1
        served=$($PY -c "import json,sys,urllib.request as u; r=u.Request(sys.argv[1]+'/models', headers={'Authorization': 'Bearer '+sys.argv[2]}); print(json.load(u.urlopen(r, timeout=30))['data'][0]['id'])" "$VLLM_BASE_URL" "$VLLM_API_KEY")
        if [ "$served" != "$model" ]; then
            echo "the pod serves '$served', not '$model'" >&2
            exit 1
        fi
        args+=(--model OPENAI_COMPATIBLE --model-id "$model") ;;
    *)
        echo "unknown model: $model" >&2
        exit 2 ;;
esac

case $payload in
    en) args+=(--attack important_instructions_no_model_name) ;;
    pl) args+=(--attack important_instructions_pl) ;;
    none) ;;
    *) echo "payload_lang must be en, pl or none" >&2; exit 2 ;;
esac
if [ "$payload" != none ]; then
    for i in "${INJECTION_TASKS[@]}"; do
        args+=(-it "injection_task_$i")
    done
fi

mkdir -p runs/full
log="runs/full/$model-$task_lang-$payload.log"
echo "$(date '+%F %T') $model $task_lang/$payload $*" >> "$log"
$PY scripts/run_agentdojo.py "${args[@]}" "$@" >> "$log" 2>&1
echo "$model $task_lang/$payload: done (log $log)"
