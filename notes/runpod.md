# Self-hosted models on RunPod (vLLM)

Commands to type in the pod's **Web Terminal** (Connect → Web Terminal). Paste one line at a time.
Background and findings for each model: [models.md](models.md).

## What lives where

- **Network volume** (datacenter ca-mtl-1, 94 GB, mounted at `/workspace`). It is kept between sessions:
  - `/workspace/venv` (Python 3.12, vLLM 0.24.0+cu129);
  - `/workspace/bielik-tools` (commit `77c4f42`);
  - `/workspace/hf` (Hugging Face cache with the weights of Bielik, Mistral-Nemo and PLLuM-12B);
  - `/workspace/vllm_api_key` (the server's API key, also stored locally in `.env` as `VLLM_API_KEY`).
- **Pod**: created for a session and **terminated** afterwards (a pod with a network volume cannot be
  stopped, only terminated; the GPU is billed while it exists, the volume is billed always).
- **Template** (our own, keeps the settings for new pods): env vars `HF_HOME=/workspace/hf` and
  `HF_TOKEN={{ RUNPOD_SECRET_hf_token }}`, HTTP port **8000** exposed.

## Start a session

1. RunPod → Pods → Deploy → choose the **network volume** at the top → GPU **A40** (or any GPU with ≥ 40 GB;
   24 GB is too small for the 11–12B models in bf16) → Change Template → our template → Deploy.
2. Web Terminal, check the GPU, the volume and the token:
   ```
   nvidia-smi && df -h /workspace && echo $HF_HOME
   source /workspace/venv/bin/activate && cd /workspace
   ```
3. Start **one** of the servers below (only one fits on the GPU at a time) and watch the log until
   `Application startup complete` (Ctrl+C leaves the log, the server keeps running):
   ```
   tail -f /workspace/vllm_<model>.log
   ```
4. Locally, set in `.env`: `VLLM_BASE_URL=https://<pod-id>-8000.proxy.runpod.net/v1` (the pod id changes
   with every new pod; the key stays the same). Check from the pod:
   ```
   curl -s localhost:8000/v1/models -H "Authorization: Bearer $(cat /workspace/vllm_api_key)"
   ```
5. After work: **Terminate** the pod.

Switching models: stop the running server, wait until `nvidia-smi` shows the memory freed, start another one.
```
pkill -f "vllm serve"
```

## Servers (one line each)

### Bielik v3.0 (native tool calling via `bielik-tools`)

```
nohup vllm serve speakleash/Bielik-11B-v3.0-Instruct --served-model-name bielik-11b-v3 --enable-auto-tool-choice --tool-parser-plugin /workspace/bielik-tools/tools/bielik_vllm_tool_parser.py --tool-call-parser bielik --chat-template /workspace/bielik-tools/tools/bielik_advanced_chat_template.jinja --max-model-len 32768 --gpu-memory-utilization 0.92 --host 0.0.0.0 --port 8000 --api-key "$(cat /workspace/vllm_api_key)" > /workspace/vllm_bielik.log 2>&1 &
```

Deliberately **without** `--default-chat-template-kwargs '{"enable_thinking": false}'`: that option breaks
tool calling for v3.0 (see models.md).

### PLLuM-12B (prompt-based tool calling, no tool options on the server)

```
nohup vllm serve CYFRAGOVPL/PLLuM-12B-instruct-2512 --served-model-name pllum-12b --max-model-len 32768 --gpu-memory-utilization 0.92 --api-key "$(cat /workspace/vllm_api_key)" > /workspace/vllm_pllum.log 2>&1 &
```

### Mistral-Nemo (base of PLLuM-12B; prompt-based, same as PLLuM)

```
nohup vllm serve mistralai/Mistral-Nemo-Instruct-2407 --served-model-name mistral-nemo --tokenizer-mode mistral --config-format mistral --load-format mistral --max-model-len 32768 --gpu-memory-utilization 0.92 --api-key "$(cat /workspace/vllm_api_key)" > /workspace/vllm_nemo.log 2>&1 &
```

Native tool calling variant (used only for the comparison in models.md): add
`--enable-auto-tool-choice --tool-call-parser mistral`.

## Running AgentDojo against the pod (locally, Git Bash)

```
set -a && . ./.env && set +a
export OPENAI_COMPATIBLE_BASE_URL="$VLLM_BASE_URL" OPENAI_COMPATIBLE_API_KEY="$VLLM_API_KEY" AGENTDOJO_MAX_TOKENS=1024
```

| model | `--model-id` | extra env vars |
|---|---|---|
| Bielik | `bielik-11b-v3` | — |
| PLLuM-12B | `pllum-12b` | `AGENTDOJO_PROMPTING=1` |
| Mistral-Nemo | `mistral-nemo` | `AGENTDOJO_PROMPTING=1` (native variant: `AGENTDOJO_SYSTEM_ROLE=1`) |

```
python scripts/run_agentdojo.py -s workspace -ut user_task_0 --model OPENAI_COMPATIBLE --model-id pllum-12b --logdir runs/pllum-12b-vllm -f
```

## Rebuilding the volume from scratch (only if it is lost)

```
pip install uv && uv venv /workspace/venv --python 3.12 && source /workspace/venv/bin/activate
uv pip install "https://github.com/vllm-project/vllm/releases/download/v0.24.0/vllm-0.24.0%2Bcu129-cp38-abi3-manylinux_2_28_x86_64.whl" --torch-backend=cu129
cd /workspace && git clone https://github.com/speakleash/bielik-tools.git && git -C bielik-tools checkout 77c4f4252bdea8da24ba68ff303cb9d8fac987b4
openssl rand -hex 16 > /workspace/vllm_api_key
hf download mistralai/Mistral-Nemo-Instruct-2407 --include consolidated.safetensors --include params.json --include tekken.json
hf download CYFRAGOVPL/PLLuM-12B-instruct-2512 --include "*.safetensors" --include "*.json"
```

- Do **not** install vLLM from PyPI: newer wheels are built for CUDA 13 (`libcudart.so.13` error, the host
  driver supports CUDA 12.8), and vLLM ≥ 0.31 moved modules the `bielik-tools` parser imports.
- Mistral-Nemo: only the Mistral-format files (the repo also has the same weights in HF format, ~2× the space).
- `hf download` takes one pattern per `--include`.
- Bielik's weights are downloaded by `vllm serve` on first start. Accept the model terms on the Hub first
  (Bielik, Mistral-Nemo, PLLuM are gated).
- The new key must also go into the local `.env` (`VLLM_API_KEY`).
