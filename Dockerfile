# Small LLM (Ollama qwen2.5:1.5b) + auth proxy, for Railway.
# Base image already contains Ollama; we add python3 (for the proxy) and
# copy the proxy in. The model is pulled at BUILD time so it is baked into
# the image -- no runtime download and NO volume needed (a volume mounted
# at /root/.ollama would shadow the baked-in model). At runtime the
# container just starts Ollama and the proxy.
FROM ollama/ollama:latest

RUN apt-get update -qq \
 && apt-get install -y -qq python3 curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY proxy.py /app/proxy.py

ENV OLLAMA_HOST=127.0.0.1:11434

# Pull the model now (build time). Start Ollama in the background, wait
# for it, pull the model, then stop Ollama. The model lands in
# /root/.ollama/models inside the image.
RUN ollama serve > /tmp/ollama-build.log 2>&1 & \
    for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do \
      curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break; \
      sleep 2; \
    done; \
    ollama pull qwen2.5:1.5b; \
    pkill ollama || true; \
    sleep 2; \
    ls -la /root/.ollama/models/blobs | head -5

# Clear the ollama image ENTRYPOINT (["/bin/ollama"]) so CMD runs in a shell.
ENTRYPOINT []

CMD ["sh", "-c", "ollama serve > /tmp/ollama.log 2>&1 & for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break; sleep 3; done; python3 /app/proxy.py > /tmp/proxy.log 2>&1 & wait"]
