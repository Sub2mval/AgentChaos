from .core.state import STATE, DEFAULT_BLAST_RADIUS
from .core import interceptor
from .core.outcome import mark_success, mark_failure, run

__version__ = "0.2.0"
__all__ = ["init", "STATE", "mark_success", "mark_failure", "run"]


def init(probability=None, blast_radius=None, frameworks=("openai", "requests"),
          injectors=None, targets=None, seed=None, timeout_range=(0, 30),
          amnesia_strategy="random", mutation_rates=None):
    """Activate AgentChaos. Call once at the top of a script.

    probability    -- shorthand: sets every injector's blast_radius entry to
                       this value. Each intercepted call still makes exactly
                       one random draw against the applicable injectors'
                       combined weight, so this is "roughly this much chance
                       of an event per step", not compounded per-injector.
    blast_radius   -- explicit {"amnesia": p, "distractor": p, "gaslighter": p,
                       "mutator": p} matrix. Takes precedence over `probability`.
    frameworks     -- which HTTP layers to patch: "requests", "httpx"
                       (also covers httpx.AsyncClient). "openai"/"anthropic"
                       are accepted as aliases for "httpx" since both SDKs
                       ride on it.
    injectors      -- iterable restricting which injectors may fire.
    targets        -- optional iterable of URL substrings. When set, only
                       matching non-LLM calls are eligible for Gaslighter/
                       Mutator, so chaos doesn't land on unrelated traffic
                       (auth, telemetry, etc). Default: all non-LLM traffic.
    seed           -- optional int for reproducible chaos runs.
    timeout_range  -- (min, max) seconds the Gaslighter sleeps before a
                       simulated timeout.
    amnesia_strategy -- "random" (default) or "oldest_first".
    mutation_rates -- {"boolean_flip": p, "numeric_shift": p, "key_mangle": p}
                       per-field probabilities for the Mutator (defaults to
                       0.5/0.5/0.2 -- V0 mutated every field, unconditionally).
    """
    STATE.reset_run()

    if blast_radius is not None:
        STATE.blast_radius = dict(blast_radius)
    elif probability is not None:
        STATE.blast_radius = {k: probability for k in DEFAULT_BLAST_RADIUS}
    else:
        STATE.blast_radius = dict(DEFAULT_BLAST_RADIUS)
    if injectors is not None:
        allowed = set(injectors)
        STATE.blast_radius = {k: v for k, v in STATE.blast_radius.items() if k in allowed}

    STATE.frameworks = set(frameworks)
    STATE.targets = set(targets) if targets is not None else None
    STATE.timeout_range = timeout_range
    STATE.amnesia_strategy = amnesia_strategy
    if mutation_rates is not None:
        STATE.mutation_rates = dict(mutation_rates)
    if seed is not None:
        STATE.rng.seed(seed)
    STATE.active = True

    if "requests" in STATE.frameworks:
        interceptor.patch_requests()
    if STATE.frameworks & {"openai", "anthropic", "httpx"}:
        interceptor.patch_httpx()

    interceptor.install_hooks()
    return STATE
