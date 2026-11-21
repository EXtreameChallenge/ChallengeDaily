"""P281-P300: 数据迁移 + i18n 路由"""
import time
from flask import Blueprint, request, jsonify
from data_migration import (
    _migration_registry, _migration_runner, _tx_guard, _dep_graph,
    _data_seeder, _translation_mgr, _locale_detector,
    PluralRules, _fallback, RTLSupport,
)

bp = Blueprint("migration_i18n", __name__, url_prefix="/api/migration-i18n")


@bp.route("/migrations", methods=["GET"])
def list_migrations():
    return jsonify({"migrations": _migration_registry.list_all(),
                    "current_version": _migration_registry.get_current()})


@bp.route("/migrations/upgrade", methods=["POST"])
def upgrade():
    data = request.get_json(silent=True) or {}
    target = data.get("target_version")
    return jsonify(_migration_runner.upgrade(target))


@bp.route("/migrations/downgrade", methods=["POST"])
def downgrade():
    data = request.get_json(silent=True) or {}
    target = data.get("target_version")
    if target is None:
        return jsonify({"status": "error", "error": "缺少 target_version"}), 400
    return jsonify(_migration_runner.downgrade(int(target)))


@bp.route("/migrations/history", methods=["GET"])
def migration_history():
    return jsonify({"history": _migration_registry.get_history()})


@bp.route("/transaction/run", methods=["POST"])
def tx_run():
    data = request.get_json(silent=True) or {}
    key = data.get("key", "tx_" + str(int(time.time() * 1000)))
    state = data.get("state", {})
    op = data.get("operation_name", "")
    if op == "noop":
        result = _tx_guard.run_protected(key, state, lambda s: {**s, "touched": True})
    else:
        result = _tx_guard.run_protected(key, state, lambda s: s)
    return jsonify(result)


@bp.route("/dependency/graph", methods=["GET"])
def dep_graph():
    return jsonify({"has_cycle": _dep_graph.has_cycle()})


@bp.route("/dependency/edge", methods=["POST"])
def dep_add_edge():
    data = request.get_json(silent=True) or {}
    src = data.get("src")
    dst = data.get("dst")
    if src is None or dst is None:
        return jsonify({"status": "error", "error": "缺少 src/dst"}), 400
    _dep_graph.add_edge(int(src), int(dst))
    return jsonify({"status": "ok"})


@bp.route("/seeders", methods=["GET"])
def list_seeders():
    return jsonify({"seeders": _data_seeder.list_seeders()})


@bp.route("/seeders/run", methods=["POST"])
def run_seeder():
    data = request.get_json(silent=True) or {}
    return jsonify(_data_seeder.run(data.get("name")))


@bp.route("/i18n/locales", methods=["GET"])
def i18n_locales():
    return jsonify({"locales": _translation_mgr.list_locales(),
                    "supported": _locale_detector.list_supported()})


@bp.route("/i18n/translate", methods=["GET"])
def i18n_translate():
    key = request.args.get("key", "")
    locale = request.args.get("locale")
    return jsonify({"key": key, "text": _translation_mgr.translate(key, locale),
                    "locale": locale or "zh-CN"})


@bp.route("/i18n/add", methods=["POST"])
def i18n_add():
    data = request.get_json(silent=True) or {}
    locale = data.get("locale")
    translations = data.get("translations", {})
    if not locale or not translations:
        return jsonify({"status": "error", "error": "缺少 locale/translations"}), 400
    _translation_mgr.add_locale(locale, translations)
    return jsonify({"status": "ok", "added": len(translations)})


@bp.route("/i18n/missing-keys", methods=["GET"])
def i18n_missing():
    src = request.args.get("source", "zh-CN")
    tgt = request.args.get("target", "en-US")
    return jsonify({"missing": _translation_mgr.get_missing_keys(src, tgt)})


@bp.route("/i18n/detect", methods=["GET"])
def i18n_detect():
    header = request.headers.get("Accept-Language", "")
    return jsonify({"detected": _locale_detector.detect_from_header(header),
                    "header": header})


@bp.route("/i18n/user-pref", methods=["POST"])
def i18n_user_pref():
    data = request.get_json(silent=True) or {}
    _locale_detector.set_user_pref(data.get("user_id", ""), data.get("locale", "zh-CN"))
    return jsonify({"status": "ok"})


@bp.route("/i18n/plural", methods=["GET"])
def i18n_plural():
    locale = request.args.get("locale", "zh-CN")
    try:
        count = int(request.args.get("count", "1"))
    except ValueError:
        count = 1
    category = PluralRules.get_category(locale, count)
    return jsonify({"locale": locale, "count": count, "category": category})


@bp.route("/i18n/fallback", methods=["GET"])
def i18n_fallback():
    key = request.args.get("key", "")
    locale = request.args.get("locale", "zh-CN")
    return jsonify({"key": key, "text": _fallback.translate(key, locale),
                    "chain": _fallback.get_chain(locale)})


@bp.route("/i18n/rtl", methods=["GET"])
def i18n_rtl():
    locale = request.args.get("locale", "zh-CN")
    return jsonify({"locale": locale,
                    "is_rtl": RTLSupport.is_rtl(locale),
                    "direction": RTLSupport.get_direction(locale),
                    "rtl_locales": RTLSupport.list_rtl_locales()})
