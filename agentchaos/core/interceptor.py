"""Wraps the HTTP layer so every outgoing call (LLM or tool) can be sabotaged.

Both the OpenAI/Anthropic SDKs and most custom tool clients ultimately funnel
through requests.Session.send, httpx.Client.send, or httpx.AsyncClient.send --
patching those three choke points covers sync and async agent loops alike
without touching agent code.

Classification: a request body shaped like {"messages": [...]} or containing
a "system" key is treated as an LLM call (Amnesia / Distractor targets). Any
other outgoing call is treated as a tool call (Gaslighter / Mutator targets),
restricted to STATE.targets if the caller configured one -- otherwise every
non-LLM call in the process is eligible, which can (correctly) include
things like auth or telemetry calls. This is still a heuristic, not real
provider/client identification; init(targets=...) narrows it, but a
best-effort payload-shape guess is what actually ships in this HTTP-level
implementation, and that's a real limitation, not a solved problem.

Blast radius: each intercepted call makes exactly ONE random draw against the
probabilities of the injectors applicable to it (STATE.blast_radius), so a
call can trigger at most one chaos event -- not one roll per injector like
V0, which let e.g. both Gaslighter and Mutator fire independently on the
same call and made the documented "probability of an event" inaccurate.
"""
import functools
import json
import sys
import atexit

from .state import STATE
from ..reporters.console import log_event, scorecard
from ..injectors import amnesia, distractor, gaslighter, mutator

_LLM_POOL = ("amnesia", "distractor")
_TOOL_POOL = ("gaslighter", "mutator")


def _decide(pool):
    """One random draw across `pool`, weighted by STATE.blast_radius.
    Returns the chosen injector name, or None if nothing fires."""
    if not STATE.active:
        return None
    weights = [(name, STATE.blast_radius.get(name, 0.0)) for name in pool]
    total = sum(w for _, w in weights)
    if total <= 0:
        return None
    r = STATE.rng.random()
    if r >= total:
        return None
    upto = 0.0
    for name, w in weights:
        upto += w
        if r < upto:
            return name
    return weights[-1][0]


def _targeted(url):
    if STATE.targets is None:
        return True
    url = str(url)
    return any(t in url for t in STATE.targets)


def _record(kind, detail):
    STATE.events.append({"type": kind, "detail": detail, "fatal": False})
    log_event(kind, detail)


def _parse_json(raw):
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _is_llm_payload(body):
    return isinstance(body, dict) and ("messages" in body or "system" in body)


def _apply_amnesia(body):
    body["messages"] = amnesia.corrupt(body.get("messages", []), STATE.rng, STATE.amnesia_strategy)
    return body


def _apply_distractor(body):
    body, mode = distractor.corrupt(body, STATE.rng)
    return body, mode


def _set_requests_body(request, body):
    """Mutating request.body without updating Content-Length corrupts HTTP
    framing -- the server reads exactly the old byte count and the
    connection desyncs on the next request. Caught by testing the example
    against a real local server; requests doesn't recompute this for you."""
    encoded = json.dumps(body).encode()
    request.body = encoded
    if "Content-Length" in request.headers:
        request.headers["Content-Length"] = str(len(encoded))
    return encoded


# --------------------------------------------------------------------------- #
# requests
# --------------------------------------------------------------------------- #
def patch_requests():
    import requests

    if getattr(requests.Session.send, "_agentchaos", False):
        return
    orig_send = requests.Session.send

    @functools.wraps(orig_send)
    def send(self, request, **kwargs):
        body = _parse_json(request.body)
        is_llm = _is_llm_payload(body)
        kind = _decide(_LLM_POOL) if is_llm else (_decide(_TOOL_POOL) if _targeted(request.url) else None)

        if kind == "amnesia":
            body = _apply_amnesia(body)
            _set_requests_body(request, body)
            _record("amnesia", f"dropped context -> {request.url}")
        elif kind == "distractor":
            body, mode = _apply_distractor(body)
            _set_requests_body(request, body)
            _record("distractor", f"[{mode}] injected override -> {request.url}")
        elif kind == "gaslighter":
            resp = gaslighter.fake_requests_response(request, STATE.rng, STATE.timeout_range)
            _record("gaslighter", f"{resp.status_code} <- {request.url}")
            return resp

        resp = orig_send(self, request, **kwargs)

        if kind == "mutator":
            try:
                mutated = mutator.corrupt(resp.json(), STATE.rng, STATE.mutation_rates)
            except Exception:
                pass
            else:
                resp._content = json.dumps(mutated).encode()
                _record("mutator", f"corrupted payload <- {request.url}")
        return resp

    send._agentchaos = True
    requests.Session.send = send


