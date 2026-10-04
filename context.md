# Research project context

> Context file for Claude Code. Describes the project goal, research questions,
> experiment architecture and literature. Update as the project progresses.

## Topic (working title)

**Are AI agents easier to hijack in Polish? A cross-lingual evaluation of
indirect prompt injection and tool poisoning in MCP-based agents.**

We study the vulnerability of tool-using LLM agents to two types of attacks in
which the malicious instruction comes not from the user but from an external
source:

- **Indirect prompt injection (IPI)** — an instruction hidden in data read by the
  agent (email content, a document, a tool result).
- **Tool poisoning** — an MCP-specific variant; the instruction is hidden in the
  tool description (docstring) and enters the model's context as soon as the
  server is registered.

The language dimension (the same attack and task in Polish and English, and in
mixed configurations) is the comparative axis, but **it is not novel in itself**
— a cross-lingual prompt injection comparison has already been done for Turkish
(see Literature → Multilinguality). **The core novelty** is a combination nobody
has done: tool-using / MCP agents + tool poisoning + deterministic success
measurement via the executed action + the Polish context (in particular PLLuM).
The paper must explicitly distinguish itself from the Turkish works, which
operate at the chat level rather than on tool-using agents.

Goal: a research paper intended for publication (international conference or
journal).

## Research questions

- **RQ1 (language).** Does attack success rate (ASR) differ between Polish and
  English **with model, task and attack vector held constant** (language as an
  isolated variable)?
- **RQ2 (language boundary).** In mixed configurations, which matters more: the
  payload language or the task language? (Hypothesis: payload language dominates.)
- **RQ3 (robustness transfer across attack classes).** Does PLLuM's low
  vulnerability to jailbreaks carry over to robustness against IPI/tool
  poisoning? **We measure both types in our own harness, on the same tasks**, so
  the comparison is fair — we do not compare our IPI ASR with someone else's
  jailbreak ASR.
- **RQ4 (detectors, optional).** Do **prompt injection detectors** (e.g.
  PromptGuard, ProtectAI DeBERTa and multilingual variants) work on Polish IPI
  payloads — recall and false-positive rate on benign Polish text? This extends
  the AgentShield result (Kurdish/Arabic) to Polish.
  NOTE: this is **not the same** as content moderators (Bielik Guard, PL-Guard),
  which detect hate speech/crime rather than injections. Moderators can at most
  be tested as an illustration of "this is not the right tool".

## Hypotheses (to be falsified)

- **H1** — ASR differs significantly between PL and EN. The direction is
  **uncertain and probably model-dependent**: for Turkish, English was found to
  be sometimes more dangerous (contrary to the jailbreak intuition). We do not
  fix H1 as directional.
- **H2** — in a mixed configuration, effectiveness is determined by the payload
  (instruction) language, not the task language.
- **H3** — PLLuM is significantly more vulnerable to IPI than to jailbreaks,
  **measured on the same basis** (shared harness, same tasks). Without a shared
  basis the hypothesis is uninterpretable.
- **H4 (secondary)** — prompt injection detectors have low recall or high FP on
  Polish IPI payloads. (Content moderators are a separate, weaker question — see
  RQ4.)

## Experiment architecture (hybrid approach)

Two tracks, chosen according to the attack vector:

- **IPI via data → AgentDojo (track B).** A mature, stateful environment, the de
  facto standard. We take the existing suites (workspace: mail/calendar/files,
  banking, travel) and translate the payloads into Polish. Our contribution = the
  language layer.
- **Tool poisoning → our own MCP servers (track A).** A few small servers built
  with the official MCP Python SDK (FastMCP), because only there is the tool
  description a real attack vector.

Shared principles:

- Servers/tools are **functional** but operate on **isolated, resettable state**
  (e.g. SQLite), not on real services.
