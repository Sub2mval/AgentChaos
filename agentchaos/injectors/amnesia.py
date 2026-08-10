def corrupt(messages, rng, strategy="random"):
    """Drop 10-30% of *historical* context.

    V0 sampled uniformly across the whole list, which could delete the
    system prompt or the current user turn -- that's not "context rot",
    that's lobotomizing the agent's instructions. This protects the
    system/developer message and the most recent turn, and only corrupts
    what's actually history in between.

    strategy: "random" (default) samples the drop set uniformly;
              "oldest_first" always drops the earliest eligible messages,
              for a more deterministic degradation experiment.
    """
    n = len(messages)
    if n < 3:
        return messages

    protected = set()
    if messages[0].get("role") in ("system", "developer"):
        protected.add(0)
    protected.add(n - 1)  # keep the current/most recent turn intact

    candidates = [i for i in range(n) if i not in protected]
    if not candidates:
        return messages

    frac = rng.uniform(0.10, 0.30)
    n_drop = min(len(candidates), max(1, int(n * frac)))

    if strategy == "oldest_first":
        drop = set(candidates[:n_drop])
    else:
        drop = set(rng.sample(candidates, n_drop))

    return [m for i, m in enumerate(messages) if i not in drop]