# --------------------------------------------------------------------------- #
# httpx (sync + async) -- also used internally by the openai / anthropic SDKs
# --------------------------------------------------------------------------- #
def patch_httpx():
    import httpx

    if not getattr(httpx.Client.send, "_agentchaos", False):
        orig_send = httpx.Client.send

        @functools.wraps(orig_send)
        def send(self, request, **kwargs):
            body = _parse_json(request.content)
            is_llm = _is_llm_payload(body)
            kind = _decide(_LLM_POOL) if is_llm else (_decide(_TOOL_POOL) if _targeted(request.url) else None)

            if kind == "amnesia":
                body = _apply_amnesia(body)
                request = httpx.Request(request.method, request.url,
                                         headers=request.headers, content=json.dumps(body).encode())
                _record("amnesia", f"dropped context -> {request.url}")
            elif kind == "distractor":
                body, mode = _apply_distractor(body)
                request = httpx.Request(request.method, request.url,
                                         headers=request.headers, content=json.dumps(body).encode())
                _record("distractor", f"[{mode}] injected override -> {request.url}")
            elif kind == "gaslighter":
                resp = gaslighter.fake_httpx_response(request, STATE.rng, STATE.timeout_range)
                _record("gaslighter", f"{resp.status_code} <- {request.url}")
                return resp

            resp = orig_send(self, request, **kwargs)

            if kind == "mutator":
                try:
                    mutated = mutator.corrupt(resp.json(), STATE.rng, STATE.mutation_rates)
                except Exception:
                    pass
                else:
                    resp._content = json.dumps(mutated).encode()
                    _record("mutator", f"corrupted payload <- {request.url}")
            return resp

        send._agentchaos = True
        httpx.Client.send = send

    # V0 only patched the sync client -- async agent loops (the common case
    # for modern frameworks) went through AsyncClient.send and bypassed
    # chaos entirely. Same logic, awaited.
    if not getattr(httpx.AsyncClient.send, "_agentchaos", False):
        orig_asend = httpx.AsyncClient.send

        @functools.wraps(orig_asend)
        async def asend(self, request, **kwargs):
            body = _parse_json(request.content)
            is_llm = _is_llm_payload(body)
            kind = _decide(_LLM_POOL) if is_llm else (_decide(_TOOL_POOL) if _targeted(request.url) else None)

            if kind == "amnesia":
                body = _apply_amnesia(body)
                request = httpx.Request(request.method, request.url,
                                         headers=request.headers, content=json.dumps(body).encode())
                _record("amnesia", f"dropped context -> {request.url}")
            elif kind == "distractor":
                body, mode = _apply_distractor(body)
                request = httpx.Request(request.method, request.url,
                                         headers=request.headers, content=json.dumps(body).encode())
                _record("distractor", f"[{mode}] injected override -> {request.url}")
            elif kind == "gaslighter":
                resp = await gaslighter.fake_httpx_response_async(request, STATE.rng, STATE.timeout_range)
                _record("gaslighter", f"{resp.status_code} <- {request.url}")
                return resp

            resp = await orig_asend(self, request, **kwargs)

            if kind == "mutator":
                try:
                    mutated = mutator.corrupt(resp.json(), STATE.rng, STATE.mutation_rates)
                except Exception:
                    pass
                else:
                    resp._content = json.dumps(mutated).encode()
                    _record("mutator", f"corrupted payload <- {request.url}")
            return resp

        asend._agentchaos = True
        httpx.AsyncClient.send = asend


# --------------------------------------------------------------------------- #
# fallback crash attribution + scorecard on exit, for callers who don't use
# agentchaos.run() / mark_success() / mark_failure()
# --------------------------------------------------------------------------- #
def install_hooks():
    if STATE._hooked:
        return
    STATE._hooked = True

    orig_hook = sys.excepthook

    def hook(exc_type, exc, tb):
        STATE.crashed = True
        if STATE.events:
            STATE.events[-1]["fatal"] = True
        orig_hook(exc_type, exc, tb)

    sys.excepthook = hook

    @atexit.register
    def _report():
        # If agentchaos.run() already printed the scorecard for this run,
        # don't print it twice.
        if STATE.events and not STATE._reported:
            scorecard(STATE.events, STATE.task_result, STATE.task_reason, STATE.crashed)
