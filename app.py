#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CPA-XX 管理面板后端 v3 (Performance Optimized)
功能: 为 CLIProxyAPI 提供监控统计、健康检查、资源监控、配置管理、API测试、模型管理
优化: 缓存机制、预编译正则、非阻塞监控、减少shell调用
"""

import os
import json
import time
import subprocess
import threading
import re
import platform
import shutil
import hmac
from datetime import datetime, timedelta, timezone
from collections import deque
from urllib.parse import urlparse
from flask import Flask, jsonify, request, send_from_directory, Response
import requests

PANEL_NAME = "CPA-X"
PANEL_VERSION = "2.2.0"
PRICING_BASIS_TOKENS = 1_000_000
PRICING_BASIS_LABEL = '百万Tokens'
PRICING_BASIS_TEXT = f'美元/{PRICING_BASIS_LABEL}'

# ==================== 预编译正则表达式 ====================
# 日志格式: [2026-01-17 05:21:09] [--------] [info ] [gin_logger.go:92] 200 |            0s |       127.0.0.1 | GET     "/v1/models"
REQUEST_LOG_PATTERN = re.compile(
    r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\].*\[gin_logger\.go:\d+\]\s+(\d+)\s+\|\s+(\S+)\s+\|([\d\s.]+)\|\s+(\w+)\s+"([^"]+)"'
)
HASH_VERSION_PATTERN = re.compile(r'^[0-9a-f]{7,40}$', re.IGNORECASE)
EXCLUDED_LOG_PATHS = (
    '"/v0/management/usage"',
    '"/v0/management/',
    '"/v1/models"',
)

# 可选依赖
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("Warning: psutil not installed. Resource monitoring will be limited.")

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    print("Warning: pyyaml not installed. Config validation will be limited.")

from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__, static_folder='static', static_url_path='')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# 配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

CONFIG = {
    'cliproxy_dir': '/opt/CLIProxyAPI',
    'cliproxy_config': '/opt/CLIProxyAPI/config.yaml',
    'cliproxy_binary': '/opt/CLIProxyAPI/cliproxy',
    'cliproxy_log': '/opt/CLIProxyAPI/logs/main.log',  # CLIProxy 主日志
    'cliproxy_stderr': '/var/log/cliproxy/stderr.log',
    'auth_dir': '/opt/CLIProxyAPI/data',
    'cliproxy_service': 'cliproxy',
    'panel_port': 8080,
    'idle_threshold_seconds': 1800,  # 30分钟
    'auto_update_check_interval': 300,
    'auto_update_enabled': True,
    'cliproxy_api_port': 8317,  # CLIProxy API端口
    'cliproxy_api_base': 'http://127.0.0.1',
    'models_api_key': '',
    'management_key': '',
    'config_write_enabled': False,
    'usage_snapshot_path': os.path.join(DATA_DIR, 'usage_snapshot.json'),
    'log_stats_path': os.path.join(DATA_DIR, 'log_stats.json'),
    'persistent_stats_path': os.path.join(DATA_DIR, 'persistent_stats.json'),
    'pricing_input': 0.0,
    'pricing_output': 0.0,
    'pricing_cache': 0.0,
    'pricing_auto_enabled': True,
    'pricing_auto_source': 'openrouter',
    'pricing_auto_model': '',
    'quotes_path': os.path.join(DATA_DIR, 'quotes.txt'),
    'disk_path': '/',
    'panel_host': '0.0.0.0',
    'panel_threads': 8,
    'panel_username': '',
    'panel_password': '',
    'panel_access_key': '',
}

ENV_PREFIX = 'CLIPROXY_PANEL_'
LEGACY_ENV_MAP = {
    'PANEL_USERNAME': 'panel_username',
    'PANEL_PASSWORD': 'panel_password',
}
ENV_ALIAS_MAP = {
    f'{ENV_PREFIX}BIND_HOST': 'panel_host',
}
UNSAFE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
PUBLIC_PATHS = {'/healthz'}
PANEL_REQUEST_HEADER = 'X-Panel-Request'
PANEL_REQUEST_HEADER_VALUE = '1'

CONFIG_TYPES = {
    'panel_port': int,
    'panel_threads': int,
    'idle_threshold_seconds': int,
    'auto_update_check_interval': int,
    'auto_update_enabled': bool,
    'config_write_enabled': bool,
    'cliproxy_api_port': int,
    'pricing_input': float,
    'pricing_output': float,
    'pricing_cache': float,
    'pricing_auto_enabled': bool,
}

USAGE_ANALYTICS_BUCKETS = ('hour', 'day', 'month')
USAGE_ANALYTICS_LIMITS = {
    'hour': 24,
    'day': 30,
    'month': 12,
}


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    value_str = str(value).strip().lower()
    if value_str in {'1', 'true', 'yes', 'on'}:
        return True
    if value_str in {'0', 'false', 'no', 'off'}:
        return False
    return False


def _parse_float(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except Exception:
        return default


def _load_dotenv():
    env_path = os.path.join(BASE_DIR, '.env')
    if not os.path.exists(env_path):
        return {}
    values = {}
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' not in line:
                    continue
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                values[key] = value
    except Exception as e:
        print(f"Warning: failed to load .env: {e}")
    return values


def _format_env_value(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


def _update_dotenv_values(updates):
    env_path = os.path.join(BASE_DIR, '.env')
    env_updates = {f'{ENV_PREFIX}{key.upper()}': _format_env_value(val) for key, val in updates.items()}
    lines = []

    if os.path.exists(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                lines = f.read().splitlines()
        except Exception as e:
            print(f"Warning: failed to read .env: {e}")

    updated = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in line:
            new_lines.append(line)
            continue
        key, _ = line.split('=', 1)
        key = key.strip()
        if key in env_updates:
            new_lines.append(f"{key}={env_updates[key]}")
            updated.add(key)
        else:
            new_lines.append(line)

    for key, value in env_updates.items():
        if key not in updated:
            new_lines.append(f"{key}={value}")

    try:
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines) + '\n')
        return True
    except Exception as e:
        print(f"Warning: failed to save .env: {e}")
        return False


def _apply_overrides(overrides):
    for key, value in overrides.items():
        if key not in CONFIG:
            continue
        caster = CONFIG_TYPES.get(key)
        if caster is None:
            CONFIG[key] = value
            continue
        if caster is bool:
            CONFIG[key] = _parse_bool(value)
        else:
            try:
                CONFIG[key] = caster(value)
            except Exception:
                pass


def load_config_overrides():
    env_overrides = {}
    for key in CONFIG.keys():
        env_key = f'{ENV_PREFIX}{key.upper()}'
        if env_key in os.environ:
            env_overrides[key] = os.environ[env_key]

    dotenv_raw = _load_dotenv()
    dotenv_overrides = {}
    for key in CONFIG.keys():
        env_key = f'{ENV_PREFIX}{key.upper()}'
        if env_key in dotenv_raw:
            dotenv_overrides[key] = dotenv_raw[env_key]

    _apply_overrides(dotenv_overrides)
    _apply_overrides(env_overrides)

    for legacy_key, config_key in LEGACY_ENV_MAP.items():
        legacy_value = os.environ.get(legacy_key)
        if legacy_value and not CONFIG.get(config_key):
            CONFIG[config_key] = legacy_value

    for env_key, config_key in ENV_ALIAS_MAP.items():
        alias_value = os.environ.get(env_key)
        if alias_value:
            CONFIG[config_key] = alias_value


def _require_nonempty_config(key):
    value = str(CONFIG.get(key, '')).strip()
    if not value:
        raise RuntimeError(f'Missing required configuration: {ENV_PREFIX}{key.upper()}')
    return value


def _looks_like_placeholder(value):
    normalized = str(value or '').strip().lower()
    return normalized.startswith('replace-me') or normalized.startswith('replace_with_')


def validate_runtime_config():
    username = _require_nonempty_config('panel_username')
    password = _require_nonempty_config('panel_password')

    if _looks_like_placeholder(username) or _looks_like_placeholder(password):
        raise RuntimeError('Refusing to start with placeholder panel credentials')
    if len(password) < 12:
        raise RuntimeError('CLIPROXY_PANEL_PANEL_PASSWORD must be at least 12 characters')

    for secret_key in ('management_key', 'models_api_key'):
        secret_value = str(CONFIG.get(secret_key, '')).strip()
        if secret_value and _looks_like_placeholder(secret_value):
            raise RuntimeError(f'Refusing to start with placeholder value for {secret_key}')

    for numeric_key in ('panel_port', 'cliproxy_api_port'):
        value = int(CONFIG.get(numeric_key, 0))
        if value < 1 or value > 65535:
            raise RuntimeError(f'Invalid port for {numeric_key}: {value}')

    panel_threads = int(CONFIG.get('panel_threads', 0))
    if panel_threads < 1:
        raise RuntimeError(f'Invalid panel_threads: {panel_threads}')

    parsed = _parse_api_base_url()
    if not parsed.hostname:
        raise RuntimeError('Invalid cliproxy_api_base configuration')


def _parse_api_base_url():
    base_url = str(CONFIG.get('cliproxy_api_base', 'http://127.0.0.1')).strip() or 'http://127.0.0.1'
    if '://' not in base_url:
        base_url = f'http://{base_url}'
    parsed = urlparse(base_url)
    return parsed


def _api_host():
    parsed = _parse_api_base_url()
    return parsed.hostname or '127.0.0.1'


def _api_port():
    parsed = _parse_api_base_url()
    parsed_port = parsed.port
    if parsed_port:
        return parsed_port
    return int(CONFIG.get('cliproxy_api_port', 8317))


def _api_scheme():
    parsed = _parse_api_base_url()
    return parsed.scheme or 'http'


def _build_api_base_url():
    return f'{_api_scheme()}://{_api_host()}:{_api_port()}'


def _is_local_api_host():
    return _api_host() in {'127.0.0.1', 'localhost'}


def _panel_credentials():
    return (
        str(CONFIG.get('panel_username', '')),
        str(CONFIG.get('panel_password', '')),
    )


def _panel_access_key_expected():
    return str(CONFIG.get('panel_access_key', '') or '').strip()


def _panel_access_key_provided():
    return str(
        request.headers.get('X-Panel-Key')
        or request.args.get('panel_key')
        or request.cookies.get('panel_key')
        or ''
    ).strip()


def _has_valid_basic_auth():
    username, password = _panel_credentials()
    auth = request.authorization
    return bool(
        auth
        and hmac.compare_digest(auth.username or '', username)
        and hmac.compare_digest(auth.password or '', password)
    )


def _has_valid_panel_access_key():
    expected = _panel_access_key_expected()
    if not expected:
        return False
    return hmac.compare_digest(_panel_access_key_provided(), expected)


def is_config_write_enabled():
    return _parse_bool(CONFIG.get('config_write_enabled', False))


def config_write_blocked_response():
    message = '当前面板已禁用配置写入，只保留自动更新和查看能力'
    return jsonify({'success': False, 'error': message, 'message': message}), 403


def _same_origin(value):
    if not value:
        return True
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return False
    origin_host = (parsed.hostname or '').lower()
    request_host = (request.host.split(':')[0]).lower()
    return origin_host == request_host


@app.before_request
def enforce_admin_security():
    if request.path in PUBLIC_PATHS:
        return None

    basic_auth_valid = _has_valid_basic_auth()
    panel_key_valid = request.path.startswith('/api') and _has_valid_panel_access_key()

    if not basic_auth_valid and not panel_key_valid:
        if request.path.startswith('/api'):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        return Response(
            'Unauthorized - valid admin credentials required',
            401,
            {'WWW-Authenticate': 'Basic realm="CPA-X Panel"'},
        )

    if request.method in UNSAFE_METHODS and request.path.startswith('/api/'):
        if request.headers.get(PANEL_REQUEST_HEADER) != PANEL_REQUEST_HEADER_VALUE:
            return jsonify({
                'success': False,
                'message': f'Missing required header: {PANEL_REQUEST_HEADER}',
            }), 403
        if not _same_origin(request.headers.get('Origin')):
            return jsonify({'success': False, 'message': 'Cross-origin request rejected'}), 403
        if not _same_origin(request.headers.get('Referer')):
            return jsonify({'success': False, 'message': 'Cross-origin request rejected'}), 403

    return None


@app.after_request
def apply_response_security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'same-origin')
    if request.path.startswith('/api/'):
        response.headers.setdefault('Cache-Control', 'no-store')
    return response


load_config_overrides()
validate_runtime_config()

UPDATE_HISTORY_PATH = os.path.join(DATA_DIR, 'update_history.json')

# 全局状态
state = {
    'last_request_time': None,
    'request_count': 0,
    'update_in_progress': False,
    'last_update_time': None,
    'last_update_result': None,
    'last_auto_update_check_time': None,
    'next_auto_update_check_time': None,
    'current_version': 'unknown',
    'latest_version': 'unknown',
    'auto_update_enabled': CONFIG['auto_update_enabled'],
    'request_log': [],
    # 统计数据
    'stats': {
        'total_requests': 0,
        'successful_requests': 0,
        'failed_requests': 0,
        'input_tokens': 0,
        'output_tokens': 0,
        'cached_tokens': 0,
        'total_response_time': 0,
        'requests_per_minute': deque(maxlen=60),
        'requests_per_hour': deque(maxlen=24),
        'model_usage': {},
        'error_types': {},
        'hourly_stats': deque(maxlen=24),
    },
    # 上次从 CLIProxyAPI 读取的快照值（用于计算增量）
    'last_snapshot': {
        'input_tokens': 0,
        'output_tokens': 0,
        'cached_tokens': 0,
        'total_requests': 0,
        'success': 0,
        'failure': 0,
    },
    # 面板独立累加的统计数据（持久化保存，不受 CLIProxyAPI 重启影响）
    'accumulated_stats': {
        'input_tokens': 0,
        'output_tokens': 0,
        'cached_tokens': 0,
        'total_requests': 0,
        'success': 0,
        'failure': 0,
    },
    'last_health_check': None,
    'health_status': 'unknown',
    'log_stats': {
        'initialized': False,
        'offset': 0,
        'last_size': 0,
        'last_mtime': None,
        'total': 0,
        'success': 0,
        'failed': 0,
        'last_time': None,
        'buffer': '',
        'base_total': 0,
        'base_success': 0,
        'base_failed': 0,
        'last_saved_ts': 0
    },
    'log_stats_loaded': False,
}

log_lock = threading.Lock()
log_stats_lock = threading.Lock()
stats_lock = threading.Lock()
persistent_stats_lock = threading.Lock()
usage_sync_lock = threading.Lock()

# ==================== 持久化统计系统 ====================
PERSISTENT_STATS_FIELDS = (
    'total_requests',
    'successful_requests',
    'failed_requests',
    'input_tokens',
    'output_tokens',
    'cached_tokens',
    'model_usage',
)


def load_persistent_stats():
    """从磁盘加载持久化统计数据"""
    def safe_int(v, default=0):
        try:
            return int(v)
        except:
            return default
    
    path = CONFIG.get('persistent_stats_path')
    if not path or not os.path.exists(path):
        return False
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return False
        with stats_lock:
            for key in PERSISTENT_STATS_FIELDS:
                if key in data:
                    if key == 'model_usage':
                        state['stats'][key] = data[key] if isinstance(data[key], dict) else {}
                    else:
                        state['stats'][key] = safe_int(data[key])
            # 加载累计统计值
            if 'accumulated_stats' in data and isinstance(data['accumulated_stats'], dict):
                for key in state['accumulated_stats']:
                    if key in data['accumulated_stats']:
                        state['accumulated_stats'][key] = safe_int(data['accumulated_stats'][key])
            # 加载上次快照值
            if 'last_snapshot' in data and isinstance(data['last_snapshot'], dict):
                for key in state['last_snapshot']:
                    if key in data['last_snapshot']:
                        state['last_snapshot'][key] = safe_int(data['last_snapshot'][key])
            # 同步 request_count
            state['request_count'] = state['stats']['total_requests']
        print(f"Loaded persistent stats: accumulated={state['accumulated_stats']}, last_snapshot={state['last_snapshot']}")
        return True
    except Exception as e:
        print(f"Warning: failed to load persistent stats: {e}")
        return False


def save_persistent_stats(force=False):
    """保存统计数据到磁盘"""
    path = CONFIG.get('persistent_stats_path')
    if not path:
        return False
    with persistent_stats_lock:
        now = time.time()
        # 限制保存频率，除非强制保存
        last_saved = getattr(save_persistent_stats, '_last_saved', 0)
        if not force and now - last_saved < 10:
            return False
        save_persistent_stats._last_saved = now
    
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with stats_lock:
            payload = {
                'total_requests': state['stats'].get('total_requests', 0),
                'successful_requests': state['stats'].get('successful_requests', 0),
                'failed_requests': state['stats'].get('failed_requests', 0),
                'input_tokens': state['stats'].get('input_tokens', 0),
                'output_tokens': state['stats'].get('output_tokens', 0),
                'cached_tokens': state['stats'].get('cached_tokens', 0),
                'model_usage': dict(state['stats'].get('model_usage', {})),
                'accumulated_stats': dict(state.get('accumulated_stats', {})),
                'last_snapshot': dict(state.get('last_snapshot', {})),
                'saved_at': datetime.now().isoformat(),
            }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Warning: failed to save persistent stats: {e}")
        return False


def _persistent_stats_worker():
    """后台线程：定期保存统计数据"""
    while True:
        time.sleep(30)  # 每30秒保存一次
        try:
            save_persistent_stats()
        except Exception as e:
            print(f"Warning: persistent stats worker error: {e}")


def start_persistent_stats_worker():
    """启动持久化统计后台线程"""
    thread = threading.Thread(target=_persistent_stats_worker, daemon=True)
    thread.start()


# ==================== 缓存系统 ====================
class CacheManager:
    """轻量级缓存管理器"""
    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()

    def get(self, key, max_age=5):
        """获取缓存值，max_age为秒数"""
        with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if time.time() - timestamp < max_age:
                    return value
        return None

    def set(self, key, value):
        """设置缓存值"""
        with self._lock:
            self._cache[key] = (value, time.time())

    def invalidate(self, key=None):
        """使缓存失效"""
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _build_management_base_url():
    return _build_api_base_url()


def _management_headers():
    key = CONFIG.get('management_key', '')
    headers = {'Content-Type': 'application/json'}
    if key:
        headers['X-Management-Key'] = key
    return headers


def _normalize_named_items(items, name_key):
    if isinstance(items, dict):
        normalized = []
        for name, value in items.items():
            if isinstance(value, dict):
                item = dict(value)
                item.setdefault(name_key, name)
            else:
                item = {name_key: name, 'value': value}
            normalized.append(item)
        return normalized
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def _extract_usage_tokens(obj):
    if not isinstance(obj, dict):
        return {
            'input_tokens': 0,
            'output_tokens': 0,
            'cached_tokens': 0,
            'total_tokens': 0,
        }

    tokens = obj.get('tokens') or obj.get('usage') or obj
    input_tokens = _safe_int(tokens.get('input_tokens', tokens.get('input', tokens.get('prompt_tokens', 0))))
    output_tokens = _safe_int(tokens.get('output_tokens', tokens.get('output', tokens.get('completion_tokens', 0))))
    cached_tokens = _safe_int(tokens.get('cached_tokens', tokens.get('cache', 0)))
    reasoning_tokens = _safe_int(tokens.get('reasoning_tokens', tokens.get('reasoning', 0)))
    total_tokens = _safe_int(tokens.get('total_tokens', tokens.get('total', obj.get('total_tokens', 0))))
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens + reasoning_tokens

    return {
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'cached_tokens': cached_tokens,
        'total_tokens': total_tokens,
    }


def _extract_auth_file_items(payload):
    items = []
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        for key in ('files', 'auth_files', 'items', 'data'):
            value = payload.get(key)
            if isinstance(value, list):
                items = value
                break

    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue
        record = dict(item)
        path = str(record.get('path') or '').strip()
        if path and not record.get('name'):
            record['name'] = os.path.basename(path.rstrip('/'))
        normalized.append(record)
    return normalized


def fetch_management_auth_files(use_cache=True):
    cache_key = 'management_auth_files_v1'
    if use_cache:
        cached = cache.get(cache_key, max_age=30)
        if cached is not None:
            return cached

    url = f'{_build_management_base_url()}/v0/management/auth-files'
    try:
        resp = requests.get(url, headers=_management_headers(), timeout=6)
        resp.raise_for_status()
        payload = resp.json() if resp.content else {}
        files = _extract_auth_file_items(payload)
        cache.set(cache_key, files)
        return files
    except Exception:
        return []


def _auth_display_label(item):
    for key in ('label', 'account', 'email', 'name', 'id'):
        value = str(item.get(key) or '').strip()
        if value:
            return value
    path = str(item.get('path') or '').strip()
    if path:
        return os.path.basename(path.rstrip('/')) or path
    return 'Unknown account'


def _auth_match_keys(item):
    values = []
    for key in ('id', 'auth_index', 'auth_id', 'name', 'label', 'account', 'email'):
        value = str(item.get(key) or '').strip()
        if value:
            values.append(value)
    path = str(item.get('path') or '').strip()
    if path:
        values.append(path)
        values.append(os.path.basename(path.rstrip('/')))

    seen = set()
    keys = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            keys.append(value)
    return keys


def _build_auth_lookup(auth_files):
    lookup = {}
    for item in auth_files:
        if not isinstance(item, dict):
            continue
        meta = {
            'id': str(item.get('id') or item.get('auth_index') or item.get('auth_id') or _auth_display_label(item)).strip(),
            'label': _auth_display_label(item),
            'provider': str(item.get('provider') or item.get('type') or '').strip(),
            'account': str(item.get('account') or '').strip(),
            'email': str(item.get('email') or '').strip(),
            'matched': True,
        }
        for key in _auth_match_keys(item):
            lookup[key] = meta
            lookup[key.lower()] = meta
    return lookup


def _resolve_auth_meta(auth_index, auth_lookup):
    value = str(auth_index or '').strip()
    if not value:
        return {
            'id': 'unknown',
            'label': 'Unknown account',
            'provider': '',
            'account': '',
            'email': '',
            'matched': False,
        }

    meta = auth_lookup.get(value) or auth_lookup.get(value.lower())
    if meta:
        return meta

    short_value = value if len(value) <= 18 else f'{value[:8]}...{value[-6:]}'
    return {
        'id': value,
        'label': short_value,
        'provider': '',
        'account': '',
        'email': '',
        'matched': False,
    }


def _local_timezone():
    return datetime.now().astimezone().tzinfo or timezone.utc


def _parse_usage_timestamp(value):
    text = str(value or '').strip()
    if not text:
        return None

    candidates = [text]
    if text.endswith('Z'):
        candidates.insert(0, text[:-1] + '+00:00')
    if ' ' in text and 'T' not in text:
        candidates.append(text.replace(' ', 'T'))
        candidates.append(text.replace(' ', 'T') + '+00:00')

    for candidate in candidates:
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(_local_timezone())
        except Exception:
            continue

    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            return dt.astimezone(_local_timezone())
        except Exception:
            continue
    return None


def _floor_usage_bucket(dt_value, bucket):
    if bucket == 'hour':
        return dt_value.replace(minute=0, second=0, microsecond=0)
    if bucket == 'day':
        return dt_value.replace(hour=0, minute=0, second=0, microsecond=0)
    return dt_value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _shift_usage_month(dt_value, delta_months):
    total_months = dt_value.year * 12 + (dt_value.month - 1) + delta_months
    year = total_months // 12
    month = total_months % 12 + 1
    return dt_value.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)


def _usage_bucket_sequence(bucket, now_value=None):
    now_local = now_value or datetime.now().astimezone()
    end = _floor_usage_bucket(now_local, bucket)
    limit = USAGE_ANALYTICS_LIMITS[bucket]

    if bucket == 'month':
        return [_shift_usage_month(end, offset) for offset in range(-(limit - 1), 1)]

    delta = timedelta(hours=1) if bucket == 'hour' else timedelta(days=1)
    return [end - delta * offset for offset in range(limit - 1, -1, -1)]


def _usage_bucket_label(dt_value, bucket):
    if bucket == 'hour':
        return dt_value.strftime('%H:00')
    if bucket == 'day':
        return dt_value.strftime('%m-%d')
    return dt_value.strftime('%Y-%m')


def _usage_bucket_range_label(bucket):
    labels = {
        'hour': f'最近 {USAGE_ANALYTICS_LIMITS["hour"]} 小时',
        'day': f'最近 {USAGE_ANALYTICS_LIMITS["day"]} 天',
        'month': f'最近 {USAGE_ANALYTICS_LIMITS["month"]} 个月',
    }
    return labels.get(bucket, bucket)


def _new_usage_metric_totals():
    return {
        'requests': 0,
        'success': 0,
        'failed': 0,
        'input_tokens': 0,
        'output_tokens': 0,
        'cached_tokens': 0,
        'total_tokens': 0,
        'billable_input_tokens': 0,
        'cost': 0.0,
    }


def _merge_usage_metrics(target, source):
    for key in ('requests', 'success', 'failed', 'input_tokens', 'output_tokens', 'cached_tokens', 'total_tokens', 'billable_input_tokens'):
        target[key] = _safe_int(target.get(key, 0)) + _safe_int(source.get(key, 0))
    target['cost'] = _safe_float(target.get('cost', 0.0)) + _safe_float(source.get('cost', 0.0))
    return target


def _serialize_usage_metrics(metrics):
    payload = {key: _safe_int(metrics.get(key, 0)) for key in ('requests', 'success', 'failed', 'input_tokens', 'output_tokens', 'cached_tokens', 'total_tokens', 'billable_input_tokens')}
    payload['cost'] = round(_safe_float(metrics.get('cost', 0.0)), 6)
    return payload


def _new_usage_bucket_point(dt_value, bucket):
    point = {
        'key': dt_value.isoformat(),
        'label': _usage_bucket_label(dt_value, bucket),
        'start': dt_value.isoformat(),
    }
    point.update(_new_usage_metric_totals())
    return point


def _extract_usage_details(snapshot, pricing):
    usage = snapshot.get('usage') if isinstance(snapshot, dict) else None
    if not isinstance(usage, dict):
        usage = snapshot if isinstance(snapshot, dict) else {}

    for api in _normalize_named_items(usage.get('apis', []), 'name'):
        api_name = str(api.get('name') or api.get('id') or '').strip()
        for model in _normalize_named_items(api.get('models', []), 'id'):
            model_id = str(model.get('id') or model.get('name') or '').strip()
            details = model.get('details')
            if isinstance(details, dict):
                details = list(details.values())
            if not isinstance(details, list):
                continue

            for detail in details:
                if not isinstance(detail, dict):
                    continue

                timestamp = _parse_usage_timestamp(detail.get('timestamp') or detail.get('requested_at') or detail.get('time'))
                if timestamp is None:
                    continue

                token_totals = _extract_usage_tokens(detail)
                detail_requests = _safe_int(detail.get('requests', detail.get('count', 1)), 1)
                if detail_requests < 1:
                    detail_requests = 1
                status_code = _safe_int(detail.get('status_code', detail.get('status', 0)), 0)
                failed_flag = _parse_bool(detail.get('failed', detail.get('is_failed', False)))
                success_count = 0 if failed_flag or status_code >= 400 else detail_requests
                failed_count = detail_requests - success_count
                cost = compute_usage_costs(token_totals, pricing).get('total', 0.0)

                yield {
                    'timestamp': timestamp,
                    'api': api_name,
                    'model': model_id,
                    'auth_index': str(detail.get('auth_index') or detail.get('auth_id') or detail.get('account_id') or '').strip(),
                    'requests': detail_requests,
                    'success': success_count,
                    'failed': failed_count,
                    'input_tokens': token_totals['input_tokens'],
                    'output_tokens': token_totals['output_tokens'],
                    'cached_tokens': token_totals['cached_tokens'],
                    'total_tokens': token_totals['total_tokens'],
                    'billable_input_tokens': get_billable_input_tokens(token_totals),
                    'cost': cost,
                }


def _extract_series_map(value):
    if isinstance(value, dict):
        return {str(key): _safe_int(raw, 0) for key, raw in value.items()}

    if isinstance(value, list):
        result = {}
        for item in value:
            if not isinstance(item, dict):
                continue
            key = item.get('date') or item.get('hour') or item.get('bucket') or item.get('name')
            if key is None:
                continue
            result[str(key)] = _safe_int(item.get('value', item.get('count', item.get('tokens', 0))), 0)
        return result

    return {}


def _build_usage_analytics_fallback(snapshot):
    usage = snapshot.get('usage') if isinstance(snapshot, dict) else None
    if not isinstance(usage, dict):
        usage = snapshot if isinstance(snapshot, dict) else {}

    requests_by_day = _extract_series_map(usage.get('requests_by_day'))
    tokens_by_day = _extract_series_map(usage.get('tokens_by_day'))
    requests_by_hour = _extract_series_map(usage.get('requests_by_hour'))
    tokens_by_hour = _extract_series_map(usage.get('tokens_by_hour'))
    now_local = datetime.now().astimezone()
    analytics = {}

    for bucket in USAGE_ANALYTICS_BUCKETS:
        points = []
        for bucket_start in _usage_bucket_sequence(bucket, now_local):
            point = _new_usage_bucket_point(bucket_start, bucket)
            if bucket == 'day':
                day_key = bucket_start.strftime('%Y-%m-%d')
                point['requests'] = requests_by_day.get(day_key, 0)
                point['total_tokens'] = tokens_by_day.get(day_key, 0)
            elif bucket == 'month':
                month_key = bucket_start.strftime('%Y-%m')
                month_requests = 0
                month_tokens = 0
                for day_key, value in requests_by_day.items():
                    if str(day_key).startswith(month_key):
                        month_requests += _safe_int(value, 0)
                for day_key, value in tokens_by_day.items():
                    if str(day_key).startswith(month_key):
                        month_tokens += _safe_int(value, 0)
                point['requests'] = month_requests
                point['total_tokens'] = month_tokens
            else:
                hour_key = bucket_start.strftime('%H')
                point['requests'] = requests_by_hour.get(hour_key, requests_by_hour.get(str(int(hour_key)), 0))
                point['total_tokens'] = tokens_by_hour.get(hour_key, tokens_by_hour.get(str(int(hour_key)), 0))
            points.append(point)

        totals = _new_usage_metric_totals()
        for point in points:
            _merge_usage_metrics(totals, point)

        analytics[bucket] = {
            'range_label': _usage_bucket_range_label(bucket),
            'points': [{**point, **_serialize_usage_metrics(point)} for point in points],
            'totals': _serialize_usage_metrics(totals),
            'accounts': [],
        }

    return analytics


def build_usage_analytics(use_cache=True):
    cache_key = 'usage_analytics_v2'
    if use_cache:
        cached = cache.get(cache_key, max_age=30)
        if cached is not None:
            return cached

    snapshot = fetch_usage_snapshot(use_cache=use_cache)
    pricing, pricing_meta = get_effective_pricing()
    auth_files = fetch_management_auth_files(use_cache=use_cache)
    auth_lookup = _build_auth_lookup(auth_files)
    now_local = datetime.now().astimezone()

    bucket_data = {}
    for bucket in USAGE_ANALYTICS_BUCKETS:
        points = [_new_usage_bucket_point(bucket_start, bucket) for bucket_start in _usage_bucket_sequence(bucket, now_local)]
        bucket_data[bucket] = {
            'points_map': {point['key']: point for point in points},
            'totals': _new_usage_metric_totals(),
            'accounts_map': {},
        }

    detail_records = 0
    account_records = 0
    unmatched_account_records = 0

    for record in _extract_usage_details(snapshot, pricing):
        detail_records += 1
        auth_meta = None
        if record.get('auth_index'):
            account_records += 1
            auth_meta = _resolve_auth_meta(record['auth_index'], auth_lookup)
            if not auth_meta.get('matched'):
                unmatched_account_records += 1

        for bucket in USAGE_ANALYTICS_BUCKETS:
            bucket_start = _floor_usage_bucket(record['timestamp'], bucket)
            point = bucket_data[bucket]['points_map'].get(bucket_start.isoformat())
            if point is None:
                continue

            _merge_usage_metrics(point, record)
            _merge_usage_metrics(bucket_data[bucket]['totals'], record)

            if auth_meta is None:
                continue

            account_entry = bucket_data[bucket]['accounts_map'].get(auth_meta['id'])
            if account_entry is None:
                account_entry = {
                    'id': auth_meta['id'],
                    'label': auth_meta['label'],
                    'provider': auth_meta['provider'],
                    'account': auth_meta['account'],
                    'email': auth_meta['email'],
                    'matched': bool(auth_meta.get('matched')),
                }
                account_entry.update(_new_usage_metric_totals())
                bucket_data[bucket]['accounts_map'][auth_meta['id']] = account_entry
            _merge_usage_metrics(account_entry, record)

    if detail_records == 0:
        payload = {
            'success': True,
            'generated_at': datetime.now().isoformat(),
            'pricing_basis': get_pricing_basis_info(),
            'pricing_meta': pricing_meta,
            'meta': {
                'has_detail_records': False,
                'detail_record_count': 0,
                'has_account_dimension': False,
                'supports_cost': False,
                'account_record_count': 0,
                'mapped_account_count': 0,
                'account_source': 'unavailable',
                'notes': [
                    '当前 usage snapshot 未暴露逐条请求明细，因此无法绘制历史费用与账号维度图表。',
                    '当上游只暴露 requests_by_hour 时，小时图会退化为按小时段聚合而不是最近 24 小时时间线。',
                ],
            },
            'analytics': _build_usage_analytics_fallback(snapshot),
        }
        cache.set(cache_key, payload)
        return payload

    analytics = {}
    has_account_dimension = False
    for bucket in USAGE_ANALYTICS_BUCKETS:
        ordered_points = list(bucket_data[bucket]['points_map'].values())
        account_entries = list(bucket_data[bucket]['accounts_map'].values())
        account_entries.sort(key=lambda item: (-_safe_float(item.get('cost', 0.0)), -_safe_int(item.get('requests', 0)), item.get('label', '')))

        total_requests = max(_safe_int(bucket_data[bucket]['totals'].get('requests', 0)), 1)
        total_tokens = max(_safe_int(bucket_data[bucket]['totals'].get('total_tokens', 0)), 1)
        total_cost = max(_safe_float(bucket_data[bucket]['totals'].get('cost', 0.0)), 0.000001)

        serialized_accounts = []
        for entry in account_entries:
            payload = {
                'id': entry['id'],
                'label': entry['label'],
                'provider': entry.get('provider', ''),
                'account': entry.get('account', ''),
                'email': entry.get('email', ''),
                'matched': bool(entry.get('matched')),
            }
            payload.update(_serialize_usage_metrics(entry))
            payload['share_requests'] = round(payload['requests'] / total_requests, 6)
            payload['share_tokens'] = round(payload['total_tokens'] / total_tokens, 6)
            payload['share_cost'] = round(payload['cost'] / total_cost, 6)
            serialized_accounts.append(payload)

        analytics[bucket] = {
            'range_label': _usage_bucket_range_label(bucket),
            'points': [{**point, **_serialize_usage_metrics(point)} for point in ordered_points],
            'totals': _serialize_usage_metrics(bucket_data[bucket]['totals']),
            'accounts': serialized_accounts,
        }
        has_account_dimension = has_account_dimension or bool(serialized_accounts)

    notes = []
    if auth_files and unmatched_account_records > 0:
        notes.append('部分 auth_index 无法映射到 runtime auth metadata，当前会按原始 ID 显示。')
    if not auth_files and account_records > 0:
        notes.append('当前无法从 runtime auth-files 取得账号标签，因此会直接显示 auth_index。')

    payload = {
        'success': True,
        'generated_at': datetime.now().isoformat(),
        'pricing_basis': get_pricing_basis_info(),
        'pricing_meta': pricing_meta,
        'meta': {
            'has_detail_records': True,
            'detail_record_count': detail_records,
            'has_account_dimension': has_account_dimension,
            'supports_cost': True,
            'account_record_count': account_records,
            'mapped_account_count': len(auth_files),
            'account_source': 'management_auth_files' if auth_files else 'unavailable',
            'notes': notes,
        },
        'analytics': analytics,
    }
    cache.set(cache_key, payload)
    return payload


def load_usage_snapshot_from_disk():
    path = CONFIG.get('usage_snapshot_path')
    if not path:
        return None
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Warning: failed to load usage snapshot: {e}")
    return None


def save_usage_snapshot(snapshot):
    path = CONFIG.get('usage_snapshot_path')
    if not path or snapshot is None:
        return False
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Warning: failed to save usage snapshot: {e}")
        return False


LOG_STATS_PERSIST_FIELDS = (
    'initialized',
    'offset',
    'last_size',
    'last_mtime',
    'total',
    'success',
    'failed',
    'last_time',
    'base_total',
    'base_success',
    'base_failed',
)


def _ensure_parent_dir(path):
    if not path:
        return False
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return True
    except Exception as e:
        print(f"Warning: failed to create directory for {path}: {e}")
        return False


def load_log_stats_state():
    path = CONFIG.get('log_stats_path')
    if not path or not os.path.exists(path):
        return False
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return False
        with log_stats_lock:
            log_state = state.get('log_stats', {}).copy()
            for key in LOG_STATS_PERSIST_FIELDS:
                if key in data:
                    log_state[key] = data[key]
            log_state['buffer'] = ''
            state['log_stats'] = log_state
            state['log_stats_loaded'] = True
        return True
    except Exception as e:
        print(f"Warning: failed to load log stats: {e}")
        return False


def save_log_stats_state(force=False):
    path = CONFIG.get('log_stats_path')
    if not path:
        return False
    with log_stats_lock:
        log_state = state.get('log_stats', {})
        now = time.time()
        last_saved = _safe_float(log_state.get('last_saved_ts', 0), 0.0)
        if not force and now - last_saved < 5:
            return False
        payload = {key: log_state.get(key) for key in LOG_STATS_PERSIST_FIELDS}
        log_state['last_saved_ts'] = now
        state['log_stats'] = log_state
    if not _ensure_parent_dir(path):
        return False
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Warning: failed to save log stats: {e}")
        return False


def fetch_usage_snapshot(use_cache=True):
    cache_key = 'usage_snapshot'
    if use_cache:
        cached = cache.get(cache_key, max_age=2)
        if cached is not None:
            return cached

    base_url = _build_management_base_url()
    url = f'{base_url}/v0/management/usage'
    headers = _management_headers()
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        resp.raise_for_status()
        snapshot = resp.json()
        cache.set(cache_key, snapshot)
        save_usage_snapshot(snapshot)
        return snapshot
    except Exception:
        snapshot = load_usage_snapshot_from_disk()
        if snapshot is not None:
            cache.set(cache_key, snapshot)
        return snapshot


def aggregate_usage_snapshot(snapshot):
    totals = {
        'input_tokens': 0,
        'output_tokens': 0,
        'cached_tokens': 0,
        'total_tokens': 0,
    }
    reqs = {
        'total_requests': 0,
        'success': 0,
        'failure': 0,
    }
    if not snapshot:
        return totals, reqs

    usage = snapshot.get('usage') if isinstance(snapshot, dict) else None
    if not isinstance(usage, dict):
        usage = snapshot if isinstance(snapshot, dict) else {}

    top_total = _safe_int(usage.get('total_requests', usage.get('total', 0)))
    top_success = _safe_int(usage.get('success', usage.get('successful_requests', usage.get('success_count', 0))))
    top_failure = _safe_int(usage.get('failure', usage.get('failed_requests', usage.get('failure_count', 0))))

    apis = usage.get('apis', [])
    if isinstance(apis, dict):
        apis = list(apis.values())
    if not isinstance(apis, list):
        apis = []

    sum_total = 0
    sum_success = 0
    sum_failure = 0

    for api in apis:
        if not isinstance(api, dict):
            continue
        sum_total += _safe_int(api.get('total_requests', api.get('total', api.get('requests', 0))))
        sum_success += _safe_int(api.get('success', api.get('successful_requests', api.get('success_count', 0))))
        sum_failure += _safe_int(api.get('failure', api.get('failed_requests', api.get('failure_count', 0))))

        models = api.get('models', [])
        if isinstance(models, dict):
            models = list(models.values())
        if not isinstance(models, list):
            continue
        for model in models:
            if not isinstance(model, dict):
                continue
            details = model.get('details')
            if isinstance(details, list) and details:
                for detail in details:
                    token_totals = _extract_usage_tokens(detail)
                    totals['input_tokens'] += token_totals['input_tokens']
                    totals['output_tokens'] += token_totals['output_tokens']
                    totals['cached_tokens'] += token_totals['cached_tokens']
                    totals['total_tokens'] += token_totals['total_tokens']
            else:
                token_totals = _extract_usage_tokens(model)
                totals['input_tokens'] += token_totals['input_tokens']
                totals['output_tokens'] += token_totals['output_tokens']
                totals['cached_tokens'] += token_totals['cached_tokens']
                totals['total_tokens'] += token_totals['total_tokens']

    if totals['total_tokens'] == 0:
        totals['total_tokens'] = _safe_int(usage.get('total_tokens', 0))

    if top_total > 0:
        reqs['total_requests'] = top_total
        reqs['success'] = top_success
        reqs['failure'] = top_failure
    else:
        reqs['total_requests'] = sum_total
        reqs['success'] = sum_success
        reqs['failure'] = sum_failure

    return totals, reqs


def compute_usage_costs(tokens, pricing):
    input_price = _safe_float(pricing.get('input', 0.0))
    output_price = _safe_float(pricing.get('output', 0.0))
    cache_price = _safe_float(pricing.get('cache', 0.0))

    billable_input_tokens = get_billable_input_tokens(tokens)
    output_tokens = _safe_int(tokens.get('output_tokens', 0))
    cached_tokens = _safe_int(tokens.get('cached_tokens', 0))

    input_cost = billable_input_tokens / PRICING_BASIS_TOKENS * input_price
    output_cost = output_tokens / PRICING_BASIS_TOKENS * output_price
    cache_cost = cached_tokens / PRICING_BASIS_TOKENS * cache_price
    total_cost = input_cost + output_cost + cache_cost

    return {
        'input': input_cost,
        'output': output_cost,
        'cache': cache_cost,
        'total': total_cost,
    }


def get_billable_input_tokens(tokens):
    input_tokens = _safe_int(tokens.get('input_tokens', 0))
    cached_tokens = _safe_int(tokens.get('cached_tokens', 0))
    return max(input_tokens - cached_tokens, 0)


def get_pricing_basis_info():
    return {
        'tokens': PRICING_BASIS_TOKENS,
        'label': PRICING_BASIS_LABEL,
        'text': PRICING_BASIS_TEXT,
    }


def _parse_float_or_none(value):
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _fetch_openrouter_models():
    cache_key = 'openrouter_models_v1'
    cached = cache.get(cache_key, max_age=6 * 3600)
    if cached is not None:
        return cached

    try:
        resp = requests.get(
            'https://openrouter.ai/api/v1/models',
            timeout=15,
            headers={'User-Agent': 'CPA-X Panel'},
        )
        resp.raise_for_status()
        payload = resp.json() if resp.content else {}
        models = payload.get('data', []) if isinstance(payload, dict) else []
        if not isinstance(models, list):
            models = []
        cache.set(cache_key, models)
        return models
    except Exception as e:
        print(f'Warning: failed to fetch openrouter models: {e}')
        cache.set(cache_key, [])
        return []


def _openrouter_pricing_per_million(model_id):
    if not model_id:
        return None

    for model in _fetch_openrouter_models():
        if not isinstance(model, dict):
            continue
        if (model.get('id') or '') != model_id:
            continue
        pricing = model.get('pricing') if isinstance(model.get('pricing'), dict) else {}
        prompt = _parse_float_or_none(pricing.get('prompt'))
        completion = _parse_float_or_none(pricing.get('completion'))
        cache_read = _parse_float_or_none(pricing.get('input_cache_read'))
        if prompt is None or completion is None:
            return None

        per_million = {
            'input': prompt * PRICING_BASIS_TOKENS,
            'output': completion * PRICING_BASIS_TOKENS,
            'cache': (cache_read if cache_read is not None else prompt) * PRICING_BASIS_TOKENS,
        }
        return {
            'pricing': per_million,
            'model': model_id,
            'source': 'openrouter',
        }
    return None


def _pick_pricing_auto_model_id():
    configured = str(CONFIG.get('pricing_auto_model', '') or '').strip()
    if configured:
        return configured
    try:
        models, _ = get_models_from_config()
        if isinstance(models, list) and models:
            model_id = (models[0].get('id') if isinstance(models[0], dict) else None) or ''
            model_id = str(model_id).strip()
            if model_id:
                return model_id
    except Exception:
        pass
    return 'openai/gpt-4o-mini'


def get_effective_pricing():
    manual = {
        'input': _safe_float(CONFIG.get('pricing_input', 0.0)),
        'output': _safe_float(CONFIG.get('pricing_output', 0.0)),
        'cache': _safe_float(CONFIG.get('pricing_cache', 0.0)),
    }
    meta = {
        'mode': 'manual',
        'source': 'manual',
        'model': None,
        'fields': {'input': 'manual', 'output': 'manual', 'cache': 'manual'},
        'auto_enabled': _parse_bool(CONFIG.get('pricing_auto_enabled', True)),
        'auto_source': str(CONFIG.get('pricing_auto_source', 'openrouter') or 'openrouter').strip().lower(),
        'auto_model': (str(CONFIG.get('pricing_auto_model', '') or '').strip() or None),
    }

    if not _parse_bool(CONFIG.get('pricing_auto_enabled', True)):
        return manual, meta

    if not any(manual.get(key, 0.0) <= 0 for key in ('input', 'output', 'cache')):
        return manual, meta

    source = str(CONFIG.get('pricing_auto_source', 'openrouter') or 'openrouter').strip().lower()
    if source != 'openrouter':
        return manual, meta

    model_id = _pick_pricing_auto_model_id()
    suggested = _openrouter_pricing_per_million(model_id)
    if not suggested and model_id != 'openai/gpt-4o-mini':
        suggested = _openrouter_pricing_per_million('openai/gpt-4o-mini')
    if not suggested:
        return manual, meta

    effective = dict(manual)
    fields = dict(meta['fields'])
    for key in ('input', 'output', 'cache'):
        if effective.get(key, 0.0) <= 0:
            effective[key] = _safe_float(suggested['pricing'].get(key, effective[key]))
            fields[key] = 'openrouter'

    meta = {
        'mode': 'mixed' if any(v == 'openrouter' for v in fields.values()) and any(v == 'manual' for v in fields.values()) else 'auto',
        'source': suggested.get('source', 'openrouter'),
        'model': suggested.get('model'),
        'fields': fields,
        'auto_enabled': True,
        'auto_source': source,
        'auto_model': (str(CONFIG.get('pricing_auto_model', '') or '').strip() or None),
    }
    return effective, meta


def import_usage_snapshot(snapshot):
    if not snapshot:
        return False
    base_url = _build_management_base_url()
    url = f'{base_url}/v0/management/usage/import'
    headers = _management_headers()
    try:
        resp = requests.post(url, headers=headers, json=snapshot, timeout=8)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"Warning: usage import failed: {e}")
        return False


def _usage_snapshot_worker():
    snapshot = load_usage_snapshot_from_disk()
    if snapshot:
        import_usage_snapshot(snapshot)
    while True:
        try:
            fetch_usage_snapshot(use_cache=False)
        except Exception:
            pass
        time.sleep(60)


def start_usage_snapshot_worker():
    thread = threading.Thread(target=_usage_snapshot_worker, daemon=True)
    thread.start()


def _read_file_first_line(path):
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.readline().strip()
    except Exception:
        pass
    return None


def get_system_info():
    info = {
        'cpu_model': None,
        'os_version': None,
        'cloud_vendor': None,
    }
    if is_linux():
        try:
            with open('/proc/cpuinfo', 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if 'model name' in line:
                        info['cpu_model'] = line.split(':', 1)[-1].strip()
                        break
        except Exception:
            pass

        try:
            with open('/etc/os-release', 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    if line.startswith('PRETTY_NAME='):
                        info['os_version'] = line.split('=', 1)[-1].strip().strip('"')
                        break
        except Exception:
            pass

        vendor = _read_file_first_line('/sys/class/dmi/id/sys_vendor')
        product = _read_file_first_line('/sys/class/dmi/id/product_name')
        if vendor or product:
            info['cloud_vendor'] = ' '.join([v for v in [vendor, product] if v])

    info['cpu_model'] = info['cpu_model'] or platform.processor() or 'unknown'
    info['os_version'] = info['os_version'] or platform.platform()
    info['cloud_vendor'] = info['cloud_vendor'] or 'unknown'
    return info


def get_cliproxy_process_usage():
    if not HAS_PSUTIL:
        return {'cpu_percent': 0.0, 'memory_bytes': 0, 'memory_percent': 0.0}
    target = CONFIG.get('cliproxy_service', 'cliproxy')
    cpu_percent = 0.0
    memory_bytes = 0
    memory_percent = 0.0
    try:
        for proc in psutil.process_iter(['name', 'cmdline', 'memory_info', 'memory_percent']):
            name = (proc.info.get('name') or '').lower()
            cmdline = ' '.join(proc.info.get('cmdline') or []).lower()
            if target in name or target in cmdline:
                try:
                    cpu_percent = proc.cpu_percent(interval=0.0)
                    mem_info = proc.info.get('memory_info')
                    if mem_info:
                        memory_bytes = getattr(mem_info, 'rss', 0)
                    memory_percent = _safe_float(proc.info.get('memory_percent', 0.0))
                    break
                except Exception:
                    continue
    except Exception:
        pass
    return {
        'cpu_percent': cpu_percent,
        'memory_bytes': memory_bytes,
        'memory_percent': memory_percent,
    }


def _normalize_quote_text(text):
    if not text:
        return text
    has_en = any('A' <= ch <= 'Z' or 'a' <= ch <= 'z' for ch in text)
    has_cn = any('\u4e00' <= ch <= '\u9fff' for ch in text)
    if has_en and has_cn and '（' in text and '）' in text:
        prefix, rest = text.split('（', 1)
        inside, suffix = rest.split('）', 1)
        prefix = prefix.strip()
        inside = inside.strip()
        if prefix and inside:
            prefix_has_en = any('A' <= ch <= 'Z' or 'a' <= ch <= 'z' for ch in prefix)
            inside_has_en = any('A' <= ch <= 'Z' or 'a' <= ch <= 'z' for ch in inside)
            if not prefix_has_en and inside_has_en:
                return f"{inside}（{prefix}）{suffix}".strip()
    return text.strip()


def load_quotes():
    path = CONFIG.get('quotes_path')
    if not path or not os.path.exists(path):
        return []
    quotes = []
    seen = set()
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        markers = list(re.finditer('出自：', content))
        if not markers:
            return []
        last_end = 0
        for idx, marker in enumerate(markers):
            quote = content[last_end:marker.start()].strip()
            next_marker_pos = markers[idx + 1].start() if idx + 1 < len(markers) else len(content)
            author_block = content[marker.end():next_marker_pos]
            author_line = author_block.split('\n', 1)[0].strip()
            if len(author_line) > 80:
                cut_positions = [author_line.find(p) for p in ['。', '！', '？', '!', '?', '；', ';']]
                cut_positions = [p for p in cut_positions if p != -1]
                if cut_positions:
                    author_line = author_line[:min(cut_positions)].strip()
            quote = _normalize_quote_text(quote)
            if quote and author_line:
                key = f"{quote}||{author_line}"
                if key not in seen:
                    seen.add(key)
                    quotes.append({'text': quote, 'author': author_line})
            last_end = marker.end() + len(author_line)
    except Exception as e:
        print(f"Warning: failed to load quotes: {e}")
    return quotes


def get_random_quote():
    cached = cache.get('quotes_cache', max_age=30)
    if cached is None:
        cached = load_quotes()
        cache.set('quotes_cache', cached)
    if not cached:
        return {'text': '欢迎回来，祝你今天高效完成任务。', 'author': '系统'}
    import random
    return random.choice(cached)

cache = CacheManager()

# ==================== 后台资源监控 ====================
class ResourceMonitor:
    """非阻塞资源监控器"""
    def __init__(self):
        self._cpu_percent = 0.0
        self._lock = threading.Lock()
        self._running = False

    def start(self):
        """启动后台监控线程"""
        if self._running:
            return
        self._running = True
        thread = threading.Thread(target=self._monitor_loop, daemon=True)
        thread.start()

    def _monitor_loop(self):
        """后台监控循环"""
        while self._running:
            try:
                if HAS_PSUTIL:
                    cpu = psutil.cpu_percent(interval=1)  # 1秒采样
                    with self._lock:
                        self._cpu_percent = cpu
            except:
                pass
            time.sleep(2)  # 每3秒更新一次(1秒采样+2秒等待)

    def get_cpu_percent(self):
        """获取CPU使用率（非阻塞）"""
        with self._lock:
            return self._cpu_percent

resource_monitor = ResourceMonitor()

def run_cmd(cmd, timeout=60, cwd=None):
    if not isinstance(cmd, (list, tuple)) or not cmd:
        raise ValueError('run_cmd expects a non-empty argument list')
    try:
        result = subprocess.run(
            list(cmd),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, '', 'Command timed out'
    except Exception as e:
        return False, '', str(e)


def is_linux():
    return platform.system().lower() == 'linux'


def command_available(command):
    return shutil.which(command) is not None


def _command_output_lines(cmd, timeout=10, cwd=None):
    success, stdout, _ = run_cmd(cmd, timeout=timeout, cwd=cwd)
    if not success:
        return []
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def _first_matching_line(lines, prefix):
    for line in lines:
        if line.startswith(prefix):
            return line
    return None


def _df_usage(path):
    lines = _command_output_lines(['df', path], timeout=5)
    if len(lines) < 2:
        return None
    parts = lines[-1].split()
    if len(parts) < 5:
        return None
    try:
        total = int(parts[1]) * 1024
        used = int(parts[2]) * 1024
        free = int(parts[3]) * 1024
    except Exception:
        return None
    return {
        'total': total,
        'used': used,
        'free': free,
        'percent': round(used / total * 100, 1) if total > 0 else 0,
    }


def _free_memory_usage():
    lines = _command_output_lines(['free', '-b'], timeout=5)
    mem_line = _first_matching_line(lines, 'Mem:')
    if not mem_line:
        return None
    parts = mem_line.split()
    if len(parts) < 3:
        return None
    try:
        total = int(parts[1])
        used = int(parts[2])
    except Exception:
        return None
    return {
        'total': total,
        'used': used,
        'available': total - used,
        'percent': round(used / total * 100, 1) if total > 0 else 0,
    }


def _cliproxy_pid():
    if not _is_local_api_host() or not command_available('pgrep'):
        return None
    lines = _command_output_lines(['pgrep', '-f', 'cliproxy -config'], timeout=5)
    return lines[0] if lines else None


def _service_control_supported():
    return _is_local_api_host() and is_linux() and command_available('systemctl')


def _service_api_reachable():
    try:
        resp = requests.get(_build_management_base_url(), timeout=2)
        return True, f'API reachable at {_api_host()}:{_api_port()} (HTTP {resp.status_code})'
    except requests.RequestException as exc:
        return False, f'API not reachable at {_api_host()}:{_api_port()} ({exc})'

def get_service_status(use_cache=True):
    """获取服务状态（带缓存）"""
    cache_key = 'service_status'
    if use_cache:
        cached = cache.get(cache_key, max_age=1)
        if cached:
            return cached

    status_out = ''
    pid_out = None
    is_running = False

    if _service_control_supported():
        success, stdout, _ = run_cmd(['systemctl', 'is-active', CONFIG['cliproxy_service']])
        is_running = success and stdout == 'active'
        _, systemctl_status, _ = run_cmd(
            ['systemctl', 'status', CONFIG['cliproxy_service'], '--no-pager', '-l'],
            timeout=10,
        )
        status_out = '\n'.join(systemctl_status.splitlines()[:20]).strip()
    else:
        is_running, status_out = _service_api_reachable()

    pid_out = _cliproxy_pid()

    memory = 'N/A'
    cpu = 'N/A'
    uptime = 'N/A'

    if not is_running and pid_out:
        is_running = True
        status_out = f'Process running (PID: {pid_out}) - detected locally'

    if pid_out:
        if HAS_PSUTIL:
            try:
                proc = psutil.Process(int(pid_out))
                memory = f'{proc.memory_info().rss / 1024 / 1024:.1f} MB'
                # 使用后台监控的CPU数据，避免阻塞
                cpu = f'{resource_monitor.get_cpu_percent():.1f}%'
                uptime_seconds = time.time() - proc.create_time()
                uptime = format_uptime(uptime_seconds)
            except:
                pass
        elif command_available('ps'):
            _, mem_out, _ = run_cmd(['ps', '-o', 'rss=', '-p', pid_out])
            if mem_out:
                try:
                    memory = f'{int(mem_out) / 1024:.1f} MB'
                except:
                    pass

    result = {
        'running': is_running,
        'status': 'running' if is_running else 'stopped',
        'pid': pid_out if pid_out else None,
        'memory': memory,
        'cpu': cpu,
        'uptime': uptime,
        'details': status_out
    }

    cache.set(cache_key, result)
    return result

def format_uptime(seconds):
    if seconds < 60:
        return f'{int(seconds)}秒'
    elif seconds < 3600:
        return f'{int(seconds/60)}分钟'
    elif seconds < 86400:
        hours = int(seconds / 3600)
        mins = int((seconds % 3600) / 60)
        return f'{hours}小时{mins}分'
    else:
        days = int(seconds / 86400)
        hours = int((seconds % 86400) / 3600)
        return f'{days}天{hours}小时'


def get_github_release_version():
    """从GitHub releases获取最新版本号（带缓存）"""
    cache_key = 'github_release'
    cached = cache.get(cache_key, max_age=300)
    if cached:
        return cached

    try:
        repo = 'router-for-me/CLIProxyAPI'
        api_url = f'https://api.github.com/repos/{repo}/releases/latest'
        html_latest_url = f'https://github.com/{repo}/releases/latest'

        def api_headers():
            headers = {
                'User-Agent': 'CLIProxyPanel',
                'Accept': 'application/vnd.github+json',
            }
            token = (os.environ.get('CLIPROXY_PANEL_GITHUB_TOKEN') or os.environ.get('GITHUB_TOKEN') or '').strip()
            if token:
                headers['Authorization'] = 'Bearer ' + token
            return headers

        try:
            resp = requests.get(api_url, headers=api_headers(), timeout=10)
            if resp.status_code == 200:
                data = resp.json() if resp.content else {}
                version = (data.get('tag_name') if isinstance(data, dict) else None) or 'unknown'
                cache.set(cache_key, version)
                return version
        except Exception as e:
            print(f'get_github_release_version api error: {e}')

        try:
            resp = requests.get(
                html_latest_url,
                headers={'User-Agent': 'CLIProxyPanel'},
                timeout=10,
                allow_redirects=False,
            )
            location = resp.headers.get('Location', '')
            match = re.search(r'/tag/(v[^/?#]+)', location)
            if not match:
                resp2 = requests.get(
                    html_latest_url,
                    headers={'User-Agent': 'CLIProxyPanel'},
                    timeout=10,
                    allow_redirects=True,
                )
                match = re.search(r'/tag/(v[^/?#]+)', str(getattr(resp2, 'url', '') or ''))
            if match:
                version = match.group(1)
                cache.set(cache_key, version)
                return version
        except Exception as e:
            print(f'get_github_release_version fallback error: {e}')
    except Exception as e:
        print(f'get_github_release_version error: {e}')
    return 'unknown'


def _normalize_release_version(version):
    if version is None:
        return ''
    raw = str(version).strip()
    if not raw:
        return ''
    if raw.lower() == 'unknown':
        return 'unknown'
    if raw.lower() == 'dev':
        return 'dev'
    if raw.startswith(('v', 'V')) and len(raw) > 1:
        return raw[1:]
    return raw


def _decorate_version_tag(version):
    raw = str(version).strip() if version is not None else ''
    if not raw:
        return raw
    if raw.lower() in {'unknown', 'dev'}:
        return raw.lower()
    normalized = _normalize_release_version(raw)
    if re.match(r'^\d+(\.\d+){1,3}$', normalized):
        return f'v{normalized}'
    return raw


def _cliproxy_management_get(path, timeout=6):
    try:
        return requests.get(
            f'{_build_management_base_url()}{path}',
            headers=_management_headers(),
            timeout=timeout,
        )
    except Exception:
        return None


def _get_local_version_from_management():
    cache_key = 'local_version_mgmt'
    cached = cache.get(cache_key, max_age=10)
    if cached:
        return cached

    resp = _cliproxy_management_get('/v0/management/config', timeout=5)
    if resp is None:
        return None
    try:
        if resp.status_code != 200:
            return None
        header_value = resp.headers.get('X-Cpa-Version') or resp.headers.get('X-CPA-VERSION')
        if not header_value:
            return None
        version = _decorate_version_tag(header_value)
        if _normalize_release_version(version) in {'unknown', 'dev', ''}:
            return None
        cache.set(cache_key, version)
        return version
    except Exception:
        return None


def _is_git_repo(path):
    try:
        return bool(path) and os.path.isdir(path) and os.path.isdir(os.path.join(path, '.git'))
    except Exception:
        return False


def _is_semver_like(version):
    normalized = _normalize_release_version(version)
    if not normalized or normalized in {'unknown', 'dev'}:
        return False
    return bool(re.match(r'^\d+(\.\d+){1,3}$', str(normalized)))


def _get_last_successful_release_version_from_history():
    try:
        path = UPDATE_HISTORY_PATH
        if not path or not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            history = json.load(f)
        if not isinstance(history, list):
            return None
        for entry in reversed(history):
            if not isinstance(entry, dict):
                continue
            if entry.get('success') is not True:
                continue
            version = entry.get('version')
            if _is_semver_like(version):
                return _decorate_version_tag(version)
    except Exception:
        return None
    return None


def get_management_version():
    cache_key = 'management_version'
    cached = cache.get(cache_key, max_age=30)
    if cached:
        return cached
    try:
        resp = requests.get(
            f'{_build_management_base_url()}/v0/management/version',
            headers=_management_headers(),
            timeout=5,
        )
        resp.raise_for_status()
        payload = resp.json()
        version = str(payload.get('version', '')).strip()
        if version:
            cache.set(cache_key, version)
            return version
    except Exception:
        pass
    return None

def get_local_version():
    """获取本地版本号"""
    cache_key = 'local_version'
    cached = cache.get(cache_key, max_age=30)
    if cached:
        return cached

    management_candidate = None
    management_version = _get_local_version_from_management() or get_management_version()
    if management_version:
        decorated = _decorate_version_tag(resolve_version_label(management_version))
        if _is_semver_like(decorated):
            cache.set(cache_key, decorated)
            return decorated
        management_candidate = decorated

    version_file = os.path.join(CONFIG['cliproxy_dir'], 'VERSION')
    if os.path.exists(version_file):
        try:
            with open(version_file, 'r') as f:
                version = f.read().strip()
                if version and _is_semver_like(version):
                    decorated = _decorate_version_tag(version)
                    cache.set(cache_key, decorated)
                    return decorated
        except:
            pass

    cliproxy_dir = CONFIG['cliproxy_dir']
    if _is_git_repo(cliproxy_dir) and command_available('git'):
        run_cmd(['git', 'fetch', '--tags'], cwd=cliproxy_dir, timeout=10)

        _, stdout, _ = run_cmd(['git', 'describe', '--tags', '--abbrev=0'], cwd=cliproxy_dir, timeout=10)
        if stdout and _is_semver_like(stdout):
            decorated = _decorate_version_tag(stdout)
            cache.set(cache_key, decorated)
            return decorated

        _, stdout, _ = run_cmd(['git', 'rev-parse', '--short', 'HEAD'], cwd=cliproxy_dir, timeout=10)
        if stdout:
            management_candidate = management_candidate or stdout

    history_version = _get_last_successful_release_version_from_history()
    if history_version:
        cache.set(cache_key, history_version)
        return history_version

    if management_candidate:
        cache.set(cache_key, management_candidate)
        return management_candidate

    cache.set(cache_key, 'unknown')
    return 'unknown'

def _reset_log_stats_state():
    with log_stats_lock:
        state['log_stats'] = {
            'initialized': False,
            'offset': 0,
            'last_size': 0,
            'last_mtime': None,
            'total': 0,
            'success': 0,
            'failed': 0,
            'last_time': None,
            'buffer': '',
            'base_total': 0,
            'base_success': 0,
            'base_failed': 0,
            'last_saved_ts': 0
        }
    save_log_stats_state(force=True)


def read_log_tail(log_file, max_lines=100, chunk_size=4096):
    """尾部读取日志，避免全量读取"""
    if not os.path.exists(log_file):
        return []
    if max_lines <= 0:
        return []

    try:
        with open(log_file, 'rb') as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            remaining = file_size
            data = b''
            while remaining > 0 and data.count(b'\n') <= max_lines:
                read_size = chunk_size if remaining >= chunk_size else remaining
                remaining -= read_size
                f.seek(remaining)
                data = f.read(read_size) + data
            text = data.decode('utf-8', errors='ignore')
            return text.splitlines()[-max_lines:]
    except Exception:
        return []


def get_request_count_from_logs():
    """从日志获取请求统计（增量解析）"""
    cache_key = 'request_count_logs'
    cached = cache.get(cache_key, max_age=2)
    if cached:
        return cached

    if not state.get('log_stats_loaded'):
        load_log_stats_state()

    log_file = CONFIG['cliproxy_log']
    if not os.path.exists(log_file):
        with log_stats_lock:
            log_state = state.get('log_stats', {})
            result = {
                'count': _safe_int(log_state.get('base_total', 0)),
                'last_time': log_state.get('last_time'),
                'success': _safe_int(log_state.get('base_success', 0)),
                'failed': _safe_int(log_state.get('base_failed', 0))
            }
        cache.set(cache_key, result)
        return result

    try:
        stat = os.stat(log_file)
        file_size = stat.st_size
        mtime = stat.st_mtime
    except Exception:
        result = {'count': 0, 'last_time': None, 'success': 0, 'failed': 0}
        cache.set(cache_key, result)
        return result

    needs_save = False
    with log_stats_lock:
        log_state = state.get('log_stats', {})
        initialized = log_state.get('initialized')
        last_size = log_state.get('last_size', 0)
        last_mtime = log_state.get('last_mtime')
        offset = log_state.get('offset', 0)

        rotated = False
        if not initialized:
            rotated = True
        elif file_size < last_size:
            rotated = True
        elif last_mtime and mtime < last_mtime:
            rotated = True

        if rotated:
            if log_state.get('initialized'):
                log_state['base_total'] = _safe_int(log_state.get('base_total', 0)) + _safe_int(log_state.get('total', 0))
                log_state['base_success'] = _safe_int(log_state.get('base_success', 0)) + _safe_int(log_state.get('success', 0))
                log_state['base_failed'] = _safe_int(log_state.get('base_failed', 0)) + _safe_int(log_state.get('failed', 0))
            offset = 0
            log_state['buffer'] = ''
            log_state['total'] = 0
            log_state['success'] = 0
            log_state['failed'] = 0
            log_state['last_time'] = None
        changed = rotated

        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                if offset:
                    f.seek(offset)
                new_data = f.read()
                new_offset = f.tell()
        except Exception:
            result = {'count': 0, 'last_time': None, 'success': 0, 'failed': 0}
            cache.set(cache_key, result)
            return result

        buffer = log_state.get('buffer', '') + new_data
        lines = buffer.splitlines(keepends=True)
        if lines and not lines[-1].endswith('\n'):
            log_state['buffer'] = lines[-1]
            lines = lines[:-1]
        else:
            log_state['buffer'] = ''

        for line in lines:
            if '[gin_logger.go' in line and ('POST' in line or 'GET' in line):
                if any(path in line for path in EXCLUDED_LOG_PATHS):
                    continue
                log_state['total'] += 1
                match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]', line)
                if match:
                    log_state['last_time'] = match.group(1)
                status_match = re.search(r'\s(\d{3})\s', line)
                if status_match:
                    code = int(status_match.group(1))
                    if 200 <= code < 300:
                        log_state['success'] += 1
                    elif code >= 400:
                        log_state['failed'] += 1
                changed = True

        log_state['initialized'] = True
        log_state['offset'] = new_offset
        log_state['last_size'] = file_size
        log_state['last_mtime'] = mtime
        state['log_stats'] = log_state

        needs_save = changed

        result = {
            'count': _safe_int(log_state.get('base_total', 0)) + _safe_int(log_state.get('total', 0)),
            'last_time': log_state['last_time'],
            'success': _safe_int(log_state.get('base_success', 0)) + _safe_int(log_state.get('success', 0)),
            'failed': _safe_int(log_state.get('base_failed', 0)) + _safe_int(log_state.get('failed', 0))
        }
        cache.set(cache_key, result)

    if needs_save:
        save_log_stats_state()
    log_stats_path = CONFIG.get('log_stats_path')
    if log_stats_path and not os.path.exists(log_stats_path):
        save_log_stats_state(force=True)
    return result


def resolve_version_label(version):
    if not version:
        return version
    version_str = str(version).strip()
    if not HASH_VERSION_PATTERN.match(version_str):
        return version_str
    if not command_available('git'):
        return version_str
    cliproxy_dir = CONFIG['cliproxy_dir']
    if not os.path.isdir(os.path.join(cliproxy_dir, '.git')):
        return version_str
    _, tags_out, _ = run_cmd(['git', 'tag', '--contains', version_str], cwd=cliproxy_dir, timeout=10)
    if not tags_out:
        return version_str
    tags = [t.strip() for t in tags_out.splitlines() if t.strip()]
    if not tags:
        return version_str
    def parse_version_key(tag):
        cleaned = tag.lstrip('vV')
        parts = re.split(r'[^0-9]+', cleaned)
        nums = [int(p) for p in parts if p.isdigit()]
        return nums or [0]
    tags.sort(key=parse_version_key)
    return tags[-1]


def get_current_commit():
    """获取当前commit（带缓存）"""
    cache_key = 'current_commit'
    cached = cache.get(cache_key, max_age=30)
    if cached:
        return cached
    if not command_available('git'):
        cache.set(cache_key, 'unknown')
        return 'unknown'
    cliproxy_dir = CONFIG['cliproxy_dir']
    if not os.path.isdir(os.path.join(cliproxy_dir, '.git')):
        cache.set(cache_key, 'unknown')
        return 'unknown'
    _, stdout, _ = run_cmd(['git', 'rev-parse', '--short', 'HEAD'], cwd=cliproxy_dir, timeout=10)
    result = stdout if stdout else 'unknown'
    cache.set(cache_key, result)
    return result

def get_latest_commit():
    """获取最新commit（带缓存，减少网络请求）"""
    cache_key = 'latest_commit'
    cached = cache.get(cache_key, max_age=120)  # 2分钟缓存
    if cached:
        return cached
    if not command_available('git'):
        cache.set(cache_key, 'unknown')
        return 'unknown'
    cliproxy_dir = CONFIG['cliproxy_dir']
    if not os.path.isdir(os.path.join(cliproxy_dir, '.git')):
        cache.set(cache_key, 'unknown')
        return 'unknown'
    run_cmd(['git', 'fetch', 'origin', 'main', '--quiet'], cwd=cliproxy_dir, timeout=10)
    _, stdout, _ = run_cmd(['git', 'rev-parse', '--short', 'origin/main'], cwd=cliproxy_dir, timeout=10)
    result = stdout if stdout else 'unknown'
    cache.set(cache_key, result)
    return result

def check_for_updates(use_cache=True):
    """检查更新（使用GitHub releases）"""
    cache_key = 'update_check'
    if use_cache:
        cached = cache.get(cache_key, max_age=60)
        if cached is not None:
            return cached

    current = get_local_version()
    latest = get_github_release_version()
    state['current_version'] = _decorate_version_tag(current)
    state['latest_version'] = _decorate_version_tag(latest)
    result = (
        _normalize_release_version(state['current_version']) not in {'', 'unknown'}
        and _normalize_release_version(state['latest_version']) not in {'', 'unknown'}
        and _normalize_release_version(state['current_version']) != _normalize_release_version(state['latest_version'])
    )
    cache.set(cache_key, result)
    return result


def get_idle_state(stats=None):
    if stats is None:
        stats = get_request_count_from_logs()

    last_time_str = stats.get('last_time')
    idle_threshold = max(0, int(CONFIG.get('idle_threshold_seconds', 0) or 0))
    result = {
        'is_idle': True,
        'last_request_time': last_time_str,
        'idle_threshold_seconds': idle_threshold,
        'idle_for_seconds': None,
        'idle_wait_seconds': 0,
    }

    if not last_time_str:
        return result

    try:
        last_time = datetime.strptime(last_time_str, '%Y-%m-%d %H:%M:%S')
        idle_seconds = max(0, int((datetime.now() - last_time).total_seconds()))
        idle_wait_seconds = max(0, idle_threshold - idle_seconds)
        result['idle_for_seconds'] = idle_seconds
        result['idle_wait_seconds'] = idle_wait_seconds
        result['is_idle'] = idle_wait_seconds == 0
        return result
    except Exception:
        return result


def is_idle():
    return get_idle_state().get('is_idle', True)


def get_auto_update_state(has_update=None, stats=None):
    if stats is None:
        stats = get_request_count_from_logs()
    if has_update is None:
        has_update = check_for_updates()

    idle_state = get_idle_state(stats)
    next_check_time = state.get('next_auto_update_check_time')
    next_check_in_seconds = None
    if next_check_time:
        try:
            next_check_dt = datetime.fromisoformat(next_check_time)
            next_check_in_seconds = max(0, int((next_check_dt - datetime.now()).total_seconds()))
        except Exception:
            next_check_in_seconds = None

    summary = '等待状态更新'
    phase = 'unknown'
    if not state.get('auto_update_enabled', False):
        phase = 'disabled'
        summary = '自动更新已关闭'
    elif state.get('update_in_progress'):
        phase = 'updating'
        summary = '正在执行自动更新'
    elif not has_update:
        phase = 'no_update'
        summary = '已是最新版本'
    elif not idle_state.get('is_idle'):
        phase = 'wait_idle'
        summary = f'还需空闲 {idle_state.get("idle_wait_seconds", 0)} 秒'
    elif next_check_in_seconds is not None and next_check_in_seconds > 0:
        phase = 'wait_check'
        summary = f'{next_check_in_seconds} 秒后进行下一次检查'
    else:
        phase = 'ready'
        summary = '已满足自动更新条件'

    return {
        'phase': phase,
        'summary': summary,
        'can_update_now': phase == 'ready',
        'has_update': has_update,
        'last_check_time': state.get('last_auto_update_check_time'),
        'next_check_time': next_check_time,
        'next_check_in_seconds': next_check_in_seconds,
        'idle': idle_state,
    }

def perform_update():
    if state['update_in_progress']:
        return False, 'Update already in progress'

    if not _service_control_supported():
        return False, {'success': False, 'message': 'Update only supported on Linux with systemd', 'details': []}

    state['update_in_progress'] = True
    result = {'success': False, 'message': '', 'details': []}
    cliproxy_dir = CONFIG['cliproxy_dir']

    try:
        result['details'].append('Stopping service...')
        run_cmd(['systemctl', 'stop', CONFIG['cliproxy_service']])
        time.sleep(2)

        result['details'].append('Pulling latest code...')
        success, fetch_stdout, fetch_stderr = run_cmd(['git', 'fetch', '--tags'], cwd=cliproxy_dir, timeout=30)
        if not success:
            result['message'] = f'Fetch failed: {fetch_stderr}'
            run_cmd(['systemctl', 'start', CONFIG['cliproxy_service']])
            return False, result
        success, stdout, stderr = run_cmd(['git', 'pull', 'origin', 'main'], cwd=cliproxy_dir, timeout=60)
        if not success:
            result['message'] = f'Pull failed: {stderr}'
            run_cmd(['systemctl', 'start', CONFIG['cliproxy_service']])
            return False, result
        if fetch_stdout:
            result['details'].append(fetch_stdout)
        if stdout:
            result['details'].append(stdout)

        result['details'].append('Rebuilding...')
        success, stdout, stderr = run_cmd(
            ['go', 'build', '-o', 'cliproxy', './cmd/server'],
            cwd=cliproxy_dir,
            timeout=300
        )
        if not success:
            result['message'] = f'Build failed: {stderr}'
            run_cmd(['systemctl', 'start', CONFIG['cliproxy_service']])
            return False, result
        result['details'].append('Build successful')

        result['details'].append('Starting service...')
        success, _, stderr = run_cmd(['systemctl', 'start', CONFIG['cliproxy_service']])
        if not success:
            result['message'] = f'Start failed: {stderr}'
            return False, result

        time.sleep(2)

        status = get_service_status()
        if not status['running']:
            result['message'] = 'Service not running after start'
            return False, result

        result['success'] = True
        result['message'] = 'Update successful'
        result['details'].append('Service is running')

        state['last_update_time'] = datetime.now().isoformat()
        state['last_update_result'] = result
        state['current_version'] = get_local_version()

        # 记录更新历史
        try:
            record_update_history(state['current_version'])
        except Exception as e:
            print(f"Failed to record update history: {e}")
        # 清除版本缓存
        try:
            cache.invalidate('local_version')
            cache.invalidate('management_version')
            cache.invalidate('github_release')
            cache.invalidate('update_check')
        except:
            pass

        return True, result

    except Exception as e:
        result['message'] = f'Update error: {str(e)}'
        run_cmd(['systemctl', 'start', CONFIG['cliproxy_service']])
        return False, result
    finally:
        state['update_in_progress'] = False

def auto_update_worker():
    while True:
        interval = max(60, int(CONFIG.get('auto_update_check_interval', 300) or 300))
        state['next_auto_update_check_time'] = (datetime.now() + timedelta(seconds=interval)).isoformat()
        time.sleep(interval)
        state['last_auto_update_check_time'] = datetime.now().isoformat()

        if not state['auto_update_enabled']:
            print(f'[{datetime.now()}] Auto-update skipped: disabled')
            continue

        if state['update_in_progress']:
            print(f'[{datetime.now()}] Auto-update skipped: update already in progress')
            continue

        try:
            has_update = check_for_updates()
            if not has_update:
                print(f'[{datetime.now()}] Auto-update check: no new release')
                continue

            idle_state = get_idle_state()
            if idle_state.get('is_idle'):
                print(f'[{datetime.now()}] Update detected and system idle, starting auto-update...')
                perform_update()
            else:
                print(
                    f'[{datetime.now()}] Auto-update skipped: busy, '
                    f'last request at {idle_state.get("last_request_time")}, '
                    f'threshold={CONFIG["idle_threshold_seconds"]}s'
                )
        except Exception as e:
            print(f'[{datetime.now()}] Auto-update check failed: {e}')

def parse_log_file(log_file, max_lines=100):
    """解析日志文件（优化：Python原生读取，提取实际时间戳）"""
    if not os.path.exists(log_file):
        return []

    # 匹配日志时间格式: [2026-01-18 23:48:53]
    time_pattern = re.compile(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]')

    try:
        lines = read_log_tail(log_file, max_lines=max_lines)

        logs = []
        for line in lines:
            line = line.strip()
            if line:
                # 尝试从日志中提取时间
                time_match = time_pattern.search(line)
                if time_match:
                    # 解析日志中的时间（服务器是UTC）
                    log_time_str = time_match.group(1)
                    try:
                        log_time = datetime.strptime(log_time_str, '%Y-%m-%d %H:%M:%S')
                        # 标记为UTC时间
                        time_iso = log_time.isoformat() + 'Z'
                    except:
                        time_iso = datetime.utcnow().isoformat() + 'Z'
                else:
                    time_iso = datetime.utcnow().isoformat() + 'Z'

                logs.append({
                    'time': time_iso,
                    'message': line[:500]
                })

        return logs[-50:]
    except:
        return []

def parse_request_logs(max_lines=200, use_cache=True):
    """解析 CLIProxy 请求日志（优化：预编译正则+缓存+原生读取）"""
    cache_key = 'request_logs'
    empty_stats = {'total': 0, 'success': 0, 'failed': 0}

    if use_cache:
        cached = cache.get(cache_key, max_age=2)
        if cached:
            return cached

    log_file = CONFIG['cliproxy_log']

    if not os.path.exists(log_file):
        return [], empty_stats

    try:
        lines = read_log_tail(log_file, max_lines=max_lines)

        logs = []
        # 使用预编译的正则表达式
        for line in lines:
            match = REQUEST_LOG_PATTERN.search(line)
            if match:
                timestamp, status, duration, client_ip, method, path = match.groups()
                client_ip = client_ip.strip()
                logs.append({
                    'time': timestamp,
                    'status': int(status),
                    'duration': duration,
                    'client': client_ip,
                    'method': method,
                    'path': path,
                    'message': f'{method} {path} - {status} ({duration})'
                })

        # 统计
        total = len(logs)
        success = sum(1 for l in logs if l['status'] < 400)
        failed = total - success

        result = (logs[-50:], {'total': total, 'success': success, 'failed': failed})
        cache.set(cache_key, result)
        return result
    except Exception as e:
        print(f'parse_request_logs error: {e}')
        return [], empty_stats

def get_paths_info():
    return {
        'config': CONFIG['cliproxy_config'],
        'auth_dir': CONFIG['auth_dir'],
        'binary': CONFIG['cliproxy_binary'],
        'logs': os.path.dirname(CONFIG['cliproxy_log']),
        'project_dir': CONFIG['cliproxy_dir']
    }

def load_cliproxy_config(use_cache=True):
    """加载CLIProxy配置文件（优化：带缓存）"""
    cache_key = 'cliproxy_config'
    if use_cache:
        cached = cache.get(cache_key, max_age=30)
        if cached:
            return cached

    config_path = CONFIG['cliproxy_config']
    if not os.path.exists(config_path):
        return None, 'Config file not found'

    if not HAS_YAML:
        # 没有yaml模块时返回原始内容
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                result = ({'_raw': f.read()}, None)
                cache.set(cache_key, result)
                return result
        except Exception as e:
            return None, str(e)

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            result = (config, None)
            cache.set(cache_key, result)
            return result
    except Exception as e:
        return None, str(e)

def validate_yaml_config(content):
    """验证YAML配置格式"""
    if not HAS_YAML:
        return {
            'valid': True,
            'errors': [],
            'warnings': ['pyyaml未安装，无法进行深度验证'],
            'config': None
        }

    try:
        config = yaml.safe_load(content)
        errors = []
        warnings = []

        # 基本结构检查
        if not isinstance(config, dict):
            errors.append('配置必须是一个字典/对象')
            return {'valid': False, 'errors': errors, 'warnings': warnings}

        # 检查必需字段
        required_fields = ['port']
        for field in required_fields:
            if field not in config:
                errors.append(f'缺少必需字段: {field}')

        # 检查端口
        if 'port' in config:
            port = config['port']
            if not isinstance(port, int) or port < 1 or port > 65535:
                errors.append('端口必须是1-65535之间的整数')

        # 检查providers
        if 'providers' in config:
            if not isinstance(config['providers'], list):
                errors.append('providers必须是一个数组')
            else:
                for i, provider in enumerate(config['providers']):
                    if not isinstance(provider, dict):
                        errors.append(f'provider[{i}] 必须是一个对象')
                        continue
                    if 'name' not in provider:
                        warnings.append(f'provider[{i}] 缺少name字段')
                    if 'type' not in provider:
                        warnings.append(f'provider[{i}] 缺少type字段')

        # 检查路由策略
        if 'routing' in config:
            valid_strategies = ['round-robin', 'fill-first']
            strategy = config['routing'].get('strategy', '')
            if strategy and strategy not in valid_strategies:
                warnings.append(f'未知的路由策略: {strategy}，有效值: {", ".join(valid_strategies)}')

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'config': config if len(errors) == 0 else None
        }
    except yaml.YAMLError as e:
        return {
            'valid': False,
            'errors': [f'YAML解析错误: {str(e)}'],
            'warnings': []
        }

def get_system_resources(use_cache=True):
    """获取系统资源（优化：非阻塞CPU+缓存）"""
    cache_key = 'system_resources'
    if use_cache:
        cached = cache.get(cache_key, max_age=2)
        if cached:
            return cached

    disk_path = CONFIG.get('disk_path') or '/'
    system_info = get_system_info()
    cliproxy_usage = get_cliproxy_process_usage()

    if not HAS_PSUTIL:
        # 没有psutil时使用命令行获取基本信息
        resources = {
            'cpu': {'percent': 0, 'cores': 1},
            'memory': {'total': 0, 'used': 0, 'percent': 0, 'available': 0},
            'disk': {'total': 0, 'used': 0, 'percent': 0, 'free': 0, 'path': disk_path},
            'network': {'bytes_sent': 0, 'bytes_recv': 0},
            'system': system_info,
            'cliproxy': cliproxy_usage,
            'timestamp': datetime.now().isoformat(),
            'limited': True
        }

        # 尝试获取内存信息（Linux）
        if is_linux() and command_available('free'):
            mem_usage = _free_memory_usage()
            if mem_usage:
                resources['memory']['total'] = mem_usage['total']
                resources['memory']['used'] = mem_usage['used']
                resources['memory']['available'] = mem_usage['available']
                resources['memory']['percent'] = mem_usage['percent']

        # 尝试获取磁盘信息（Linux）
        try:
            usage = shutil.disk_usage(disk_path)
            total = usage.total
            used = usage.used
            resources['disk']['total'] = total
            resources['disk']['used'] = used
            resources['disk']['free'] = usage.free
            resources['disk']['percent'] = round(used / total * 100, 1) if total > 0 else 0
        except Exception:
            if is_linux() and command_available('df'):
                disk_usage = _df_usage(disk_path)
                if disk_usage:
                    resources['disk']['total'] = disk_usage['total']
                    resources['disk']['used'] = disk_usage['used']
                    resources['disk']['free'] = disk_usage['free']
                    resources['disk']['percent'] = disk_usage['percent']

        cache.set(cache_key, resources)
        return resources

    try:
        # 使用后台监控的CPU数据，避免阻塞
        cpu_percent = resource_monitor.get_cpu_percent()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(disk_path)

        # 网络IO
        net_io = psutil.net_io_counters()

        # 获取更详细的CPU信息
        cpu_freq = psutil.cpu_freq()
        cpu_times = psutil.cpu_times_percent(interval=0)
        per_cpu = psutil.cpu_percent(percpu=True)

        # 获取更详细的内存信息
        swap = psutil.swap_memory()

        # 获取系统负载（Linux）
        try:
            load_avg = psutil.getloadavg()
        except:
            load_avg = (0, 0, 0)

        # 获取进程数
        try:
            process_count = len(psutil.pids())
        except:
            process_count = 0

        result = {
            'cpu': {
                'percent': cpu_percent,
                'cores': psutil.cpu_count(),
                'cores_logical': psutil.cpu_count(logical=True),
                'cores_physical': psutil.cpu_count(logical=False) or psutil.cpu_count(),
                'freq_current': cpu_freq.current if cpu_freq else 0,
                'freq_max': cpu_freq.max if cpu_freq and cpu_freq.max else 0,
                'per_cpu': per_cpu,
                'user': cpu_times.user if cpu_times else 0,
                'system': cpu_times.system if cpu_times else 0,
                'idle': cpu_times.idle if cpu_times else 0,
                'iowait': getattr(cpu_times, 'iowait', 0),
                'load_1m': round(load_avg[0], 2),
                'load_5m': round(load_avg[1], 2),
                'load_15m': round(load_avg[2], 2),
                'process_count': process_count,
            },
            'memory': {
                'total': memory.total,
                'used': memory.used,
                'percent': memory.percent,
                'available': memory.available,
                'free': memory.free,
                'cached': getattr(memory, 'cached', 0),
                'buffers': getattr(memory, 'buffers', 0),
                'shared': getattr(memory, 'shared', 0),
                'swap_total': swap.total,
                'swap_used': swap.used,
                'swap_percent': swap.percent,
                'swap_free': swap.free,
            },
            'disk': {
                'total': disk.total,
                'used': disk.used,
                'percent': round(disk.used / disk.total * 100, 1) if disk.total > 0 else 0,
                'free': disk.free,
                'path': disk_path,
            },
            'network': {
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
            },
            'system': system_info,
            'cliproxy': cliproxy_usage,
            'timestamp': datetime.now().isoformat()
        }
        cache.set(cache_key, result)
        return result
    except Exception as e:
        return {'error': str(e)}

def perform_health_check(use_cache=True):
    """执行健康检查（优化：带缓存）"""
    cache_key = 'health_check'
    if use_cache:
        cached = cache.get(cache_key, max_age=10)
        if cached:
            return cached

    results = {
        'timestamp': datetime.now().isoformat(),
        'checks': [],
        'checks_map': {},
        'overall': 'healthy'
    }

    # 1. 服务状态检查
    service = get_service_status()
    service_check = {
        'name': '服务状态',
        'status': 'pass' if service['running'] else 'fail',
        'message': '服务运行中' if service['running'] else '服务未运行',
        'details': service
    }
    results['checks'].append(service_check)
    results['checks_map']['service'] = service_check

    # 2. 配置文件检查
    config, error = load_cliproxy_config()
    config_check = {
        'name': '配置文件',
        'status': 'pass' if config else 'fail',
        'message': '配置文件有效' if config else f'配置错误: {error}'
    }
    results['checks'].append(config_check)
    results['checks_map']['config'] = config_check

    # 3. 磁盘空间检查
    if HAS_PSUTIL:
        try:
            disk = psutil.disk_usage('/')
            disk_ok = disk.percent < 90
            disk_check = {
                'name': '磁盘空间',
                'status': 'pass' if disk_ok else 'warn',
                'message': f'已使用 {disk.percent}%',
                'details': {'percent': disk.percent}
            }
            results['checks'].append(disk_check)
            results['checks_map']['disk'] = disk_check
        except:
            disk_check = {
                'name': '磁盘空间',
                'status': 'unknown',
                'message': '无法获取磁盘信息'
            }
            results['checks'].append(disk_check)
            results['checks_map']['disk'] = disk_check
    else:
        # 使用df命令获取磁盘信息（Linux）
        if is_linux() and command_available('df'):
            disk_usage = _df_usage(CONFIG.get('disk_path') or '/')
            if disk_usage:
                percent = disk_usage['percent']
                disk_ok = percent < 90
                disk_check = {
                    'name': '磁盘空间',
                    'status': 'pass' if disk_ok else 'warn',
                    'message': f'已使用 {percent}%',
                    'details': {'percent': percent}
                }
                results['checks'].append(disk_check)
                results['checks_map']['disk'] = disk_check
            else:
                disk_check = {
                    'name': '磁盘空间',
                    'status': 'unknown',
                    'message': '无法获取磁盘信息'
                }
                results['checks'].append(disk_check)
                results['checks_map']['disk'] = disk_check
        else:
            disk_check = {
                'name': '磁盘空间',
                'status': 'unknown',
                'message': '无法获取磁盘信息'
            }
            results['checks'].append(disk_check)
            results['checks_map']['disk'] = disk_check

    # 4. 内存检查
    if HAS_PSUTIL:
        try:
            memory = psutil.virtual_memory()
            mem_ok = memory.percent < 90
            memory_check = {
                'name': '内存使用',
                'status': 'pass' if mem_ok else 'warn',
                'message': f'已使用 {memory.percent}%',
                'details': {'percent': memory.percent}
            }
            results['checks'].append(memory_check)
            results['checks_map']['memory'] = memory_check
        except:
            memory_check = {
                'name': '内存使用',
                'status': 'unknown',
                'message': '无法获取内存信息'
            }
            results['checks'].append(memory_check)
            results['checks_map']['memory'] = memory_check
    else:
        # 使用free命令获取内存信息（Linux）
        if is_linux() and command_available('free'):
            mem_usage = _free_memory_usage()
            if mem_usage:
                percent = mem_usage['percent']
                mem_ok = percent < 90
                memory_check = {
                    'name': '内存使用',
                    'status': 'pass' if mem_ok else 'warn',
                    'message': f'已使用 {percent}%',
                    'details': {'percent': percent}
                }
                results['checks'].append(memory_check)
                results['checks_map']['memory'] = memory_check
            else:
                memory_check = {
                    'name': '内存使用',
                    'status': 'unknown',
                    'message': '无法获取内存信息'
                }
                results['checks'].append(memory_check)
                results['checks_map']['memory'] = memory_check
        else:
            memory_check = {
                'name': '内存使用',
                'status': 'unknown',
                'message': '无法获取内存信息'
            }
            results['checks'].append(memory_check)
            results['checks_map']['memory'] = memory_check

    # 5. 认证文件检查
    auth_dir = CONFIG['auth_dir']
    if os.path.exists(auth_dir):
        auth_files = [f for f in os.listdir(auth_dir) if os.path.isfile(os.path.join(auth_dir, f))]
        auth_check = {
            'name': '认证文件',
            'status': 'pass' if len(auth_files) > 0 else 'warn',
            'message': f'找到 {len(auth_files)} 个凭证文件',
            'details': {'count': len(auth_files)}
        }
        results['checks'].append(auth_check)
        results['checks_map']['auth'] = auth_check
    else:
        auth_check = {
            'name': '认证文件',
            'status': 'fail',
            'message': '认证目录不存在'
        }
        results['checks'].append(auth_check)
        results['checks_map']['auth'] = auth_check

    # 6. API端口检查
    try:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((_api_host(), _api_port()))
        sock.close()
        port_open = result == 0
        port_check = {
            'name': 'API端口',
            'status': 'pass' if port_open else 'fail',
            'message': f'端口 {_api_host()}:{_api_port()} {"开放" if port_open else "关闭"}'
        }
        results['checks'].append(port_check)
        results['checks_map']['api_port'] = port_check
    except:
        port_check = {
            'name': 'API端口',
            'status': 'unknown',
            'message': '无法检测端口状态'
        }
        results['checks'].append(port_check)
        results['checks_map']['api_port'] = port_check

    # 计算整体状态
    statuses = [c['status'] for c in results['checks']]
    if 'fail' in statuses:
        results['overall'] = 'unhealthy'
    elif 'warn' in statuses:
        results['overall'] = 'degraded'
    else:
        results['overall'] = 'healthy'

    state['last_health_check'] = results
    state['health_status'] = results['overall']

    cache.set(cache_key, results)
    return results

def get_models_from_config():
    """从配置中获取模型列表"""
    config, error = load_cliproxy_config()
    if not config:
        return [], error

    # 如果没有yaml，无法解析模型
    if '_raw' in config:
        return [], 'pyyaml未安装，无法解析模型列表'

    models = []
    providers = config.get('providers', [])

    for provider in providers:
        provider_name = provider.get('name', 'unknown')
        provider_models = provider.get('models', [])

        for model in provider_models:
            if isinstance(model, str):
                models.append({
                    'id': model,
                    'provider': provider_name,
                    'name': model
                })
            elif isinstance(model, dict):
                models.append({
                    'id': model.get('id', model.get('name', 'unknown')),
                    'provider': provider_name,
                    'name': model.get('name', model.get('id', 'unknown')),
                    'aliases': model.get('aliases', [])
                })

    return models, None


def sync_usage_state(use_cache=True):
    with usage_sync_lock:
        log_requests = get_request_count_from_logs()
        snapshot = fetch_usage_snapshot(use_cache=use_cache)
        token_totals, usage_reqs = aggregate_usage_snapshot(snapshot)
        pricing, pricing_meta = get_effective_pricing()
        billable_input_tokens = get_billable_input_tokens(token_totals)

        current_input = token_totals.get('input_tokens', 0)
        current_output = token_totals.get('output_tokens', 0)
        current_cached = token_totals.get('cached_tokens', 0)
        current_requests = usage_reqs.get('total_requests', 0) or 0
        current_success = usage_reqs.get('success', 0) or 0
        current_failure = usage_reqs.get('failure', 0) or 0

        last = state.get('last_snapshot', {})
        last_input = last.get('input_tokens', 0)
        last_output = last.get('output_tokens', 0)
        last_cached = last.get('cached_tokens', 0)
        last_requests = last.get('total_requests', 0)
        last_success = last.get('success', 0)
        last_failure = last.get('failure', 0)

        delta_input = current_input - last_input if current_input >= last_input else current_input
        delta_output = current_output - last_output if current_output >= last_output else current_output
        delta_cached = current_cached - last_cached if current_cached >= last_cached else current_cached
        delta_requests = current_requests - last_requests if current_requests >= last_requests else current_requests
        delta_success = current_success - last_success if current_success >= last_success else current_success
        delta_failure = current_failure - last_failure if current_failure >= last_failure else current_failure

        acc = state.get('accumulated_stats', {})
        acc['input_tokens'] = acc.get('input_tokens', 0) + delta_input
        acc['output_tokens'] = acc.get('output_tokens', 0) + delta_output
        acc['cached_tokens'] = acc.get('cached_tokens', 0) + delta_cached
        acc['total_requests'] = acc.get('total_requests', 0) + delta_requests
        acc['success'] = acc.get('success', 0) + delta_success
        acc['failure'] = acc.get('failure', 0) + delta_failure
        state['accumulated_stats'] = acc

        state['last_snapshot'] = {
            'input_tokens': current_input,
            'output_tokens': current_output,
            'cached_tokens': current_cached,
            'total_requests': current_requests,
            'success': current_success,
            'failure': current_failure,
        }

        display_input_tokens = acc['input_tokens']
        display_output_tokens = acc['output_tokens']
        display_cached_tokens = acc['cached_tokens']
        display_total_requests = acc['total_requests']
        display_success = acc['success']
        display_failure = acc['failure']
        display_total_tokens = display_input_tokens + display_output_tokens + display_cached_tokens
        display_billable_input_tokens = max(display_input_tokens - display_cached_tokens, 0)

        display_token_totals = {
            'input_tokens': display_input_tokens,
            'output_tokens': display_output_tokens,
            'cached_tokens': display_cached_tokens,
        }
        usage_costs = compute_usage_costs(display_token_totals, pricing)

        with stats_lock:
            state['stats']['input_tokens'] = display_input_tokens
            state['stats']['output_tokens'] = display_output_tokens
            state['stats']['cached_tokens'] = display_cached_tokens

        save_persistent_stats()

        final_count = display_total_requests if display_total_requests > 0 else log_requests.get('count', 0)
        final_success = display_success if display_success > 0 else log_requests.get('success', 0)
        final_failed = display_failure if display_failure > 0 else log_requests.get('failed', 0)

        return {
            'log_requests': log_requests,
            'pricing': pricing,
            'pricing_meta': pricing_meta,
            'pricing_basis': get_pricing_basis_info(),
            'usage_costs': usage_costs,
            'display': {
                'input_tokens': display_input_tokens,
                'billable_input_tokens': display_billable_input_tokens,
                'output_tokens': display_output_tokens,
                'cached_tokens': display_cached_tokens,
                'total_tokens': display_total_tokens,
                'count': final_count,
                'success': final_success,
                'failed': final_failed,
            },
            'snapshot': {
                'input_tokens': current_input,
                'billable_input_tokens': billable_input_tokens,
                'output_tokens': current_output,
                'cached_tokens': current_cached,
                'total_requests': current_requests,
            },
        }

# ==================== API 路由 ====================


@app.route('/healthz')
def healthz():
    return jsonify({'status': 'ok'})

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/status')
def api_status():
    service = get_service_status()
    has_update = check_for_updates()
    usage_state = sync_usage_state()
    log_requests = usage_state['log_requests']
    display = usage_state['display']
    pricing = usage_state['pricing']
    pricing_meta = usage_state['pricing_meta']
    pricing_basis = usage_state['pricing_basis']
    usage_costs = usage_state['usage_costs']
    idle_state = get_idle_state(log_requests)
    auto_update_state = get_auto_update_state(has_update=has_update, stats=log_requests)

    return jsonify({
        'panel': {
            'name': PANEL_NAME,
            'version': f'v{PANEL_VERSION}',
        },
        'service': service,
        'version': {
            'current': state['current_version'],
            'latest': state['latest_version'],
            'has_update': has_update
        },
        'requests': {
            'count': display['count'],
            'last_time': log_requests.get('last_time'),
            'success': display['success'],
            'failed': display['failed'],
            'is_idle': idle_state.get('is_idle', True),
            'input_tokens': display['input_tokens'],
            'billable_input_tokens': display['billable_input_tokens'],
            'output_tokens': display['output_tokens'],
            'cached_tokens': display['cached_tokens'],
            'total_tokens': display['total_tokens'],
        },
        'update': {
            'in_progress': state['update_in_progress'],
            'last_time': state['last_update_time'],
            'last_result': state['last_update_result'],
            'auto_enabled': state['auto_update_enabled'],
            'status': auto_update_state,
        },
        'config': {
            'idle_threshold': CONFIG['idle_threshold_seconds'],
            'check_interval': CONFIG['auto_update_check_interval'],
            'write_enabled': is_config_write_enabled(),
        },
        'pricing': pricing,
        'pricing_basis': pricing_basis,
        'pricing_meta': pricing_meta,
        'usage_costs': usage_costs,
        'paths': get_paths_info(),
        'health': state['health_status']
    })


@app.route('/api/usage/analytics')
def api_usage_analytics():
    analytics = build_usage_analytics()
    return jsonify(analytics)

@app.route('/api/logs')
def api_logs():
    logs = parse_log_file(CONFIG['cliproxy_log'])
    return jsonify({'logs': logs, 'count': len(logs)})

@app.route('/api/cliproxy-logs')
def api_cliproxy_logs():
    """获取 CLIProxy 完整日志"""
    logs = parse_log_file(CONFIG['cliproxy_log'], max_lines=150)
    if len(logs) < 10:
        stderr_logs = parse_log_file(CONFIG['cliproxy_stderr'], max_lines=50)
        logs = logs + stderr_logs
    return jsonify({'logs': logs[-50:], 'count': len(logs)})

@app.route('/api/cliproxy-logs/clear', methods=['POST'])
def api_clear_cliproxy_logs():
    """清空 CLIProxy 日志"""
    log_files = [CONFIG.get('cliproxy_log'), CONFIG.get('cliproxy_stderr')]
    cleared = False
    errors = []

    for log_file in log_files:
        if not log_file or not os.path.exists(log_file):
            continue
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write('')
            cleared = True
        except Exception as e:
            errors.append(f"{log_file}: {e}")

    _reset_log_stats_state()
    try:
        cache.invalidate('request_count_logs')
    except:
        pass

    if errors:
        return jsonify({'success': False, 'message': '清空失败', 'errors': errors}), 500
    if not cleared:
        return jsonify({'success': True, 'message': '暂无日志可清空'})
    return jsonify({'success': True, 'message': '日志已清空'})

@app.route('/api/request-logs')
def api_request_logs():
    """获取解析后的 HTTP 请求日志"""
    logs, stats = parse_request_logs(max_lines=300)
    return jsonify({
        'logs': logs,
        'count': len(logs),
        'stats': stats
    })

@app.route('/api/paths')
def api_paths():
    return jsonify(get_paths_info())


@app.route('/api/update-history')
def api_update_history():
    """获取更新历史"""
    history_file = UPDATE_HISTORY_PATH
    try:
        os.makedirs(os.path.dirname(history_file), exist_ok=True)
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
        else:
            history = []

        # 计算每次更新距今多少小时
        now = datetime.utcnow()
        for entry in history:
            try:
                update_time = datetime.strptime(entry['time'], '%Y-%m-%d %H:%M:%S')
                hours_ago = (now - update_time).total_seconds() / 3600
                entry['hours_ago'] = round(hours_ago, 1)
            except:
                entry['hours_ago'] = None
            entry['version'] = resolve_version_label(entry.get('version'))

        return jsonify({
            'success': True,
            'history': history[-10:]  # 返回最近10条
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def record_update_history(version, success=True):
    """记录更新历史"""
    history_file = UPDATE_HISTORY_PATH
    try:
        os.makedirs(os.path.dirname(history_file), exist_ok=True)
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
        else:
            history = []

        history.append({
            'version': version,
            'time': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
            'success': success
        })

        # 只保留最近50条
        history = history[-50:]

        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

        return True
    except Exception as e:
        print(f"Error recording update history: {e}")
        return False

@app.route('/api/update', methods=['POST'])
def api_update():
    force = request.json.get('force', False) if request.json else False

    if not force and not is_idle():
        return jsonify({
            'success': False,
            'message': 'System has active requests. Wait for idle or use force update.'
        }), 400

    if state['update_in_progress']:
        return jsonify({'success': False, 'message': 'Update already in progress'}), 400

    def do_update():
        perform_update()

    thread = threading.Thread(target=do_update)
    thread.start()

    return jsonify({'success': True, 'message': 'Update started, please refresh to check status'})

@app.route('/api/service/<action>', methods=['POST'])
def api_service(action):
    if action not in ['start', 'stop', 'restart']:
        return jsonify({'success': False, 'message': 'Invalid action'}), 400

    if not _service_control_supported():
        return jsonify({'success': False, 'message': 'Service control not supported on this platform'}), 400

    success, stdout, stderr = run_cmd(['systemctl', action, CONFIG['cliproxy_service']])
    time.sleep(2)

    status = get_service_status()
    return jsonify({'success': success, 'message': stdout or stderr, 'status': status})

@app.route('/api/config/auto-update', methods=['POST'])
def api_toggle_auto_update():
    data = request.json or {}
    enabled_raw = data.get('enabled', not state['auto_update_enabled'])
    enabled = enabled_raw if isinstance(enabled_raw, bool) else _parse_bool(enabled_raw)
    state['auto_update_enabled'] = enabled
    CONFIG['auto_update_enabled'] = enabled
    _update_dotenv_values({'auto_update_enabled': enabled})
    return jsonify({'success': True, 'auto_update_enabled': state['auto_update_enabled']})

@app.route('/api/config/idle-threshold', methods=['POST'])
def api_set_idle_threshold():
    data = request.json or {}
    threshold = data.get('threshold', 60)

    if not isinstance(threshold, int) or threshold < 10:
        return jsonify({'success': False, 'message': 'Threshold must be integer >= 10'}), 400

    CONFIG['idle_threshold_seconds'] = threshold
    _update_dotenv_values({'idle_threshold_seconds': CONFIG['idle_threshold_seconds']})
    return jsonify({'success': True, 'idle_threshold': CONFIG['idle_threshold_seconds']})

@app.route('/api/config/check-interval', methods=['POST'])
def api_set_check_interval():
    """设置自动更新检查间隔"""
    data = request.json or {}
    interval = data.get('interval', 300)
    if not isinstance(interval, (int, float)) or interval < 60:
        return jsonify({'success': False, 'error': 'Invalid interval (min 60 seconds)'}), 400
    CONFIG['auto_update_check_interval'] = int(interval)
    _update_dotenv_values({'auto_update_check_interval': CONFIG['auto_update_check_interval']})
    return jsonify({'success': True, 'check_interval': CONFIG['auto_update_check_interval']})


@app.route('/api/pricing', methods=['GET', 'POST'])
def api_pricing():
    if request.method == 'POST':
        data = request.json or {}
        input_price = _parse_float(data.get('input', CONFIG.get('pricing_input', 0.0)))
        output_price = _parse_float(data.get('output', CONFIG.get('pricing_output', 0.0)))
        cache_price = _parse_float(data.get('cache', CONFIG.get('pricing_cache', 0.0)))
        CONFIG['pricing_input'] = input_price
        CONFIG['pricing_output'] = output_price
        CONFIG['pricing_cache'] = cache_price
        _update_dotenv_values({
            'pricing_input': input_price,
            'pricing_output': output_price,
            'pricing_cache': cache_price,
        })
        cache.invalidate('usage_analytics_v2')
        effective, pricing_meta = get_effective_pricing()
        return jsonify({
            'success': True,
            'pricing': {'input': input_price, 'output': output_price, 'cache': cache_price},
            'effective_pricing': effective,
            'pricing_basis': get_pricing_basis_info(),
            'pricing_meta': pricing_meta,
        })

    effective, pricing_meta = get_effective_pricing()
    return jsonify({
        'success': True,
        'pricing': {
            'input': _safe_float(CONFIG.get('pricing_input', 0.0)),
            'output': _safe_float(CONFIG.get('pricing_output', 0.0)),
            'cache': _safe_float(CONFIG.get('pricing_cache', 0.0)),
        },
        'effective_pricing': effective,
        'pricing_basis': get_pricing_basis_info(),
        'pricing_meta': pricing_meta,
    })


@app.route('/api/config/pricing-auto', methods=['POST'])
def api_set_pricing_auto():
    data = request.json or {}
    enabled_raw = data.get('enabled', CONFIG.get('pricing_auto_enabled', True))
    enabled = enabled_raw if isinstance(enabled_raw, bool) else _parse_bool(enabled_raw)
    CONFIG['pricing_auto_enabled'] = enabled
    _update_dotenv_values({'pricing_auto_enabled': enabled})
    cache.invalidate('usage_analytics_v2')
    effective, pricing_meta = get_effective_pricing()
    return jsonify({
        'success': True,
        'pricing_auto_enabled': enabled,
        'effective_pricing': effective,
        'pricing_basis': get_pricing_basis_info(),
        'pricing_meta': pricing_meta,
    })


@app.route('/api/quote', methods=['GET', 'POST'])
def api_quote():
    if request.method == 'POST':
        data = request.json or {}
        line = (data.get('line') or '').strip()
        if not line or '出自：' not in line:
            return jsonify({'success': False, 'error': '格式错误，请使用“内容 出自：作者”'}), 400
        path = CONFIG.get('quotes_path')
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'a', encoding='utf-8') as f:
                if not line.endswith('\n'):
                    line = line + '\n'
                f.write(line)
            cache.set('quotes_cache', load_quotes())
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    quote = get_random_quote()
    return jsonify({'text': quote.get('text', ''), 'author': quote.get('author', '')})

@app.route('/api/record-request', methods=['POST'])
def api_record_request():
    with log_lock:
        state['last_request_time'] = time.time()
        state['request_count'] += 1

        data = request.json or {}
        state['request_log'].append({
            'time': datetime.now().isoformat(),
            'model': data.get('model', 'unknown'),
            'client': request.remote_addr,
            'status': data.get('status', 'unknown'),
            'response_time': data.get('response_time', 0)
        })

        if len(state['request_log']) > 100:
            state['request_log'] = state['request_log'][-100:]

        # 更新统计
        with stats_lock:
            state['stats']['total_requests'] += 1
            if data.get('status') == 'success':
                state['stats']['successful_requests'] += 1
            else:
                state['stats']['failed_requests'] += 1

            model = data.get('model', 'unknown')
            state['stats']['model_usage'][model] = state['stats']['model_usage'].get(model, 0) + 1

    # 触发持久化保存（后台线程会定期保存，这里只是触发检查）
    save_persistent_stats()

    return jsonify({'success': True})

@app.route('/api/request-history')
def api_request_history():
    return jsonify({
        'history': state['request_log'][-50:],
        'total_count': state['request_count'],
        'last_time': state['last_request_time']
    })

@app.route('/api/check-update')
def api_check_update():
    has_update = check_for_updates()
    return jsonify({
        'has_update': has_update,
        'current': state['current_version'],
        'latest': state['latest_version']
    })

@app.route('/api/auth-files')
def api_auth_files():
    runtime_files = fetch_management_auth_files()
    if runtime_files:
        files = []
        for item in runtime_files:
            record = dict(item)
            record['label'] = _auth_display_label(item)
            files.append(record)
        return jsonify({
            'files': files,
            'source': 'management',
            'path': None,
        })

    auth_dir = CONFIG['auth_dir']
    if not os.path.exists(auth_dir):
        return jsonify({'files': [], 'error': 'Auth directory not found', 'source': 'filesystem'})

    try:
        files = []
        for f in os.listdir(auth_dir):
            filepath = os.path.join(auth_dir, f)
            if os.path.isfile(filepath):
                stat = os.stat(filepath)
                files.append({
                    'name': f,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
        return jsonify({'files': files, 'path': auth_dir, 'source': 'filesystem'})
    except Exception as e:
        return jsonify({'files': [], 'error': str(e), 'source': 'filesystem'})

@app.route('/api/config', methods=['GET'])
def api_get_config():
    config_path = CONFIG['cliproxy_config']
    if not os.path.exists(config_path):
        return jsonify({'success': False, 'error': 'Config file not found', 'path': config_path}), 404

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({'success': True, 'content': content, 'path': config_path})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config', methods=['POST'])
def api_upload_config():
    if not is_config_write_enabled():
        return config_write_blocked_response()

    config_path = CONFIG['cliproxy_config']

    if 'file' in request.files:
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        try:
            content = file.read().decode('utf-8')
            validation = validate_yaml_config(content)
            if not validation.get('valid'):
                return jsonify({'success': False, 'error': validation.get('errors', ['Invalid config'])[0]}), 400
            file.stream.seek(0)
            backup_path = config_path + '.bak'
            if os.path.exists(config_path):
                import shutil
                shutil.copy2(config_path, backup_path)

            file.save(config_path)
            cache.invalidate('cliproxy_config')
            return jsonify({
                'success': True,
                'message': 'Config uploaded successfully',
                'path': config_path,
                'backup': backup_path
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    data = request.json
    if data and 'content' in data:
        try:
            validation = validate_yaml_config(data['content'])
            if not validation.get('valid'):
                return jsonify({'success': False, 'error': validation.get('errors', ['Invalid config'])[0]}), 400
            backup_path = config_path + '.bak'
            if os.path.exists(config_path):
                import shutil
                shutil.copy2(config_path, backup_path)

            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(data['content'])

            cache.invalidate('cliproxy_config')
            return jsonify({
                'success': True,
                'message': 'Config saved successfully',
                'path': config_path,
                'backup': backup_path
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    return jsonify({'success': False, 'error': 'No file or content provided'}), 400

@app.route('/api/config/restore', methods=['POST'])
def api_restore_config():
    if not is_config_write_enabled():
        return config_write_blocked_response()

    config_path = CONFIG['cliproxy_config']
    backup_path = config_path + '.bak'

    if not os.path.exists(backup_path):
        return jsonify({'success': False, 'error': 'No backup file found'}), 404

    try:
        import shutil
        shutil.copy2(backup_path, config_path)
        cache.invalidate('cliproxy_config')
        return jsonify({
            'success': True,
            'message': 'Config restored from backup',
            'path': config_path
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== 新增API ====================

@app.route('/api/config/validate', methods=['POST'])
def api_validate_config():
    """验证配置文件格式"""
    data = request.json or {}
    content = data.get('content', '')

    if not content:
        # 验证当前配置文件
        config_path = CONFIG['cliproxy_config']
        if not os.path.exists(config_path):
            return jsonify({'success': False, 'error': 'Config file not found'}), 404
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()

    result = validate_yaml_config(content)
    return jsonify(result)

@app.route('/api/config/reload', methods=['POST'])
def api_reload_config():
    """重新加载配置（发送SIGHUP信号）"""
    if not _is_local_api_host():
        return jsonify({'success': False, 'message': 'Reload only supported for local CLIProxy instances'}), 400

    if not command_available('pgrep'):
        return jsonify({'success': False, 'message': 'Reload not supported on this platform'}), 400

    pid_out = _cliproxy_pid()

    if not pid_out:
        return jsonify({'success': False, 'message': '服务未运行'}), 400

    try:
        if command_available('kill'):
            success, stdout, stderr = run_cmd(['kill', '-HUP', pid_out])
        else:
            success, stdout, stderr = (False, '', 'kill not available')

        if success:
            return jsonify({'success': True, 'message': '配置重载信号已发送'})
        else:
            # 如果SIGHUP不支持，尝试重启服务（Linux/systemd）
            if _service_control_supported():
                run_cmd(['systemctl', 'restart', CONFIG['cliproxy_service']])
                time.sleep(2)
                status = get_service_status()
                return jsonify({
                    'success': status['running'],
                    'message': '已重启服务以应用配置',
                    'status': status
                })

            return jsonify({'success': False, 'message': 'Reload not supported on this platform'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config/routing', methods=['GET'])
def api_get_routing():
    """获取当前路由策略"""
    config, error = load_cliproxy_config()
    if not config:
        return jsonify({'success': False, 'error': error}), 500

    # 如果没有yaml，返回默认值
    if '_raw' in config:
        return jsonify({
            'success': True,
            'strategy': 'round-robin',
            'available': ['round-robin', 'fill-first'],
            'note': 'pyyaml未安装，无法解析配置'
        })

    routing = config.get('routing', {})
    return jsonify({
        'success': True,
        'strategy': routing.get('strategy', 'round-robin'),
        'available': ['round-robin', 'fill-first']
    })

@app.route('/api/config/routing', methods=['POST'])
def api_set_routing():
    """设置路由策略"""
    if not is_config_write_enabled():
        return config_write_blocked_response()

    if not HAS_YAML:
        return jsonify({'success': False, 'error': 'pyyaml未安装，无法修改配置'}), 400

    data = request.json or {}
    strategy = data.get('strategy')

    valid_strategies = ['round-robin', 'fill-first']
    if strategy not in valid_strategies:
        return jsonify({'success': False, 'error': f'无效的策略，可选: {", ".join(valid_strategies)}'}), 400

    config_path = CONFIG['cliproxy_config']
    config, error = load_cliproxy_config()
    if not config:
        return jsonify({'success': False, 'error': error}), 500

    # 更新路由策略
    if 'routing' not in config:
        config['routing'] = {}
    config['routing']['strategy'] = strategy

    try:
        # 备份
        import shutil
        backup_path = config_path + '.bak'
        if os.path.exists(config_path):
            shutil.copy2(config_path, backup_path)

        # 写入新配置
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

        cache.invalidate('cliproxy_config')
        return jsonify({'success': True, 'message': f'路由策略已设置为 {strategy}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/health')
def api_health():
    """健康检查"""
    results = perform_health_check()
    return jsonify(results)

@app.route('/api/resources')
def api_resources():
    """获取系统资源"""
    get_request_count_from_logs()
    resources = get_system_resources()
    return jsonify(resources)

@app.route('/api/stats')
def api_stats():
    """获取统计数据"""
    with stats_lock:
        stats = {
            'total_requests': state['stats']['total_requests'],
            'successful_requests': state['stats']['successful_requests'],
            'failed_requests': state['stats']['failed_requests'],
            'success_rate': (state['stats']['successful_requests'] / max(state['stats']['total_requests'], 1)) * 100,
            'model_usage': dict(state['stats']['model_usage']),
            'error_types': dict(state['stats']['error_types']),
            'request_log': state['request_log'][-20:],
        }

    return jsonify(stats)

@app.route('/api/stats/clear', methods=['POST'])
def api_clear_stats():
    """清空请求统计（清空累计值，更新快照为当前值）"""
    # 先获取当前 CLIProxyAPI 的值，作为新的快照起点
    snapshot = fetch_usage_snapshot(use_cache=False)
    token_totals, usage_reqs = aggregate_usage_snapshot(snapshot)

    # 更新快照为当前值（这样下次计算增量时从0开始）
    state['last_snapshot'] = {
        'input_tokens': token_totals.get('input_tokens', 0),
        'output_tokens': token_totals.get('output_tokens', 0),
        'cached_tokens': token_totals.get('cached_tokens', 0),
        'total_requests': usage_reqs.get('total_requests', 0) or 0,
        'success': usage_reqs.get('success', 0) or 0,
        'failure': usage_reqs.get('failure', 0) or 0,
    }

    # 清空累计统计值
    state['accumulated_stats'] = {
        'input_tokens': 0,
        'output_tokens': 0,
        'cached_tokens': 0,
        'total_requests': 0,
        'success': 0,
        'failure': 0,
    }

    with stats_lock:
        state['stats']['total_requests'] = 0
        state['stats']['successful_requests'] = 0
        state['stats']['failed_requests'] = 0
        state['stats']['input_tokens'] = 0
        state['stats']['output_tokens'] = 0
        state['stats']['cached_tokens'] = 0
        state['stats']['model_usage'].clear()
        state['stats']['error_types'].clear()
        state['request_log'].clear()
        state['request_count'] = 0

    # 保存清空后的状态到持久化文件
    save_persistent_stats(force=True)

    # 清空 usage_snapshot.json
    usage_path = CONFIG.get('usage_snapshot_path')
    if usage_path and os.path.exists(usage_path):
        try:
            os.remove(usage_path)
        except Exception as e:
            print(f"Error removing usage snapshot: {e}")

    # 清除所有缓存
    try:
        cache.invalidate()
    except Exception:
        pass

    # 清空日志文件中的请求记录
    log_file = CONFIG['cliproxy_log']
    try:
        if os.path.exists(log_file):
            # 备份并清空日志
            backup_file = log_file + '.bak'
            import shutil
            shutil.copy2(log_file, backup_file)
            # 清空日志文件
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write('')
            _reset_log_stats_state()
    except Exception as e:
        print(f"Error clearing log file: {e}")

    return jsonify({'success': True, 'message': '统计数据已清空'})

@app.route('/api/models')
def api_models():
    """获取模型列表"""
    base_url = _build_management_base_url()
    api_key = CONFIG.get('models_api_key', '')

    models_url = f'{base_url}/v1/models'
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'

    try:
        resp = requests.get(models_url, headers=headers, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
        models = payload.get('data', []) if isinstance(payload, dict) else []
        return jsonify({'success': True, 'models': models, 'count': len(models)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'models': []}), 502

@app.route('/api/test/connection', methods=['POST'])
def api_test_connection():
    """测试连接"""
    data = request.json or {}
    target = data.get('target', 'api')
    if target not in {'api', 'internet', 'all'}:
        return jsonify({'success': False, 'error': 'Invalid target'}), 400

    results = {'success': True, 'tests': []}

    if target in ['api', 'all']:
        # 测试API端口
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            start = time.time()
            result = sock.connect_ex((_api_host(), _api_port()))
            latency = (time.time() - start) * 1000
            sock.close()

            results['tests'].append({
                'name': 'API端口',
                'success': result == 0,
                'latency': f'{latency:.1f}ms' if result == 0 else None,
                'message': f'端口 {_api_host()}:{_api_port()} 正常' if result == 0 else '连接失败'
            })
        except Exception as e:
            results['tests'].append({
                'name': 'API端口',
                'success': False,
                'message': str(e)
            })

    if target in ['internet', 'all']:
        # 测试外网连接
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            start = time.time()
            result = sock.connect_ex(('8.8.8.8', 53))
            latency = (time.time() - start) * 1000
            sock.close()

            results['tests'].append({
                'name': '外网连接',
                'success': result == 0,
                'latency': f'{latency:.1f}ms' if result == 0 else None,
                'message': '网络正常' if result == 0 else '无法连接外网'
            })
        except Exception as e:
            results['tests'].append({
                'name': '外网连接',
                'success': False,
                'message': str(e)
            })

    # 整体结果
    results['success'] = all(t['success'] for t in results['tests'])

    return jsonify(results)

@app.route('/api/test/api', methods=['POST'])
def api_test_api():
    """API测试器"""
    data = request.json or {}
    endpoint = data.get('endpoint', '/v1/models')
    method = data.get('method', 'GET')
    body = data.get('body')
    headers = data.get('headers', {})
    if not isinstance(endpoint, str) or not endpoint.strip():
        return jsonify({'success': False, 'error': 'Endpoint is required'}), 400
    if headers is None:
        headers = {}
    if not isinstance(headers, dict):
        return jsonify({'success': False, 'error': 'Headers must be an object'}), 400
    if not endpoint.startswith('/'):
        endpoint = '/' + endpoint

    method = str(method or 'GET').upper()
    if method not in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE'}:
        return jsonify({'success': False, 'error': 'Unsupported HTTP method'}), 400

    base_url = _build_management_base_url()
    url = base_url + endpoint

    try:
        import urllib.request
        import urllib.error

        start_time = time.time()

        req_data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=req_data, method=method)

        for key, value in headers.items():
            req.add_header(key, value)

        if body:
            req.add_header('Content-Type', 'application/json')

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                response_time = (time.time() - start_time) * 1000
                response_body = response.read().decode('utf-8')

                try:
                    response_json = json.loads(response_body)
                except:
                    response_json = None

                return jsonify({
                    'success': True,
                    'status': response.status,
                    'response_time': f'{response_time:.1f}ms',
                    'headers': dict(response.headers),
                    'body': response_json if response_json else response_body[:2000]
                })
        except urllib.error.HTTPError as e:
            response_time = (time.time() - start_time) * 1000
            return jsonify({
                'success': False,
                'status': e.code,
                'response_time': f'{response_time:.1f}ms',
                'error': str(e),
                'body': e.read().decode('utf-8')[:1000] if e.fp else None
            })
        except urllib.error.URLError as e:
            return jsonify({
                'success': False,
                'error': f'连接失败: {str(e.reason)}'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/export/<data_type>')
def api_export(data_type):
    """数据导出"""
    if data_type == 'logs':
        logs = state['request_log']
        content = json.dumps(logs, indent=2, ensure_ascii=False)
        return Response(
            content,
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename=logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'}
        )

    elif data_type == 'stats':
        with stats_lock:
            stats = {
                'exported_at': datetime.now().isoformat(),
                'total_requests': state['stats']['total_requests'],
                'successful_requests': state['stats']['successful_requests'],
                'failed_requests': state['stats']['failed_requests'],
                'model_usage': dict(state['stats']['model_usage']),
            }
        content = json.dumps(stats, indent=2, ensure_ascii=False)
        return Response(
            content,
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename=stats_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'}
        )

    elif data_type == 'config':
        config_path = CONFIG['cliproxy_config']
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return Response(
                content,
                mimetype='application/x-yaml',
                headers={'Content-Disposition': f'attachment; filename=config_{datetime.now().strftime("%Y%m%d_%H%M%S")}.yaml'}
            )
        return jsonify({'error': 'Config not found'}), 404

    elif data_type == 'health':
        health = perform_health_check()
        content = json.dumps(health, indent=2, ensure_ascii=False)
        return Response(
            content,
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename=health_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'}
        )

    return jsonify({'error': 'Unknown data type'}), 400

# 启动后台任务
def background_tasks():
    """后台任务：定期健康检查和资源监控"""
    while True:
        try:
            perform_health_check()
            get_request_count_from_logs()
            sync_usage_state(use_cache=False)
        except Exception as e:
            print(f'[{datetime.now()}] Health check failed: {e}')
        time.sleep(60)

if __name__ == '__main__':
    from waitress import serve

    state['current_version'] = get_local_version()

    # 确保 data 目录存在
    os.makedirs(DATA_DIR, exist_ok=True)

    # 加载持久化统计数据（最重要的，放在最前面）
    load_persistent_stats()
    # 立即保存一次，确保文件存在
    save_persistent_stats(force=True)

    load_log_stats_state()
    try:
        get_request_count_from_logs()
        save_log_stats_state(force=True)
    except Exception as e:
        print(f"Warning: failed to initialize log stats: {e}")

    # 启动资源监控器（非阻塞CPU监控）
    resource_monitor.start()

    # 启动自动更新线程
    auto_thread = threading.Thread(target=auto_update_worker, daemon=True)
    auto_thread.start()

    # 启动后台任务线程
    bg_thread = threading.Thread(target=background_tasks, daemon=True)
    bg_thread.start()

    # 启动 usage 持久化线程
    start_usage_snapshot_worker()

    # 启动统计数据持久化线程
    start_persistent_stats_worker()

    # 预加载语录并做数量检查
    quotes = load_quotes()
    if quotes:
        cache.set('quotes_cache', quotes)
        author_count = len({q.get('author') for q in quotes if q.get('author')})
        if len(quotes) < 300 or author_count < 30:
            print(f"Warning: quotes count {len(quotes)}, authors {author_count}")

    print(f'CPA-XX Management Panel v3 (Optimized) started on {CONFIG["panel_host"]}:{CONFIG["panel_port"]}')
    serve(
        app,
        host=CONFIG['panel_host'],
        port=CONFIG['panel_port'],
        threads=CONFIG['panel_threads'],
        connection_limit=1000,
    )
