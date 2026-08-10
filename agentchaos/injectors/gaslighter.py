import asyncio
import json
import time

_KINDS = ("timeout", "rate_limit", "server_error")


def _payload(kind):
    return json.dumps({"error": {"type": kind, "message": f"AgentChaos simulated {kind}"}}).encode()


def fake_requests_response(request, rng, timeout_range):
    import requests
    kind = rng.choice(_KINDS)
    if kind == "timeout":
        time.sleep(rng.uniform(*timeout_range))
        raise requests.exceptions.Timeout(f"AgentChaos: simulated 504 timeout for {request.url}")

    resp = requests.Response()
    resp.status_code = 429 if kind == "rate_limit" else 503
    resp.url = str(request.url)
    resp.headers["Content-Type"] = "application/json"
    resp._content = _payload(kind)
    return resp


def fake_httpx_response(request, rng, timeout_range):
    """Sync path (httpx.Client)."""
    import httpx
    kind = rng.choice(_KINDS)
    if kind == "timeout":
        time.sleep(rng.uniform(*timeout_range))
        raise httpx.TimeoutException(f"AgentChaos: simulated 504 timeout for {request.url}", request=request)
    return _httpx_error_response(httpx, request, kind)


async def fake_httpx_response_async(request, rng, timeout_range):
    """Async path (httpx.AsyncClient) -- uses asyncio.sleep so the event
    loop isn't blocked. V0 only patched the sync client, so any agent using
    AsyncClient (the common case for modern async agent loops) bypassed
    chaos entirely."""
    import httpx
    kind = rng.choice(_KINDS)
    if kind == "timeout":
        await asyncio.sleep(rng.uniform(*timeout_range))
        raise httpx.TimeoutException(f"AgentChaos: simulated 504 timeout for {request.url}", request=request)
    return _httpx_error_response(httpx, request, kind)


def _httpx_error_response(httpx, request, kind):
    status = 429 if kind == "rate_limit" else 503
    return httpx.Response(status, request=request, content=_payload(kind),
                           headers={"Content-Type": "application/json"})
