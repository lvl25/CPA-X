FROM python:3.11-slim

ARG PANEL_VERSION=2.2.0

LABEL org.opencontainers.image.title="CPA-X" \
      org.opencontainers.image.description="CPA-X admin panel for CLIProxyAPI" \
      org.opencontainers.image.source="https://github.com/lvl25/CPA-X" \
      org.opencontainers.image.version="${PANEL_VERSION}" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends ca-certificates \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

ENV CLIPROXY_PANEL_BIND_HOST=0.0.0.0
ENV CLIPROXY_PANEL_PANEL_PORT=8080
ENV CLIPROXY_PANEL_PANEL_THREADS=8

EXPOSE 8080

CMD ["python", "app.py"]
