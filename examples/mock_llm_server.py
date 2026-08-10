"""A tiny local stand-in for an OpenAI-style chat completions endpoint plus
one tool endpoint, so the agent example is a genuine (if toy) LLM agent loop
that runs offline -- no API key, no real network call.

Endpoint contract, deliberately shaped like the real chat completions API so
AgentChaos's is_llm_payload() heuristic classifies it correctly:

    POST /v1/chat/completions   body: {"messages": [...]}
        -> if the latest user message hasn't triggered the tool step yet,
           returns a tool_call asking for fetch_balance
        -> otherwise returns a final text answer quoting the balance it was
           given in the tool result message

    GET  /tools/fetch_balance
        -> {"user_id": 42, "balance": 1250.5, "verified": true}
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

REAL_BALANCE = 1250.50


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # keep the demo output focused on AgentChaos's own logging

    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/tools/fetch_balance":
            self._send_json({"user_id": 42, "balance": REAL_BALANCE, "verified": True})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        messages = body.get("messages", [])
        has_tool_result = any(m.get("role") == "tool" for m in messages)

        if not has_tool_result:
            self._send_json({
                "choices": [{"message": {
                    "role": "assistant",
                    "tool_calls": [{"id": "call_1", "function": {"name": "fetch_balance", "arguments": "{}"}}],
                }}]
            })
            return

        tool_msg = next(m for m in messages if m.get("role") == "tool")
        try:
            balance = json.loads(tool_msg["content"])["balance"]
        except Exception:
            balance = "unknown"
        self._send_json({
            "choices": [{"message": {
                "role": "assistant",
                "content": f"Your account balance is ${balance}.",
            }}]
        })


def start(port=8931):
    server = HTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
