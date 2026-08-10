"""A genuine (if minimal) LLM tool-calling agent, run against a local mock
chat-completions server -- no API key needed. V0's example was just a bare
`requests.get()` with no LLM step at all; this one actually does:

    LLM asks for a tool call -> tool executes -> LLM reads the tool result
    and answers -> the harness verifies the *answer is actually correct*,
    not just that the process didn't crash.

Run clean, then under chaos, and compare:

    python examples/basic_agent.py
    python examples/basic_agent.py --chaos

Under --chaos with the Mutator active, watch for a run where the process
exits cleanly (no exception) but the scorecard still shows a task failure --
that's the gap V0's crash-only scoring missed entirely.
"""
import re
import sys

import requests

from mock_llm_server import start, REAL_BALANCE

BASE = "http://127.0.0.1:8931"


def call_llm(messages):
    resp = requests.post(f"{BASE}/v1/chat/completions", json={"messages": messages}, timeout=5)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]


def call_tool(name):
    """Defensive tool call: retries once, and validates the response shape
    before trusting it -- this is what actually gives an agent a shot at
    surviving Gaslighter/Mutator, not just avoiding a crash."""
    for attempt in range(2):
        try:
            resp = requests.get(f"{BASE}/tools/{name}", timeout=5)
            resp.raise_for_status()
            data = resp.json()
        except (requests.exceptions.Timeout, requests.exceptions.HTTPError,
                requests.exceptions.ConnectionError) as e:
            print(f"  tool call failed ({e}); retrying..." if attempt == 0 else f"  tool call failed twice: {e}")
            continue
        if "balance" not in data or not isinstance(data.get("balance"), (int, float)):
            print(f"  tool response missing/invalid 'balance' field: {data}")
            return None
        return data
    return None


def run_agent():
    messages = [{"role": "user", "content": "What is my account balance?"}]
    step1 = call_llm(messages)

    if not step1.get("tool_calls"):
        return None, "LLM did not request the expected tool call"

    tool_data = call_tool("fetch_balance")
    if tool_data is None:
        return None, "tool call did not return usable data"

    messages.append({"role": "assistant", "tool_calls": step1["tool_calls"]})
    messages.append({"role": "tool", "content": __import__("json").dumps(tool_data)})
    step2 = call_llm(messages)
    answer = step2.get("content", "")

    match = re.search(r"\$?(\d+(?:\.\d+)?)", answer)
    reported = float(match.group(1)) if match else None
    return reported, answer


def main():
    start()
    chaos = "--chaos" in sys.argv

    if chaos:
        import agentchaos
        agentchaos.init(
            probability=0.5,
            frameworks=["requests"],
            targets=["/tools/", "/v1/chat/completions"],  # scope chaos to this demo's own traffic
            seed=7,
            timeout_range=(0, 0.3),  # short sleeps so the demo runs fast
        )
        with agentchaos.run():
            reported, detail = run_agent()
            if reported is not None and abs(reported - REAL_BALANCE) < 0.01:
                agentchaos.mark_success()
                print(f"Agent reported ${reported} -- correct.")
            else:
                agentchaos.mark_failure(f"reported {reported!r}, actual {REAL_BALANCE} ({detail})")
                print(f"Agent reported {reported!r} instead of ${REAL_BALANCE} -- WRONG.")
    else:
        reported, detail = run_agent()
        print(f"Agent reported ${reported}" if reported == REAL_BALANCE else f"Unexpected: {reported!r} ({detail})")


if __name__ == "__main__":
    main()
