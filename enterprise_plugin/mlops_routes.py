"""P401-P420: MLOps+特征存储路由"""
from flask import Blueprint, request, jsonify
from mlops_feature import (
    _model_registry, _model_version, _lifecycle, _deployment, _inference,
    _feature_store, _feature_pipeline, FeatureAggregator,
    ModelEvaluatorML, ModelComparison, DriftDetector, _model_monitor,
    _cc, _rollback, _approval, _mlops,
)

bp = Blueprint("mlops", __name__, url_prefix="/api/mlops")


@bp.route("/models/register", methods=["POST"])
def model_register():
    data = request.get_json(silent=True) or {}
    return jsonify(_model_registry.register(
        data.get("name", ""), data.get("version", ""),
        data.get("framework", "sklearn"), data.get("description", ""),
        data.get("metrics"), data.get("artifacts")))


@bp.route("/models", methods=["GET"])
def model_list():
    return jsonify({"models": _model_registry.list_models()})


@bp.route("/models/<name>", methods=["GET"])
def model_get(name: str):
    return jsonify(_model_registry.get(name, request.args.get("version")) or {"error": "未找到"})


@bp.route("/models/transition", methods=["POST"])
def model_transition():
    data = request.get_json(silent=True) or {}
    return jsonify(_model_version.transition_stage(
        data.get("model", ""), data.get("version", ""), data.get("stage", "")))


@bp.route("/models/<model>/production", methods=["GET"])
def model_production(model: str):
    return jsonify({"version": _model_version.get_production_version(model)})


@bp.route("/lifecycle/<model_id>/start", methods=["POST"])
def lifecycle_start(model_id: str):
    _lifecycle.start(model_id)
    return jsonify({"status": "ok"})


@bp.route("/lifecycle/<model_id>/advance", methods=["POST"])
def lifecycle_advance(model_id: str):
    return jsonify(_lifecycle.advance(model_id))


@bp.route("/lifecycle/<model_id>", methods=["GET"])
def lifecycle_get(model_id: str):
    return jsonify(_lifecycle.get_lifecycle(model_id) or {"error": "未找到"})


@bp.route("/deploy", methods=["POST"])
def deploy():
    data = request.get_json(silent=True) or {}
    return jsonify(_deployment.deploy(
        data.get("id", ""), data.get("model", ""), data.get("version", ""),
        data.get("endpoint", ""), int(data.get("replicas", 1))))


@bp.route("/deploy/<deployment_id>/undeploy", methods=["POST"])
def undeploy(deployment_id: str):
    return jsonify(_deployment.undeploy(deployment_id))


@bp.route("/deploy/<deployment_id>/scale", methods=["POST"])
def deploy_scale(deployment_id: str):
    data = request.get_json(silent=True) or {}
    return jsonify(_deployment.scale(deployment_id, int(data.get("replicas", 1))))


@bp.route("/deploy/list", methods=["GET"])
def deploy_list():
    return jsonify({"deployments": _deployment.list_deployments()})


@bp.route("/inference/predict", methods=["POST"])
def inference_predict():
    data = request.get_json(silent=True) or {}
    return jsonify(_inference.predict(data.get("model", ""), data.get("inputs", {})))


@bp.route("/inference/log", methods=["GET"])
def inference_log():
    return jsonify({"log": _inference.get_log()})


@bp.route("/feature-store/group", methods=["POST"])
def fs_group():
    data = request.get_json(silent=True) or {}
    _feature_store.register_group(data.get("name", ""), data.get("features", []),
                                  data.get("entity_key", "id"), data.get("description", ""))
    return jsonify({"status": "ok"})


@bp.route("/feature-store/write", methods=["POST"])
def fs_write():
    data = request.get_json(silent=True) or {}
    return jsonify(_feature_store.write_offline(
        data.get("group", ""), data.get("entity_id", ""), data.get("values", {})))


@bp.route("/feature-store/<group>/<entity_id>", methods=["GET"])
def fs_read(group: str, entity_id: str):
    return jsonify(_feature_store.read_online(group, entity_id) or {"error": "未找到"})


@bp.route("/feature-store/groups", methods=["GET"])
def fs_groups():
    return jsonify({"groups": _feature_store.get_groups()})


