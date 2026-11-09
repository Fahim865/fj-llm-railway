#!/bin/bash
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 curl ca-certificates
if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
mkdir -p /app
curl -fsSL https://raw.githubusercontent.com/Fahim865/fj-llm-railway/main/proxy.py -o /app/proxy.py
export OLLAMA_HOST=127.0.0.1:11434
ollama serve > /tmp/ollama.log 2>&1 &
for i in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then break; fi
  sleep 2
done
python3 /app/proxy.py > /tmp/proxy.log 2>&1 &
ollama pull qwen2.5:1.5b || ollama pull qwen2.5:1.5b
wait
