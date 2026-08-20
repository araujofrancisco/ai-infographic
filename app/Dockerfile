FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        shared-mime-info \
        fonts-dejavu \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/output /app/projects /app/tasks

COPY update-env-ip.sh /usr/local/bin/update-env-ip.sh
RUN chmod +x /usr/local/bin/update-env-ip.sh

EXPOSE 8080

# update-env-ip.sh detects the reachable Ollama endpoint, exports OLLAMA_URL,
# then starts uvicorn in-process. No shell quoting here: the script owns handoff.
CMD ["/usr/local/bin/update-env-ip.sh"]
