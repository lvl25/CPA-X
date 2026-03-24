# CPA-X Admin Panel (v2.2.0)

English | [中文](README_CN.md)

**AI-first repo**: this project is primarily designed to be deployed and operated by AI agents.

- AI deployment guide: `AI_DEPLOY_CN.md`
- Agent instructions: `AGENTS.md`
- Release notes: `RELEASE_NOTES_v2.2.0.md`

A monitoring and management panel for **CLIProxyAPI**, featuring health checks, resource monitoring, logs, update management, request statistics, and pricing display.

> Current security posture: frontend export entries are removed, main-config writeback is disabled by default, and this local hardened build also requires explicit admin credentials before the panel will start.

## Preview

### Dark Theme
![CPA-X Dark Preview](docs/images/preview-dark.png)

### Light Theme
![CPA-X Light Preview](docs/images/preview-light.png)

## Requirements
- Recommended: Linux
- Python 3.11+
- Access to CLIProxyAPI management interface (default `http://127.0.0.1:8317`)

> Windows is also supported, but service control and auto-update features are limited there.

## Quick Installation

### Option 1: One-Click Install
```bash
bash scripts/install.sh

# Optional but recommended: rerun auto-detect
python3 scripts/doctor.py --write-env
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install.ps1
```

### Option 2: Manual Installation

```bash
git clone https://github.com/ferretgeek/CPA-X.git
cd CPA-X
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

The installer and runtime both refuse to start if placeholder credentials or keys remain in `.env`.

Important settings:
- `CLIPROXY_PANEL_PANEL_USERNAME` / `CLIPROXY_PANEL_PANEL_PASSWORD`
- `CLIPROXY_PANEL_BIND_HOST`
- `CLIPROXY_PANEL_PANEL_ACCESS_KEY`
- `CLIPROXY_PANEL_CONFIG_WRITE_ENABLED`
- `CLIPROXY_PANEL_CLIPROXY_API_BASE` / `CLIPROXY_PANEL_CLIPROXY_API_PORT`
- `CLIPROXY_PANEL_MANAGEMENT_KEY` / `CLIPROXY_PANEL_MODELS_API_KEY`
- `CLIPROXY_PANEL_CLIPROXY_SERVICE` / `CLIPROXY_PANEL_CLIPROXY_BINARY`
- `CLIPROXY_PANEL_PRICING_*`
- `CLIPROXY_PANEL_PRICING_AUTO_*`
- `CLIPROXY_PANEL_GITHUB_TOKEN`

Start the panel:

```bash
python app.py
```

Open:

```text
http://127.0.0.1:8080
```

Health endpoint:

```text
http://127.0.0.1:8080/healthz
```

## Docker / Container Deployment

Good for: monitoring, stats, models, logs, config read/validate.

Not good for: full systemd-based service control and auto-update.

This repo includes:
- `Dockerfile`
- `docker-compose.yml`
- `.env.docker.example`
- published image: `registry.maxsale.vn/tools/cpa-x:v2.2.0`

Shortest path:

```bash
docker compose up -d --build
```

Registry publish:

```bash
REGISTRY_USERNAME=... REGISTRY_PASSWORD=... PUSH_LATEST=true ./scripts/publish-docker.sh
```

Server update with the published image:

```bash
docker pull registry.maxsale.vn/tools/cpa-x:v2.2.0
docker stop cpax-panel || true
docker rm cpax-panel || true
docker run -d --name cpax-panel --restart unless-stopped -p 8080:8080 registry.maxsale.vn/tools/cpa-x:v2.2.0
```

For container mode, mount host files/directories for config, logs, and auths if you need those features. Config writeback stays disabled by default.

## FAQ

### Page loads but data is empty
Check that CLIProxyAPI is running and `.env` points to the correct management base/port.

### Health check timeout
`/api/status` does more work than `/api/resources`; use `/api/resources` first if you want a lighter check.

### systemd features are unavailable
That is expected on non-systemd targets and most containers.

## Security Notes
- Do not commit `.env`.
- Keep management keys, model keys, panel access keys, and admin passwords only in `.env`.
- Default bind host is `0.0.0.0` for LAN-friendly deployment. Set `CLIPROXY_PANEL_BIND_HOST=127.0.0.1` if you only want local access.
- `CLIPROXY_PANEL_PANEL_ACCESS_KEY` is an optional extra API gate for automation and upstream compatibility.
- Main-config writeback stays off unless you explicitly set `CLIPROXY_PANEL_CONFIG_WRITE_ENABLED=true`.

## License
MIT License (see `LICENSE`)
