# 给 AI 的部署与对接指引（必读）

本仓库的默认使用者是 **AI Agent**。你的目标是：在一台已经安装并运行了 **CLIProxyAPI / cliproxyapi** 的设备上，把本面板部署起来，并保证：

- 面板可访问（静态页面 + `/api/*` 正常）
- 统计数据正确
- 自动更新在 systemd 场景下可用
- 配置查看/校验、日志、模型等功能都能用

## 最快可用（推荐路径）

1. `bash scripts/install.sh`
2. `python3 scripts/doctor.py --write-env`
3. 填入真实的：
   - `CLIPROXY_PANEL_PANEL_USERNAME`
   - `CLIPROXY_PANEL_PANEL_PASSWORD`
   - `CLIPROXY_PANEL_MANAGEMENT_KEY`
   - `CLIPROXY_PANEL_MODELS_API_KEY`
4. `systemctl restart cliproxy-panel`

> 这个本地 hardened 版本要求显式管理员口令。`doctor.py` 只会补路径/服务名，不会写入任何明文密钥或账号口令。

## Docker / 容器部署

如果你用 Docker/容器部署，请先明确限制：

- 要全功能（自动更新/服务控制）：不要用容器
- 只要监控与查看：可以用容器，但必须显式提供：
  - `CLIPROXY_PANEL_BIND_HOST=0.0.0.0`
  - 上游管理接口地址
  - 如需日志/配置/auth 能力，把宿主机路径挂载进容器

推荐直接用仓库内：

- `Dockerfile`
- `docker-compose.yml`
- `.env.docker.example`

## 关键环境变量

- 面板自身
  - `CLIPROXY_PANEL_PANEL_USERNAME`
  - `CLIPROXY_PANEL_PANEL_PASSWORD`
  - `CLIPROXY_PANEL_BIND_HOST`
  - `CLIPROXY_PANEL_PANEL_PORT`
  - `CLIPROXY_PANEL_PANEL_ACCESS_KEY`：可选；为 `/api/*` 增加 `X-Panel-Key` / `panel_key` 兼容层
  - `CLIPROXY_PANEL_CONFIG_WRITE_ENABLED`：默认 `false`

- 费用估算
  - `CLIPROXY_PANEL_PRICING_INPUT`
  - `CLIPROXY_PANEL_PRICING_OUTPUT`
  - `CLIPROXY_PANEL_PRICING_CACHE`
  - `CLIPROXY_PANEL_PRICING_AUTO_ENABLED`
  - `CLIPROXY_PANEL_PRICING_AUTO_SOURCE`
  - `CLIPROXY_PANEL_PRICING_AUTO_MODEL`

- CLIProxyAPI 对接
  - `CLIPROXY_PANEL_CLIPROXY_SERVICE`
  - `CLIPROXY_PANEL_CLIPROXY_BINARY`
  - `CLIPROXY_PANEL_CLIPROXY_CONFIG`
  - `CLIPROXY_PANEL_AUTH_DIR`
  - `CLIPROXY_PANEL_CLIPROXY_LOG`
  - `CLIPROXY_PANEL_CLIPROXY_API_BASE`
  - `CLIPROXY_PANEL_CLIPROXY_API_PORT`
  - `CLIPROXY_PANEL_MANAGEMENT_KEY`
  - `CLIPROXY_PANEL_MODELS_API_KEY`

## 自检

- 管理接口：
  - `curl -sS -o /dev/null -w '%{http_code}\n' -H 'X-Management-Key: <KEY>' http://127.0.0.1:8317/v0/management/usage`
- 模型列表：
  - `curl -sS -o /dev/null -w '%{http_code}\n' -H 'Authorization: Bearer <KEY>' http://127.0.0.1:8317/v1/models`
- 面板状态：
  - `curl -sS http://127.0.0.1:<PANEL_PORT>/api/status | head -c 200`

## AI 设计约束

- 文档优先“可执行”和“可验证”
- 默认值优先“安全收口”：前端不恢复导出入口，主配置写回默认关闭
- 自动探测只补缺省值，不覆盖用户明确配置
- 不要删除或弱化本地已有的 basic auth / CSRF hardening
