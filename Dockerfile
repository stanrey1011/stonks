FROM python:3.13-slim

WORKDIR /app

# Build deps for scipy/numpy C extensions (wheels cover most cases but keep gcc as fallback)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ curl \
    && rm -rf /var/lib/apt/lists/*

# Install supercronic (Docker-native cron — no syslog daemon needed)
ARG SUPERCRONIC_VERSION=0.2.33
RUN curl -fsSL \
    "https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
    -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic

# Install Python deps before copying code (layer cache).
# Strip the local editable self-install line (-e /home/as/...) — handled below.
COPY requirements.txt .
RUN grep -v '^\s*-e\s' requirements.txt > /tmp/req.txt && pip install --no-cache-dir -r /tmp/req.txt

# Install the package in editable mode so 'stonks' CLI is available.
# The actual source is volume-mounted at runtime; this just wires up the entry point.
COPY pyproject.toml .
COPY stonkslib/ stonkslib/
COPY tickers.yaml config.yaml ./
RUN pip install --no-cache-dir -e .

EXPOSE 8501

CMD ["streamlit", "run", "stonkslib/dash/app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true"]