- **Deterministic success verification** — we check the database state after the
  run (was the attacker's action executed), with no LLM judge.
- `reset_world()` before each run → reproducibility.
- Payloads are translated **manually** and verified; PL/EN semantic equivalence
  is documented. (Otherwise we confound the language effect with translation
  quality.)
- We measure **static attacks**; adaptive attacks are explicitly out of scope.
- Ethics: only our own synthetic servers — no testing against third-party
  services.

### Attack vectors (to be separated in the analysis)

1. Tool poisoning (malicious tool docstring).
2. IPI via data (malicious content returned by a tool).
3. Puppet / multi-tool (the description of one tool redirects calls to another).

### Language configurations

| Task | Payload | Note |
|---|---|---|
| PL | PL | Polish agent, Polish attacker |
| PL | EN | most realistic (MCP descriptions are usually in EN) |
| EN | PL | for symmetry |
| EN | EN | baseline from the literature |

### Models

- **Polish:** Bielik 11B Instruct (tool calling via `bielik-tools`),
  Llama-PLLuM Instruct. ← the main differentiator.
- **Open multilingual:** Qwen2.5-Instruct, Llama-3.1-8B-Instruct.
- **Commercial:** 1–2 via API (watch the costs — estimate on a small sample).

### Metrics

- **ASR** (deterministically from the world state).
- **Utility under attack** (whether the real task is still completed).
- **Refusal rate** (MCPTox: agents rarely refuse — an interesting comparison).
- Number of steps, cost (for APIs).
- Significance analysis: McNemar's test for PL vs EN pairs (paired data),
  confidence intervals rather than point ASR alone.

## Tech stack

- Python; the official **MCP Python SDK (FastMCP)** for our own servers.
- **AgentDojo** (latest version) for the IPI part.
- SQLite as the world state + reset script.
- A single agent loop (ReAct) shared by all models.
- Open models locally / on Colab; commercial and some open models via API.
- No own GPU — everything must run on APIs + Colab.

## Minimal scope (safe for one semester)

Two vectors (tool poisoning + IPI via data), four models (Bielik, PLLuM, one
multilingual, one commercial), all four language configurations.
RQ4 and the third vector (puppet) as extensions if time permits.

## Literature

### Indirect prompt injection and agent benchmarks
- **Greshake et al.**, *Not what you've signed up for: Compromising Real-World
  LLM-Integrated Applications with Indirect Prompt Injection* (arXiv:2302.12173)
  — the founding work on IPI.
- **InjecAgent** — IPI benchmark for tool-using agents.
- **AgentDojo** — dynamic, stateful environment for attacks and defenses; our
  basis for the IPI part.
- **BIPIA** — benchmark and defenses for IPI.

### MCP / tool poisoning
- **MCPTox** — tool poisoning benchmark on real MCP servers (key finding: more
  capable models can be more vulnerable, refusals are rare).
- **MCPSecBench**, **MCP Pitfall Lab (2026)** — further MCP security benchmarks.
- **Beurer-Kellner & Fischer (Invariant Labs)** — first description of tool
  poisoning in MCP.

### Defenses
- **Beurer-Kellner et al.**, *Design Patterns for Securing LLM Agents against
  Prompt Injections* (arXiv:2506.08837).
- **Hines et al.**, *spotlighting* (arXiv:2403.14720).
- **CaMeL, Progent, FIDES, RTBAS, FORGE** — "outside the model" defenses
  (reference monitor).
- **MELON** — defense via re-execution with a masked user prompt.
- **Nasr et al.** — breaking 12 published defenses with an adaptive attack.

### Multilinguality / closest work
- **AgentShield** (Rassul & Rashid, arXiv:2605.11026) — IPI in Kurdish and
  Arabic on top of AgentDojo; shows the collapse of English-centric detectors
  (ProtectAI DeBERTa: 97.5% FP in Kurdish, 75% in Arabic). The closest
  methodological template. Note: InjecAgent attacks turned out to be mostly
  rejected by today's models → AgentDojo is the safer choice.

#### Turkish cross-lingual works (COMPETITORS — cite and distinguish ourselves)
They show that a cross-lingual prompt injection comparison has already been done
for Turkish. Our advantage: agents + MCP + tool poisoning + action-based
measurement, rather than the chat level.
- **Aytas et al.** (Applied Sciences 2026, doi:10.3390/app16136740) — 790
  Turkish adversarial prompts, translated to EN, 55 models; cross-lingual safety
  comparison.
- **ELECO 2025**, *A Study on Cross-Lingual Security Vulnerabilities in LLMs*
  (eleco.org.tr) — EN vs TR prompt injection, direct and **indirect** attacks,
  defenses (quotation, sanitization); EN generally more effective than TR.
- **ICEANS 2026**, *Comparative Security Evaluation ... Turkish-Language
  Adversarial Prompts* — Llama/Mistral/Qwen on Turkish prompts.

### Polish works (none addresses IPI in agents — this is our gap)
- **PL-Guard** (Krasnodębska et al., BSNLP 2025) — content moderation in Polish.
- **Bielik Guard** (Wróbel et al., arXiv:2602.07954) — Polish content safety
  classifiers; multilingual guard models are poorly calibrated on PL.
- **Rainbow-teaming for the Polish language** (Krasnodębska et al., TrustNLP 2025)
  — chat jailbreaks; PLLuM with ASR <1.5%, Bielik 45–64%.
- **Chrabąszcz et al.**, *Evaluating LLMs Robustness in Less Resourced Languages
  with Proxy Models* (arXiv:2506.07645) — robustness to text perturbations.
- **Podpora et al.**, *LLM Firewall Using Validator Agent* (Applied Sciences 2026)
  — RAG defense architecture without empirical evaluation.

> Note: verify arXiv numbers and bibliographic data before citing in the paper
> (some were collected from searches and not all are confirmed 1:1).

## Before starting
A fresh literature search for two things: (1) multilingual IPI / prompt
injection in Polish; (2) **an MCP / tool poisoning variant for any language** —
the latter is now our core novelty, so we must check whether anyone has combined
tool poisoning with a language axis. A pure language comparison (without
agents/MCP) is already taken for Turkish.