@bp.route("/feature-pipeline/transform", methods=["POST"])
def fp_add():
    data = request.get_json(silent=True) or {}
    _feature_pipeline.add_transform(data.get("name", ""), lambda d: d.get("_output", {}),
                                    data.get("inputs", []), data.get("outputs", []))
    return jsonify({"status": "ok"})


@bp.route("/feature-pipeline/run", methods=["POST"])
def fp_run():
    data = request.get_json(silent=True) or {}
    return jsonify({"result": _feature_pipeline.run(data.get("data", {}))})


@bp.route("/evaluate", methods=["POST"])
def ml_eval():
    data = request.get_json(silent=True) or {}
    return jsonify(ModelEvaluatorML.evaluate(
        data.get("predictions", []), data.get("actuals", []), data.get("metrics")))


@bp.route("/compare", methods=["POST"])
def ml_compare():
    data = request.get_json(silent=True) or {}
    return jsonify(ModelComparison.compare(data.get("model_a", {}), data.get("model_b", {})))


@bp.route("/drift", methods=["POST"])
def ml_drift():
    data = request.get_json(silent=True) or {}
    return jsonify(DriftDetector.detect_psi(
        data.get("expected", []), data.get("actual", []), int(data.get("bins", 10))))


@bp.route("/monitor/record", methods=["POST"])
def monitor_record():
    data = request.get_json(silent=True) or {}
    _model_monitor.record(data.get("model", ""), data.get("metric", ""), float(data.get("value", 0)))
    return jsonify({"status": "ok"})


@bp.route("/monitor/<model>", methods=["GET"])
def monitor_history(model: str):
    return jsonify({"history": _model_monitor.get_history(model, request.args.get("metric"))})


@bp.route("/monitor/alerts", methods=["GET"])
def monitor_alerts():
    return jsonify({"alerts": _model_monitor.get_alerts()})


@bp.route("/cc/champion", methods=["POST"])
def cc_champion():
    data = request.get_json(silent=True) or {}
    _cc.set_champion(data.get("context", ""), data.get("model_id", ""))
    return jsonify({"status": "ok"})


@bp.route("/cc/challenger", methods=["POST"])
def cc_challenger():
    data = request.get_json(silent=True) or {}
    _cc.add_challenger(data.get("context", ""), data.get("model_id", ""))
    return jsonify({"status": "ok"})


@bp.route("/cc/promote", methods=["POST"])
def cc_promote():
    data = request.get_json(silent=True) or {}
    return jsonify(_cc.promote_challenger(data.get("context", ""), data.get("model_id", "")))


@bp.route("/cc/<context>", methods=["GET"])
def cc_status(context: str):
    return jsonify(_cc.get_status(context))


@bp.route("/rollback/<model>", methods=["POST"])
def rollback(model: str):
    data = request.get_json(silent=True) or {}
    return jsonify(_rollback.rollback(model, int(data.get("steps", 1))))


@bp.route("/approval/request", methods=["POST"])
def approval_request():
    data = request.get_json(silent=True) or {}
    return jsonify(_approval.request(
        data.get("model", ""), data.get("version", ""),
        data.get("requester", ""), data.get("reason", "")))


@bp.route("/approval/<approval_id>/approve", methods=["POST"])
def approval_approve(approval_id: str):
    data = request.get_json(silent=True) or {}
    return jsonify(_approval.approve(approval_id, data.get("approver", ""), data.get("comment", "")))


@bp.route("/approval/<approval_id>/reject", methods=["POST"])
def approval_reject(approval_id: str):
    data = request.get_json(silent=True) or {}
    return jsonify(_approval.reject(approval_id, data.get("approver", ""), data.get("comment", "")))


@bp.route("/approval/pending", methods=["GET"])
def approval_pending():
    return jsonify({"pending": _approval.list_pending()})


@bp.route("/pipeline/define", methods=["POST"])
def pipeline_define():
    data = request.get_json(silent=True) or {}
    _mlops.define(data.get("name", ""), data.get("steps", []))
    return jsonify({"status": "ok"})


@bp.route("/pipeline/<name>/execute", methods=["POST"])
def pipeline_execute(name: str):
    data = request.get_json(silent=True) or {}
    return jsonify(_mlops.execute(name, data.get("params")))


@bp.route("/pipeline/list", methods=["GET"])
def pipeline_list():
    return jsonify({"pipelines": _mlops.list_pipelines()})


@bp.route("/pipeline/executions", methods=["GET"])
def pipeline_executions():
    return jsonify({"executions": _mlops.get_executions()})
