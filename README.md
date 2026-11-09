# fj-llm-railway

Small LLM (Ollama `qwen2.5:1.5b`) behind a bearer-token auth proxy, for
hosting on Railway as the free-tier engine of the FJ tool index site.

## What is in this repo

- `proxy.py` — auth + rate-limit proxy (Python standard library only).
  Listens on `0.0.0.0:$PORT`, forwards `POST /v1/chat/completions` to
  Ollama on `127.0.0.1:11434`, requires `Authorization: Bearer <token>`.
  `GET /health` returns `{"ok": true}` without auth. One request at a time,
  10 req/min, `max_tokens` clamped to 300. No secrets in this repo — the
  token comes from the `LLM_PROXY_TOKEN` environment variable.

## How Railway runs it

The Railway service uses the `ubuntu:24.04` image with a custom start
command that installs Python + Ollama, pulls the model, and runs this proxy.
The model is kept on a Railway volume mounted at `/root/.ollama` so it
survives redeploys. `OLLAMA_KEEP_ALIVE=60s` unloads the model when idle so
memory (and cost) stay low — the workspace is on the Railway Hobby plan
($5/month included usage), and this service is sized to stay inside it at
low-to-moderate traffic.

## Environment variables (set on the Railway service, never in this repo)

| Variable | Value |
|---|---|
| `LLM_PROXY_TOKEN` | Bearer token (same value as the site's `NEXA_AI_LOCAL_API_KEY`) |
| `OLLAMA_KEEP_ALIVE` | `60s` |
| `OLLAMA_MODEL` | `qwen2.5:1.5b` |

## Public endpoint

`POST https://<railway-domain>/v1/chat/completions` with
`Authorization: Bearer <token>`, body `{"model": "qwen2.5:1.5b",
"messages": [...]}`. `GET /health` needs no auth.
