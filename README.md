# AgentChaos

Drop-in chaos engineering for LLM agent loops. Patches the HTTP layer
(`requests`, `httpx.Client`, `httpx.AsyncClient` — which is what the OpenAI
and Anthropic SDKs use under the hood) to randomly sabotage a running agent,
then scores whether the agent's *task* actually survived, not just whether
the process did.

```bash
pip install agentchaos rich requests   # httpx optional, for openai/anthropic SDKs / async agents
```

```python
import agentchaos
agentchaos.init(probability=0.1, frameworks=["openai", "requests"])
```

Two lines, no changes to agent code. Injectors:

| Injector    | Targets              | Sabotage                                                       |
|-------------|-----------------------|------------------------------------------------------------------|
| Amnesia     | LLM calls             | drops 10-30% of history, preserving the system prompt and current turn |
| Distractor  | LLM calls             | splices a contradictory instruction into the system prompt *or* the latest user turn |
| Gaslighter  | tool/API calls        | simulated timeout, `429`, or `503`                                |
| Mutator     | tool/API responses    | per-field probability of flipping booleans, shifting numbers, mangling keys |

## Measuring what actually matters: task success, not process survival

```python
with agentchaos.run():
    result = my_agent(user_query)
    if result.balance == expected_balance:
        agentchaos.mark_success()
    else:
        agentchaos.mark_failure("wrong balance reported")
```

If you never call `mark_success`/`mark_failure`, AgentChaos falls back to
crash-detection (did an unhandled exception reach the top of the process)
and labels the score `(unverified)` — that's a much weaker signal than task
correctness, since an agent can process corrupted data, produce a wrong
answer, and exit cleanly. `examples/basic_agent.py --chaos` reproduces
exactly that case: the Mutator corrupts an account balance, the agent
reports the wrong number, nothing crashes, and the scorecard still shows a
failure because the harness checks the actual answer.

```
🔥 CHAOS EVENT: MUTATOR 🧬 corrupted payload <- http://127.0.0.1:8931/tools/fetch_balance
...
        AgentChaos Post-Mortem Scorecard
┌────────────────────────────────┬──────────────────────────────────────────┐
│ Total Chaos Events Injected     │ 3                                        │
│ Task Outcome                    │ ❌ failure (reported 12505.0 vs 1250.5)   │
│ Resilience Score                │ 0%                                       │
└────────────────────────────────┴──────────────────────────────────────────┘
```

## Configuration

```python
agentchaos.init(
    probability=0.1,                      # shorthand: same weight for all four injectors
    # or, for a real probability matrix:
    blast_radius={"amnesia": 0.1, "distractor": 0.05, "gaslighter": 0.15, "mutator": 0.1},
    frameworks=["openai", "requests"],    # "httpx" also covers httpx.AsyncClient
    injectors=["amnesia", "gaslighter"],  # optional allow-list, default = all four
    targets=["api.mytools.com"],          # optional: restrict Gaslighter/Mutator to matching URLs
    seed=7,                               # reproducible runs
    timeout_range=(0, 30),                # Gaslighter's simulated timeout sleep, in seconds
    amnesia_strategy="random",            # or "oldest_first" for deterministic degradation
    mutation_rates={"boolean_flip": 0.5, "numeric_shift": 0.5, "key_mangle": 0.2},
)
```

Each intercepted call makes **one** random draw against the combined weight
of the injectors applicable to it (LLM calls: Amnesia + Distractor; tool
calls: Gaslighter + Mutator) — a call triggers at most one chaos event.

## How classification works, and its limits

A request body shaped like `{"messages": [...]}` or containing a `system`
key is treated as an LLM call; anything else is a tool call, restricted to
`targets` if you set one. This is a payload-shape heuristic, not real
provider/client identification — it's what a pure HTTP-interception design
can do without parsing SDK internals, and it can misclassify an unrelated
API that happens to send a `messages` field. `targets` narrows the blast
radius for tool traffic; there's no equivalent narrowing for LLM traffic
yet.

## Known limitations (being upfront about scope)

- **Framework-agnostic in the sense of "any client on `requests`/`httpx`"**,
  not literally arbitrary tool mechanisms — Python-function tools,
  subprocess tools, database drivers, and browser automation aren't
  touched, since there's no HTTP call to intercept.
- **No integration tests against LangChain/CrewAI/AutoGPT** — the PRD names
  these as benchmark targets; this release has unit tests for the injectors
  and the blast-radius logic (`tests/`) but no framework-specific suite yet.
- **Crash attribution** (`sys.excepthook`) blames whichever chaos event fired
  most recently before an unhandled exception, which is a heuristic, not a
  causal trace — `agentchaos.run()` + `mark_success`/`mark_failure` avoids
  needing it at all when the caller can check task correctness directly.

See `examples/basic_agent.py` (a real two-step tool-calling loop against a
local mock LLM server, `examples/mock_llm_server.py`) for a runnable
before/after demo, and `tests/test_injectors.py` for the injector and
blast-radius unit tests.
