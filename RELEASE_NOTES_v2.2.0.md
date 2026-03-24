# CPA-X v2.2.0 Release Notes / 更新说明

> This release adds first-class usage analytics charts and a publishable container image flow for registry-based server updates.

## 中文（v2.2.0）

### 一句话说明

这一版新增了按小时 / 天 / 月的 usage 图表、按账号的 usage 分布视图，并把 Docker 发布路径标准化到 GHCR，方便服务器直接拉取新镜像更新。

### 主要变化

- 新增 usage analytics API 与前端趋势图
- 支持按小时 / 天 / 月查看 requests / tokens / cost
- 支持按账号查看 usage 分布，并优先使用 runtime auth metadata 做账号映射
- 新增 GHCR Docker 发布工作流
- 提供面向 registry 的发布脚本与 deploy bundle 更新方式
- `cpax-dokploy` 改为优先拉取版本化镜像，而不是在服务器本地构建

## English (v2.2.0)

### Short version

This release adds first-class usage analytics charts, account-level usage breakdown, and a GHCR-based Docker publishing flow so servers can update by pulling a tagged image.

### Highlights

- new usage analytics API and dashboard charts
- hourly / daily / monthly views for requests / tokens / cost
- account-level usage breakdown backed by runtime auth metadata when available
- new GHCR Docker publish workflow
- new registry-oriented publish script and deployment flow
- `cpax-dokploy` now prefers pulling a versioned image instead of building on the server
