#!/usr/bin/env bash
set -euo pipefail

# Detect the Ollama endpoint that is actually reachable from THIS container,
# in preference order, and export it before uvicorn starts.
#  1. the OLLAMA_URL we were launched with (a known-good value, e.g. from .env)
#  2. common Docker host aliases (host.docker.internal, docker-gateway, localhost)
#  3. the container's default gateway from /proc/net/route (the host bridge)
# We probe each candidate with HTTP GET /api/tags and use the first that answers.
# This works even when Docker's internal resolver/host-gateway mapping is flaky
# (e.g. in WSL2, where host.docker.internal can point at a dead interface).
PICK=$(python3 - <<'PY'
import os
import urllib.request

candidates = []

edge = (os.getenv("OLLAMA_URL") or "").strip().rstrip("/")
if edge:
    candidates.append(edge)

for name in ("host.docker.internal", "docker-gateway", "localhost"):
    candidates.append(f"http://{name}:11434")

# /proc/net/route first default route entry: destination 0.0.0.0, little-endian hex.
try:
    with open("/proc/net/route", encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) >= 3 and parts[0] == "eth0" and parts[1] == "00000000":
                raw = parts[2]
                gw = ".".join(
                    str(int(raw[index:index + 2], 16))
                    for index in (6, 4, 2, 0)
                )
                candidates.append(f"http://{gw}:11434")
                break
except Exception:
    pass

seen = set()
for url in candidates:
    if url in seen:
        continue
    seen.add(url)
    try:
        with urllib.request.urlopen(url + "/api/tags", timeout=3) as response:
            if response.status == 200:
                print(url)
                break
    except Exception:
        continue
PY
)

if [ -n "$PICK" ]; then

    export OLLAMA_URL="$PICK"
    echo "OLLAMA_URL=$OLLAMA_URL"

else

    echo "No reachable Ollama endpoint detected; keeping OLLAMA_URL=$OLLAMA_URL"

fi

# Start uvicorn in this process so OLLAMA_URL above is inherited.
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8080}"
