# ── builder ──────────────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Strip the local editable self-install line (-e ...) — handled in runtime stage.
RUN grep -v '^\s*-e\s' requirements.txt > /tmp/req.txt \
    && pip install --no-cache-dir --prefix=/install -r /tmp/req.txt

# ── runtime ───────────────────────────────────────────────────────────────────
FROM python:3.13-slim
WORKDIR /app

# curl for the Streamlit healthcheck; no compilers needed at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

ARG SUPERCRONIC_VERSION=0.2.33
RUN curl -fsSL \
    "https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
    -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic

# Copy pre-built wheels from builder.
COPY --from=builder /install /usr/local

# Copy application source.
COPY pyproject.toml tickers.yaml config.yaml ./
COPY stonkslib/ stonkslib/
COPY docker/ docker/

# Install the package entry point (stonks CLI). No compilers needed — wheels already installed.
RUN pip install --no-cache-dir -e . \
    && mkdir -p /app/data /app/log \
    && useradd -u 1000 -m stonks \
    && chown -R stonks:stonks /app

USER stonks

EXPOSE 8501

CMD ["streamlit", "run", "stonkslib/dash/app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true"]
