# CPA-X（AI 部署手册）

这份文档写给会跑命令的 AI Agent：目标是把面板部署到目标设备上，并与设备上已存在的 **CLIProxyAPI / cliproxyapi** 正常对接。

## 最小闭环

部署完成后至少要满足：

1. `GET /` 能打开页面
2. `GET /api/status` 正常返回
3. `GET /api/models` 正常返回 models
4. 请求统计和费用估算口径正确
5. systemd 场景下自动更新可完成 `stop -> 下载 -> 替换 -> start`
6. 面板管理员口令和上游密钥都不是 placeholder

## 推荐步骤

```bash
bash scripts/install.sh
python3 scripts/doctor.py --write-env
systemctl restart cliproxy-panel
```

然后手动补齐：

- `CLIPROXY_PANEL_PANEL_USERNAME`
- `CLIPROXY_PANEL_PANEL_PASSWORD`
- `CLIPROXY_PANEL_MANAGEMENT_KEY`
- `CLIPROXY_PANEL_MODELS_API_KEY`

## Docker / 容器部署

适合：监控、查看、状态、模型、日志、配置读取/校验。

不适合：完整的 systemd 服务控制与自动更新。

关键点：

- 容器内要监听 `0.0.0.0`
- 面板必须能访问宿主机上的 CLIProxyAPI 管理接口
- 如果要日志/配置/auth 相关功能，宿主机路径必须挂载进容器
- 容器模式建议：
  - `CLIPROXY_PANEL_AUTO_UPDATE_ENABLED=false`
  - `CLIPROXY_PANEL_CONFIG_WRITE_ENABLED=false`

## doctor 的职责

`scripts/doctor.py` 会尝试自动探测：

- systemd unit
- `ExecStart`
- config 路径
- auth 目录
- log 路径
- working dir

但它不会自动获得：

- 管理密钥
- 模型密钥
- 管理员账号口令

## GitHub 限流

如需更稳定地检查 release，建议设置：

- `CLIPROXY_PANEL_GITHUB_TOKEN=<PAT>`

## Token 价格自动同步

面板内部价格口径固定为 **美元/百万Tokens**。

- 默认开启自动同步：手动价格为 0 时，会尝试从 OpenRouter 补齐
- 如需严格使用手动价格：设置 `CLIPROXY_PANEL_PRICING_AUTO_ENABLED=false`
