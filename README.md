# fj-llm-railway

Small LLM (Ollama `qwen2.5:0.5b`) behind a bearer-token auth proxy, for
hosting on Railway as the free-tier engine of the FJ tool index site.

## What is in this repo

- `Dockerfile` — builds the image from `ollama/ollama`: installs python3 +
  curl, copies `proxy.py` in, and **pulls the model at build time** so it is
  baked into the image (no runtime download, no volume needed).
- `proxy.py` — auth + rate-limit proxy (Python standard library only).
  Listens on `0.0.0.0:$PORT`, forwards `POST /v1/chat/completions` to
  Ollama on `127.0.0.1:11434`, requires `Authorization: Bearer <token>`.
  `GET /health` returns `{"ok": true}` without auth. One request at a time,
  10 req/min, `max_tokens` clamped to 300. No secrets in this repo — the
  token comes from the `LLM_PROXY_TOKEN` environment variable.
- `.github/workflows/docker.yml` — GitHub Actions builds the image on every
  push to `main` and pushes `ghcr.io/fahim865/fj-llm-railway:latest`
  (public). Railway deploys from that image.

## Why 0.5b, not 1.5b

Railway caps this service at **1 GB RAM**. The 1.5b model is 986 MB of
weights; with Ollama + the proxy it needs ~1,050 MB, so the kernel
OOM-kills the inference process. The 0.5b model (397 MB) fits comfortably.
If the memory limit is ever raised to 2 GB, change `qwen2.5:0.5b` back to
`qwen2.5:1.5b` in the Dockerfile, in `proxy.py`'s default, and in the
`OLLAMA_MODEL` / `NEXA_AI_LOCAL_MODEL` env vars, then redeploy.

## How Railway runs it

Railway service `fj-llm-ghcr` in project `zooming-creation`, image
`ghcr.io/fahim865/fj-llm-railway:latest`, limits 1 vCPU / 1 GB RAM,
healthcheck `GET /health`. No volume (the model is in the image; a volume
mounted at `/root/.ollama` would shadow it). `OLLAMA_KEEP_ALIVE=60s`
unloads the model when idle to keep the cost inside the Hobby credit.

## Environment variables (set on the Railway service, never in this repo)

| Variable | Value |
|---|---|
| `LLM_PROXY_TOKEN` | Bearer token (same value as the site's `NEXA_AI_LOCAL_API_KEY`) |
| `OLLAMA_KEEP_ALIVE` | `60s` |
| `OLLAMA_MODEL` | `qwen2.5:0.5b` |

## Public endpoint

`POST https://fj-llm-ghcr-production.up.railway.app/v1/chat/completions`
with `Authorization: Bearer <token>`, body
`{"model": "qwen2.5:0.5b", "messages": [...]}`.
`GET /health` needs no auth.
