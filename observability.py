"""可观测性：结构化日志 + trace_id + 指标采集"""
import logging
import logging.config
import json
import time
import uuid
import threading
from collections import defaultdict

# ── 结构化 JSON 日志格式 ──
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        if hasattr(record, 'trace_id'):
            log_entry['trace_id'] = record.trace_id
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)

def setup_structured_logging(level=logging.INFO, json_output=True):
    """配置结构化日志"""
    root = logging.getLogger()
    root.setLevel(level)
    # 移除旧 handler
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler()
    if json_output:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    root.addHandler(handler)

# ── Trace ID ──
_trace_id_local = threading.local()

def generate_trace_id() -> str:
    """生成 8 位 trace_id"""
    return str(uuid.uuid4())[:8]

def set_trace_id(trace_id: str):
    _trace_id_local.trace_id = trace_id

def get_trace_id() -> str:
    return getattr(_trace_id_local, 'trace_id', '')

# ── 指标采集 ──
_metrics_lock = threading.Lock()
_metrics = defaultdict(lambda: {'count': 0, 'total_time': 0.0, 'errors': 0})

def record_request(endpoint: str, duration_sec: float, error: bool = False):
    with _metrics_lock:
        m = _metrics[endpoint]
        m['count'] += 1
        m['total_time'] += duration_sec
        if error:
            m['errors'] += 1

def get_metrics() -> dict:
    with _metrics_lock:
        result = {}
        for ep, m in _metrics.items():
            avg = m['total_time'] / m['count'] if m['count'] > 0 else 0
            result[ep] = {
                'count': m['count'],
                'avg_time_sec': round(avg, 4),
                'total_time_sec': round(m['total_time'], 2),
                'errors': m['errors'],
                'error_rate': round(m['errors'] / m['count'], 4) if m['count'] > 0 else 0,
            }
        return result

def reset_metrics():
    with _metrics_lock:
        _metrics.clear()
