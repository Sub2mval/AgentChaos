"""
Run with:  PYTHONPATH=<repo>:<rich-stub-dir-if-needed> python -m pytest tests/ -q
"""
import random
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agentchaos.injectors import amnesia, distractor, mutator
from agentchaos.core.interceptor import _decide
from agentchaos.core.state import STATE, DEFAULT_BLAST_RADIUS


def test_amnesia_preserves_system_and_latest_message():
    rng = random.Random(0)
    messages = [{"role": "system", "content": "rules"}] + \
        [{"role": "user", "content": f"m{i}"} for i in range(8)] + \
        [{"role": "user", "content": "LATEST"}]
    for seed in range(20):
        rng.seed(seed)
        out = amnesia.corrupt(messages, rng)
        assert out[0]["content"] == "rules"
        assert out[-1]["content"] == "LATEST"
        assert len(out) < len(messages)


def test_amnesia_no_op_below_three_messages():
    rng = random.Random(0)
    messages = [{"role": "user", "content": "hi"}]
    assert amnesia.corrupt(messages, rng) == messages


def test_amnesia_oldest_first_drops_from_the_front():
    messages = [{"role": "system", "content": "s"}] + \
        [{"role": "user", "content": str(i)} for i in range(10)]
    out = amnesia.corrupt(list(messages), random.Random(5), strategy="oldest_first")
    kept_contents = [m["content"] for m in out]
    # whatever got dropped, it should be a prefix of the historical (non-protected) messages
    dropped_count = len(messages) - len(out)
    assert dropped_count > 0
    assert kept_contents == ["s"] + [str(i) for i in range(dropped_count, 10)]


def test_distractor_reports_mode_and_mutates_body():
    rng = random.Random(0)
    body = {"messages": [{"role": "system", "content": "be terse"},
                          {"role": "user", "content": "hi"}]}
    for seed in range(10):
        rng.seed(seed)
        out, mode = distractor.corrupt(dict(body, messages=[dict(m) for m in body["messages"]]), rng)
        assert mode in ("system_append", "system_insert", "user_append")
        assert "URGENT OVERRIDE" in str(out["messages"])


def test_mutator_respects_zero_rates():
    rng = random.Random(0)
    data = {"active": True, "score": 5, "user_id": "abc123"}
    out = mutator.corrupt(data, rng, rates={"boolean_flip": 0, "numeric_shift": 0, "key_mangle": 0})
    assert out == data  # nothing should change with all rates at 0


def test_mutator_respects_full_rates():
    rng = random.Random(0)
    data = {"active": True, "score": 5}
    out = mutator.corrupt(data, rng, rates={"boolean_flip": 1, "numeric_shift": 1, "key_mangle": 0})
    assert out["active"] is False
    assert out["score"] == 50


def test_blast_radius_single_roll_never_fires_twice():
    STATE.blast_radius = dict(DEFAULT_BLAST_RADIUS)
    STATE.active = True
    STATE.rng = random.Random(42)
    fires = {"gaslighter": 0, "mutator": 0, "none": 0}
    for _ in range(2000):
        kind = _decide(("gaslighter", "mutator"))
        fires[kind or "none"] += 1
    total_events = fires["gaslighter"] + fires["mutator"]
    # combined chance should track the sum of the two probabilities (0.2),
    # not double-fire on the same call the way V0's two independent rolls could
    assert 300 < total_events < 500


def test_init_resets_events_between_runs():
    import agentchaos
    agentchaos.init(probability=1.0, frameworks=[], seed=1)
    STATE.events.append({"type": "amnesia", "detail": "x", "fatal": False})
    assert len(STATE.events) == 1
    agentchaos.init(probability=1.0, frameworks=[], seed=1)
    assert STATE.events == []  # V0 bug: second init() inherited first run's events


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all tests passed")
