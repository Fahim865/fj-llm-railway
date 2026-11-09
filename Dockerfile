# Small LLM (Ollama qwen2.5:1.5b) + auth proxy, for Railway.
# Base image already contains Ollama; we add python3 (for the proxy) and
# copy the proxy in. The model is pulled at container start (first boot
# downloads ~986 MB into /root/.ollama, which should be a Railway volume so
# later deploys reuse it) and the proxy starts immediately so the
# /health endpoint answers while the model downloads.
FROM ollama/ollama:latest

RUN apt-get update -qq \
 && apt-get install -y -qq python3 curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY proxy.py /app/proxy.py

ENV OLLAMA_HOST=127.0.0.1:11434

# Clear the ollama image ENTRYPOINT (["/bin/ollama"]) so CMD runs in a shell.
ENTRYPOINT []

CMD ["sh", "-c", "ollama serve > /tmp/ollama.log 2>&1 & for i in $(seq 1 40); do curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break; sleep 2; done; python3 /app/proxy.py > /tmp/proxy.log 2>&1 & ollama pull qwen2.5:1.5b || ollama pull qwen2.5:1.5b; wait"]
