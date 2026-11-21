"""
P1001-P1040: 性能监控/APM/诊断 路由
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from perf_apm import (
    _apm, _mem_analyzer, _gc_monitor,
    _cpu_profiler, _thread_analyzer, _hotspot, _baseline,
)

bp = Blueprint("perf_apm", __name__, url_prefix="/api/perf")


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _arg(name: str, default=None):
    return request.args.get(name, default)


# ═════════ APM ═════════

@bp.route("/apm/transactions/top-slow", methods=["GET"])
def apm_top_slow():
    return jsonify(_apm.top_slow(int(_arg("limit", 20))))


@bp.route("/apm/transactions/<tx_id>", methods=["GET"])
def apm_get_tx(tx_id):
    return jsonify(_apm.get_transaction(tx_id))


@bp.route("/apm/transactions/<tx_id>/spans", methods=["POST"])
def apm_add_span(tx_id):
    data = _json_body()
    return jsonify(_apm.add_span(
        tx_id,
        data.get("name", ""),
        float(data.get("duration_ms", 0)),
        data.get("tags"),
    ))


@bp.route("/apm/stats", methods=["GET"])
def apm_stats():
    return jsonify(_apm.stats())


@bp.route("/apm/transactions", methods=["POST"])
def apm_record_tx():
    data = _json_body()
    start_info = _apm.start_transaction(data.get("name", ""), data.get("trace_id", ""))
    # 立即结束(模拟)
    return jsonify(_apm.end_transaction(
        start_info["tx_id"],
        data.get("name", ""),
        start_info["start"],
        data.get("status", "ok"),
        data.get("error", ""),
    ))


# ═════════ 内存分析 ═════════

@bp.route("/memory/tracing/start", methods=["POST"])
def mem_start():
    return jsonify(_mem_analyzer.start_tracing())


@bp.route("/memory/tracing/stop", methods=["POST"])
def mem_stop():
    return jsonify(_mem_analyzer.stop_tracing())


@bp.route("/memory/snapshot", methods=["POST"])
def mem_snapshot():
    return jsonify(_mem_analyzer.snapshot())


@bp.route("/memory/usage", methods=["GET"])
def mem_usage():
    return jsonify(_mem_analyzer.current_usage())


@bp.route("/memory/compare", methods=["POST"])
def mem_compare():
    return jsonify(_mem_analyzer.compare_snapshots())


# ═════════ GC监控 ═════════

@bp.route("/gc/enable", methods=["POST"])
def gc_enable():
    return jsonify(_gc_monitor.enable())


@bp.route("/gc/disable", methods=["POST"])
def gc_disable():
    return jsonify(_gc_monitor.disable())


@bp.route("/gc/collect", methods=["POST"])
def gc_collect():
    data = _json_body()
    return jsonify(_gc_monitor.collect(int(data.get("generation", 2))))


@bp.route("/gc/stats", methods=["GET"])
def gc_stats():
    return jsonify(_gc_monitor.get_stats())


@bp.route("/gc/objects", methods=["GET"])
def gc_objects():
    return jsonify(_gc_monitor.get_objects(int(_arg("limit", 100))))


# ═════════ CPU Profiling ═════════

@bp.route("/cpu/profile", methods=["POST"])
def cpu_profile():
    data = _json_body()
    fn_name = data.get("fn", "")
    args = data.get("args", [])
    # 安全限制: 仅允许 "echo"
    if fn_name == "echo":
        return jsonify(_cpu_profiler.profile(
            data.get("name", ""),
            lambda x: f"echo:{x}",
            *args,
        ))
    return jsonify({"status": "error", "error": "函数不允许"}), 400


@bp.route("/cpu/profiles/<name>", methods=["GET"])
def cpu_get_profile(name):
    return jsonify(_cpu_profiler.get_profile(name))


@bp.route("/cpu/profiles", methods=["GET"])
def cpu_list_profiles():
    return jsonify(_cpu_profiler.list_profiles())


# ═════════ 线程分析 ═════════

@bp.route("/threads", methods=["GET"])
def threads_list():
    return jsonify(_thread_analyzer.list_threads())


@bp.route("/threads/count", methods=["GET"])
def threads_count():
    return jsonify(_thread_analyzer.thread_count())


@bp.route("/threads/stacks", methods=["GET"])
def threads_stacks():
    return jsonify(_thread_analyzer.get_thread_stacks())


@bp.route("/threads/deadlocks", methods=["GET"])
def threads_deadlocks():
    return jsonify(_thread_analyzer.detect_deadlocks())


# ═════════ 热点检测 ═════════

@bp.route("/hotspots/record", methods=["POST"])
def hotspots_record():
    data = _json_body()
    _hotspot.record(
        data.get("function", ""),
        float(data.get("duration_ms", 0)),
        bool(data.get("error", False)),
    )
    return jsonify({"status": "ok"})


@bp.route("/hotspots/top", methods=["GET"])
def hotspots_top():
    return jsonify(_hotspot.top_hotspots(int(_arg("limit", 20))))


@bp.route("/hotspots/recent", methods=["GET"])
def hotspots_recent():
    return jsonify(_hotspot.recent_hotspots(int(_arg("limit", 50))))


@bp.route("/hotspots/clear", methods=["POST"])
def hotspots_clear():
    return jsonify(_hotspot.clear())


# ═════════ 性能基线 ═════════

@bp.route("/baselines", methods=["POST"])
def baselines_set():
    data = _json_body()
    return jsonify(_baseline.set_baseline(
        data.get("name", ""),
        float(data.get("target_ms", 100)),
        float(data.get("tolerance_pct", 20)),
    ))


@bp.route("/baselines/record", methods=["POST"])
def baselines_record():
    data = _json_body()
    return jsonify(_baseline.record(
        data.get("name", ""),
        float(data.get("duration_ms", 0)),
    ))


@bp.route("/baselines/<name>/check", methods=["GET"])
def baselines_check(name):
    return jsonify(_baseline.check_regression(name))


@bp.route("/baselines", methods=["GET"])
def baselines_list():
    return jsonify(_baseline.list_baselines())
