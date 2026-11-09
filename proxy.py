#!/usr/bin/env python3
"""Auth + rate-limit proxy in front of Ollama, for Railway.

Listens on 0.0.0.0:$PORT (Railway sets PORT; default 8080) so Railway's
router can reach it. Only POST /v1/chat/completions is forwarded to Ollama
(127.0.0.1:11434, same container). Every forwarded request must carry
`Authorization: Bearer <token>` where the token is read from the
LLM_PROXY_TOKEN environment variable at startup. No request body, header
value or token is ever logged.

Protections (one small CPU model, RAM-tight):
  - One Ollama call at a time (global lock) — the model cannot handle
    concurrent requests.
  - Rate limit: 10 requests per rolling 60 seconds (429 + Retry-After).
  - max_tokens clamped to 300, stream forced off, body <= 16 KB,
    total message text <= 6000 chars.
  - Only the chat-completions path is allowed; everything else 404.
  - GET /health returns {"ok": true} without auth (Railway healthcheck).

No third-party deps (Python standard library only).
"""
import hashlib
import hmac
import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LISTEN_HOST = os.environ.get("PROXY_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("PORT", "8080"))
OLLAMA_URL = "http://127.0.0.1:11434/v1/chat/completions"
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b")
MAX_BODY_BYTES = 16 * 1024
MAX_TEXT_CHARS = 6000
MAX_TOKENS = 300
RATE_LIMIT = 10          # requests
RATE_WINDOW = 60.0       # per rolling seconds
UPSTREAM_TIMEOUT = 180   # seconds (model load ~10s + generation)

def _load_token():
    token = os.environ.get("LLM_PROXY_TOKEN", "").strip()
    if len(token) < 32:
        raise RuntimeError("LLM_PROXY_TOKEN env var missing or too short")
    return token

TOKEN = _load_token()
TOKEN_HASH = hashlib.sha256(TOKEN.encode("utf-8")).hexdigest()
del TOKEN  # keep only the hash in memory for comparison via hmac on the hash

# NOTE: we compare the sha256 of the presented token against the stored
# hash, so the raw token is never held in process memory after startup.
def _authorized(auth_header):
    if not auth_header or not auth_header.startswith("Bearer "):
        return False
    presented = auth_header[len("Bearer "):].strip()
    if not presented:
        return False
    digest = hashlib.sha256(presented.encode("utf-8")).hexdigest()
    return hmac.compare_digest(digest, TOKEN_HASH)

CALL_LOCK = threading.Lock()
REQUEST_TIMES = deque()
TIMES_LOCK = threading.Lock()

def _rate_limited():
    now = time.time()
    with TIMES_LOCK:
        while REQUEST_TIMES and REQUEST_TIMES[0] <= now - RATE_WINDOW:
            REQUEST_TIMES.popleft()
        if len(REQUEST_TIMES) >= RATE_LIMIT:
            return True
        REQUEST_TIMES.append(now)
        return False

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # Minimal access log: method, path, status only. No headers/bodies.
        sys.stderr.write("%s %s\n" % (self.command, self.path))

    def _send_json(self, status, payload, retry_after=None):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if retry_after is not None:
            self.send_header("Retry-After", str(retry_after))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"ok": True})
        else:
            self._send_json(404, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self._send_json(404, {"error": "not_found"})
            return
        if not _authorized(self.headers.get("Authorization")):
            self._send_json(401, {"error": "unauthorized"})
            return
        if _rate_limited():
            self._send_json(429, {"error": "rate_limited"}, retry_after=30)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send_json(400, {"error": "bad_request"})
            return
        if length <= 0 or length > MAX_BODY_BYTES:
            self._send_json(413, {"error": "body_too_large"})
            return
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send_json(400, {"error": "bad_json"})
            return
        if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
            self._send_json(400, {"error": "bad_request"})
            return
        total_chars = 0
        for msg in body["messages"]:
            if not isinstance(msg, dict) or not isinstance(msg.get("content"), str):
                self._send_json(400, {"error": "bad_request"})
                return
            total_chars += len(msg["content"])
        if total_chars > MAX_TEXT_CHARS:
            self._send_json(413, {"error": "prompt_too_large"})
            return
        # Clamp cost: short outputs only, no streaming (RAM-tight model).
        body["stream"] = False
        if isinstance(body.get("max_tokens"), int):
            body["max_tokens"] = max(1, min(body["max_tokens"], MAX_TOKENS))
        else:
            body["max_tokens"] = 120
        body["model"] = MODEL
        upstream_body = json.dumps(body).encode("utf-8")

        with CALL_LOCK:
            req = urllib.request.Request(
                OLLAMA_URL, data=upstream_body, method="POST",
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT) as resp:
                    data = resp.read()
                    status = resp.status
            except urllib.error.HTTPError as exc:
                data = exc.read()
                status = exc.code
            except Exception:
                self._send_json(502, {"error": "upstream_unavailable"})
                return
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # Reject anything else.
    def do_PUT(self):
        self._send_json(404, {"error": "not_found"})

    def do_DELETE(self):
        self._send_json(404, {"error": "not_found"})

    def do_PATCH(self):
        self._send_json(404, {"error": "not_found"})

if __name__ == "__main__":
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    sys.stderr.write("llm-proxy listening on %s:%d\n" % (LISTEN_HOST, LISTEN_PORT))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
