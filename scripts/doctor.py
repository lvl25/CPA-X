#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CPA-X doctor（AI 友好）

用途：
- 自动探测当前设备已有的 CLIProxyAPI / cliproxyapi 安装形态（systemd/unit/config/binary/auth/log）
- 生成/更新 .env，让面板“开箱即用”（除密钥外）

说明：
- doctor 不会也无法自动获取明文密钥（通常配置中存的是 hash）
- 你仍需手动注入：
  - CLIPROXY_PANEL_MANAGEMENT_KEY
  - CLIPROXY_PANEL_MODELS_API_KEY
  - CLIPROXY_PANEL_PANEL_USERNAME
  - CLIPROXY_PANEL_PANEL_PASSWORD
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple


ENV_PREFIX = "CLIPROXY_PANEL_"


def run_capture(args, timeout: int = 8) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except Exception as e:
        return 1, "", str(e)


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def has_systemd() -> bool:
    if not is_linux():
        return False
    code, out, _ = run_capture(["bash", "-lc", "command -v systemctl >/dev/null 2>&1; echo $?"])
    return code == 0 and out.endswith("0")


def systemctl_value(unit: str, prop: str) -> str:
    code, out, _ = run_capture(["systemctl", "show", unit, "-p", prop, "--value"], timeout=10)
    return out if code == 0 else ""


def parse_execstart(execstart_value: str) -> Optional[str]:
    if not execstart_value:
        return None
    match = re.search(r"argv\[\]=(.*?)(?:\s*;\s*|\s*$)", execstart_value)
    if match:
        return match.group(1).strip()
    return execstart_value.strip()


def extract_config_from_cmdline(cmdline: str) -> Tuple[Optional[str], Optional[str]]:
    if not cmdline:
        return None, None
    try:
        parts = shlex.split(cmdline)
    except Exception:
        parts = cmdline.split()
    if not parts:
        return None, None

    binary = parts[0]
    config_path = None
    for i, token in enumerate(parts):
        if token in {"-config", "--config"} and i + 1 < len(parts):
            config_path = parts[i + 1]
            break
        if token.startswith("-config="):
            config_path = token.split("=", 1)[1]
            break
    return binary, config_path


def list_running_services() -> list[str]:
    if not has_systemd():
        return []
    code, out, _ = run_capture(["systemctl", "list-units", "--type=service", "--state=running", "--no-legend"])
    if code != 0 or not out:
        return []
    units = []
    for line in out.splitlines():
        unit = line.split(None, 1)[0].strip()
        if unit.endswith(".service"):
            units.append(unit)
    return units


def pick_cliproxy_unit(units: list[str]) -> Optional[str]:
    for unit in units:
        if unit.startswith("cliproxyapi@") and unit.endswith(".service"):
            return unit
    for unit in units:
        if unit in {"cli-proxy-api.service", "cliproxyapi.service"}:
            return unit
    for unit in units:
        if unit.startswith("cliproxyapi") and unit.endswith(".service"):
            return unit
    for unit in units:
        execstart = systemctl_value(unit, "ExecStart")
        cmdline = parse_execstart(execstart) or ""
        if "cli-proxy-api" in cmdline or "cliproxyapi" in cmdline:
            return unit
    return None


def try_load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore
    except Exception:
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8", errors="ignore")) or {}
    except Exception:
        return {}


def detect_from_config(config_path: Optional[str]) -> Dict[str, str]:
    if not config_path:
        return {}
    config = try_load_yaml(Path(config_path))
    if not isinstance(config, dict):
        config = {}

    detected: Dict[str, str] = {}
    port = config.get("port")
    if isinstance(port, int) and port > 0:
        detected["cliproxy_api_port"] = str(port)

    auth_dir = config.get("auth-dir") or config.get("auth_dir")
    if isinstance(auth_dir, str) and auth_dir.strip():
        detected["auth_dir"] = auth_dir.strip()
    return detected


def detect_log_path(auth_dir: Optional[str], working_dir: Optional[str]) -> Optional[str]:
    candidates = []
    if auth_dir:
        candidates.append(os.path.join(auth_dir, "logs", "main.log"))
    if working_dir:
        candidates.append(os.path.join(working_dir, "logs", "main.log"))
        candidates.append(os.path.join(working_dir, "auths", "logs", "main.log"))

    for candidate in candidates:
        try:
            if os.path.exists(candidate):
                return candidate
        except Exception:
            continue

    if auth_dir:
        return os.path.join(auth_dir, "logs", "main.log")
    if working_dir:
        return os.path.join(working_dir, "logs", "main.log")
    return None


def env_key(key: str) -> str:
    return f"{ENV_PREFIX}{key.upper()}"


def _is_effectively_empty(value: str) -> bool:
    normalized = (value or "").strip()
    return normalized in {"", '""', "''"}


def upsert_env_file(path: Path, updates: Dict[str, str], overwrite_existing: bool) -> None:
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()

    wanted = {env_key(k): v for k, v in updates.items() if v is not None}
    if not wanted:
        return

    new_lines: list[str] = []
    seen: set[str] = set()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue
        key, existing_value = line.split("=", 1)
        key = key.strip()
        if key in wanted:
            if overwrite_existing or _is_effectively_empty(existing_value):
                new_lines.append(f"{key}={wanted[key]}")
            else:
                new_lines.append(line)
            seen.add(key)
        else:
            new_lines.append(line)

    for key, value in wanted.items():
        if key not in seen:
            new_lines.append(f"{key}={value}")

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-env", action="store_true", help="写入/更新 .env（默认只输出建议）")
    parser.add_argument("--env-path", default=".env", help="env 文件路径（默认 .env）")
    parser.add_argument("--overwrite-existing", action="store_true", help="覆盖已存在的非空配置（默认只补缺失/空值）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（便于 AI 解析）")
    args = parser.parse_args()

    result: Dict[str, str] = {
        "bind_host": "127.0.0.1",
        "panel_port": "8080",
        "cliproxy_api_base": "http://127.0.0.1",
    }

    unit = None
    binary = None
    config_path = None
    working_dir = None

    if has_systemd():
        units = list_running_services()
        unit = pick_cliproxy_unit(units)
        if unit:
            execstart = systemctl_value(unit, "ExecStart")
            cmdline = parse_execstart(execstart) or ""
            binary, config_path = extract_config_from_cmdline(cmdline)
            working_dir = systemctl_value(unit, "WorkingDirectory") or None

            if unit.endswith(".service"):
                result["cliproxy_service"] = unit[:-8]
            else:
                result["cliproxy_service"] = unit

    if binary:
        result["cliproxy_binary"] = binary
    if config_path:
        result["cliproxy_config"] = config_path
        result.update(detect_from_config(config_path))

    auth_dir = result.get("auth_dir")
    log_path = detect_log_path(auth_dir, working_dir)
    if log_path:
        result["cliproxy_log"] = log_path

    if working_dir:
        result["cliproxy_dir"] = working_dir

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for key in sorted(result.keys()):
            print(f"{env_key(key)}={result[key]}")

    if args.write_env:
        env_path = Path(args.env_path)
        upsert_env_file(env_path, result, overwrite_existing=args.overwrite_existing)
        if not args.json:
            print(f"\n[doctor] 已写入: {env_path.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
