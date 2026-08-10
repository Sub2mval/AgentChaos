import random

DEFAULT_BLAST_RADIUS = {"amnesia": 0.10, "distractor": 0.10, "gaslighter": 0.10, "mutator": 0.10}
DEFAULT_MUTATION_RATES = {"boolean_flip": 0.5, "numeric_shift": 0.5, "key_mangle": 0.2}


class State:
    """Single mutable object shared by every patched call site."""

    __slots__ = ("blast_radius", "frameworks", "targets", "rng", "events",
                 "active", "timeout_range", "crashed", "_hooked", "_reported",
                 "task_result", "task_reason", "amnesia_strategy", "mutation_rates")

    def __init__(self):
        self.blast_radius = dict(DEFAULT_BLAST_RADIUS)
        self.frameworks = set()
        self.targets = None          # None = all non-LLM traffic eligible; else URL substrings
        self.rng = random.Random()
        self.events = []             # [{"type","detail","fatal"}]
        self.active = False
        self.timeout_range = (0, 30)
        self.crashed = False
        self._hooked = False
        self._reported = False
        self.task_result = None      # None | "success" | "failure" -- set via mark_success/mark_failure
        self.task_reason = None
        self.amnesia_strategy = "random"
        self.mutation_rates = dict(DEFAULT_MUTATION_RATES)

    def reset_run(self):
        """Clear per-run state. Called by init() and by run().__enter__ so a
        second experiment doesn't inherit the first one's history (V0 bug)."""
        self.events = []
        self.crashed = False
        self._reported = False
        self.task_result = None
        self.task_reason = None


STATE = State()
