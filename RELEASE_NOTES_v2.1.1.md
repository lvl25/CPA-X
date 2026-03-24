# CPA-X v2.1.1 Release Notes / 更新说明

> This local branch keeps the upstream v2.1.1 feature set while preserving stricter local hardening.

## 中文（v2.1.1）

### 一句话说明

这一版把本地 checkout 补齐到了 upstream `ferretgeek/CPA-X` 的 v2.1.1 能力面，同时保留了本地更严格的安全收口。

### 主要变化

- 自动更新卡片现在会直接显示：
  - 是否有新版本
  - 当前是否空闲
  - 还需等待多久才会空闲
  - 下次自动检查还要多久
  - 为什么当前还没有触发自动更新
- 前端已移除导出入口
- 主配置写回默认关闭
- 新增 `scripts/doctor.py`
- 增加 OpenRouter 自动价格同步
- 增加 upstream 兼容的 `X-Panel-Key` / `panel_key` API 访问方式
- 保留本地 hardened basic auth、CSRF 和更严格的启动校验

## English (v2.1.1)

### Short version

This local branch now matches the upstream `ferretgeek/CPA-X` v2.1.1 feature surface while keeping stricter local hardening.

### Highlights

- richer auto-update status UX
- frontend export entries removed
- main-config writeback disabled by default
- `scripts/doctor.py` added
- OpenRouter pricing auto-sync added
- upstream-compatible `X-Panel-Key` / `panel_key` API access added
- local basic auth, CSRF checks, and stricter startup validation preserved
