def _mangle_key(key, rng, rate):
    if isinstance(key, str) and len(key) > 3 and rng.random() < rate:
        i = rng.randrange(1, len(key) - 1)
        return key[:i] + key[i + 1:]
    return key


def corrupt(obj, rng, rates=None):
    """Recursively corrupt a response payload.

    V0 flipped *every* boolean and multiplied *every* number by 10 -- a
    payload with several fields came back nearly unrecognizable ("nuclear
    mutation"), which makes it hard to isolate what an agent actually
    failed to validate. Each mutation kind now has its own independent
    probability (default 0.5/0.5/0.2), so a typical corruption touches a
    handful of fields rather than the whole object.
    """
    rates = rates or {"boolean_flip": 0.5, "numeric_shift": 0.5, "key_mangle": 0.2}

    def walk(o):
        if isinstance(o, dict):
            return {_mangle_key(k, rng, rates["key_mangle"]): walk(v) for k, v in o.items()}
        if isinstance(o, list):
            return [walk(v) for v in o]
        if isinstance(o, bool):
            return (not o) if rng.random() < rates["boolean_flip"] else o
        if isinstance(o, (int, float)):
            return (o * 10) if rng.random() < rates["numeric_shift"] else o
        return o

    return walk(obj)
