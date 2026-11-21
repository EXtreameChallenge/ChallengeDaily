"""
P1041-P1080: 部署/CI-CD/发布 路由
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from deployment import (
    _deployment_mgr, _pipeline_mgr, _artifact_mgr,
    _image_mgr, _env_mgr, _release_mgr,
)

bp = Blueprint("deployment", __name__, url_prefix="/api/deploy")


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _arg(name: str, default=None):
    return request.args.get(name, default)


# ═════════ 部署管理 ═════════

@bp.route("/deployments", methods=["POST"])
def deploys_create():
    data = _json_body()
    return jsonify(_deployment_mgr.create(
        deploy_id=data.get("deploy_id", ""),
        service=data.get("service", ""),
        version=data.get("version", ""),
        environment=data.get("environment", "staging"),
        strategy=data.get("strategy", "blue-green"),
    ))


@bp.route("/deployments/<deploy_id>/start", methods=["POST"])
def deploys_start(deploy_id):
    return jsonify(_deployment_mgr.start(deploy_id))


@bp.route("/deployments/<deploy_id>/steps", methods=["POST"])
def deploys_add_step(deploy_id):
    data = _json_body()
    return jsonify(_deployment_mgr.add_step(
        deploy_id, data.get("step", ""), data.get("status", "running"),
    ))


@bp.route("/deployments/<deploy_id>/steps/<step>/complete", methods=["POST"])
def deploys_complete_step(deploy_id, step):
    data = _json_body()
    return jsonify(_deployment_mgr.complete_step(
        deploy_id, step, data.get("status", "success"),
    ))


@bp.route("/deployments/<deploy_id>/finish", methods=["POST"])
def deploys_finish(deploy_id):
    data = _json_body()
    return jsonify(_deployment_mgr.finish(deploy_id, data.get("status", "success")))


@bp.route("/deployments/<deploy_id>/rollback", methods=["POST"])
def deploys_rollback(deploy_id):
    return jsonify(_deployment_mgr.rollback(deploy_id))


@bp.route("/deployments/<deploy_id>", methods=["GET"])
def deploys_get(deploy_id):
    return jsonify(_deployment_mgr.get(deploy_id))


@bp.route("/deployments", methods=["GET"])
def deploys_list():
    return jsonify(_deployment_mgr.list_deployments(
        _arg("service", ""), _arg("status", ""),
    ))


# ═════════ CI/CD流水线 ═════════

@bp.route("/pipelines", methods=["POST"])
def pipelines_create():
    data = _json_body()
    return jsonify(_pipeline_mgr.create_pipeline(
        data.get("name", ""),
        data.get("stages", []),
    ))


@bp.route("/pipelines/<name>/run", methods=["POST"])
def pipelines_run(name):
    data = _json_body()
    return jsonify(_pipeline_mgr.run(
        name,
        data.get("trigger", "manual"),
        data.get("params"),
    ))


@bp.route("/pipelines/runs/<run_id>/stages/<stage_name>", methods=["POST"])
def pipelines_update_stage(run_id, stage_name):
    data = _json_body()
    return jsonify(_pipeline_mgr.update_stage(
        run_id, stage_name, data.get("status", "success"), data.get("output", ""),
    ))


@bp.route("/pipelines/runs/<run_id>/finish", methods=["POST"])
def pipelines_finish_run(run_id):
    data = _json_body()
    return jsonify(_pipeline_mgr.finish_run(run_id, data.get("status", "success")))


@bp.route("/pipelines/runs/<run_id>", methods=["GET"])
def pipelines_get_run(run_id):
    return jsonify(_pipeline_mgr.get_run(run_id))


@bp.route("/pipelines", methods=["GET"])
def pipelines_list():
    return jsonify(_pipeline_mgr.list_pipelines())


@bp.route("/pipelines/runs/recent", methods=["GET"])
def pipelines_recent_runs():
    return jsonify(_pipeline_mgr.recent_runs(int(_arg("limit", 20))))


# ═════════ 制品管理 ═════════

@bp.route("/artifacts", methods=["POST"])
def artifacts_publish():
    data = _json_body()
    return jsonify(_artifact_mgr.publish(
        artifact_id=data.get("artifact_id", ""),
        name=data.get("name", ""),
        version=data.get("version", ""),
        type=data.get("type", "jar"),
        size_bytes=int(data.get("size_bytes", 0)),
        checksum=data.get("checksum", ""),
        metadata=data.get("metadata"),
    ))


@bp.route("/artifacts/<artifact_id>", methods=["GET"])
def artifacts_get(artifact_id):
    return jsonify(_artifact_mgr.get(artifact_id))


@bp.route("/artifacts/<artifact_id>/verify", methods=["POST"])
def artifacts_verify(artifact_id):
    data = _json_body()
    return jsonify(_artifact_mgr.verify_checksum(
        artifact_id, data.get("expected", ""),
    ))


@bp.route("/artifacts/search", methods=["GET"])
def artifacts_search():
    return jsonify(_artifact_mgr.search(
        _arg("name", ""), _arg("version", ""), _arg("type", ""),
    ))


@bp.route("/artifacts", methods=["GET"])
def artifacts_list():
    return jsonify(_artifact_mgr.list_all(int(_arg("limit", 50))))


# ═════════ 镜像管理 ═════════

@bp.route("/images", methods=["POST"])
def images_build():
    data = _json_body()
    return jsonify(_image_mgr.build(
        image_id=data.get("image_id", ""),
        name=data.get("name", ""),
        tag=data.get("tag", "latest"),
        base_image=data.get("base_image", "python:3.11"),
        layers=data.get("layers"),
        size_mb=float(data.get("size_mb", 0)),
    ))


@bp.route("/images/<image_id>/push", methods=["POST"])
def images_push(image_id):
    return jsonify(_image_mgr.push(image_id))


@bp.route("/images/pull", methods=["POST"])
def images_pull():
    data = _json_body()
    return jsonify(_image_mgr.pull(data.get("name", ""), data.get("tag", "latest")))


@bp.route("/images", methods=["GET"])
def images_list():
    return jsonify(_image_mgr.list_images())


@bp.route("/images/<image_id>/scan", methods=["POST"])
def images_scan(image_id):
    return jsonify(_image_mgr.scan_vulnerabilities(image_id))


# ═════════ 环境管理 ═════════

@bp.route("/envs", methods=["POST"])
def envs_create():
    data = _json_body()
    return jsonify(_env_mgr.create(
        data.get("name", ""),
        data.get("type", "staging"),
        data.get("region", "us-east-1"),
        data.get("resources"),
    ))


@bp.route("/envs/<env>/configs", methods=["POST"])
def envs_set_config(env):
    data = _json_body()
    return jsonify(_env_mgr.set_config(
        env, data.get("key", ""), data.get("value"),
        bool(data.get("secret", False)),
    ))


@bp.route("/envs/<env>/configs/<key>", methods=["GET"])
def envs_get_config(env, key):
    return jsonify(_env_mgr.get_config(env, key))


@bp.route("/envs/<env>/configs", methods=["GET"])
def envs_list_configs(env):
    return jsonify(_env_mgr.list_configs(env))


@bp.route("/envs/promote", methods=["POST"])
def envs_promote():
    data = _json_body()
    return jsonify(_env_mgr.promote(
        data.get("from", ""), data.get("to", ""),
        data.get("artifacts"),
    ))


@bp.route("/envs", methods=["GET"])
def envs_list():
    return jsonify(_env_mgr.list_envs())


@bp.route("/envs/<env>", methods=["DELETE"])
def envs_destroy(env):
    return jsonify(_env_mgr.destroy(env))


# ═════════ 发布管理 ═════════

@bp.route("/releases", methods=["POST"])
def releases_create():
    data = _json_body()
    return jsonify(_release_mgr.create_release(
        data.get("release_id", ""),
        data.get("product", ""),
        data.get("version", ""),
        data.get("notes", ""),
        data.get("artifacts"),
    ))


@bp.route("/releases/<release_id>/approve", methods=["POST"])
def releases_approve(release_id):
    data = _json_body()
    return jsonify(_release_mgr.approve(release_id, data.get("approver", "")))


@bp.route("/releases/<release_id>/reject", methods=["POST"])
def releases_reject(release_id):
    data = _json_body()
    return jsonify(_release_mgr.reject(
        release_id, data.get("approver", ""), data.get("reason", ""),
    ))


@bp.route("/releases/<release_id>/publish", methods=["POST"])
def releases_publish(release_id):
    return jsonify(_release_mgr.publish(release_id))


@bp.route("/releases/<release_id>/rollback", methods=["POST"])
def releases_rollback(release_id):
    data = _json_body()
    return jsonify(_release_mgr.rollback(release_id, data.get("reason", "")))


@bp.route("/releases/<release_id>", methods=["GET"])
def releases_get(release_id):
    return jsonify(_release_mgr.get(release_id))


@bp.route("/releases", methods=["GET"])
def releases_list():
    return jsonify(_release_mgr.list_releases(
        _arg("product", ""), _arg("status", ""),
    ))
