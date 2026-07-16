"""
P1041-P1080: 部署+CI/CD+发布管理+蓝绿/金丝雀+回滚+镜像+制品+流水线+环境管理+配置注入(40轮)
"""
from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional

logger = __import__("logging").getLogger(__name__)


class DeploymentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


# ═════════ P1041-P1050: 部署管理 ═════════

class DeploymentManager:
    """部署管理器"""

    def __init__(self):
        self._deployments: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self, deploy_id: str, service: str, version: str,
               environment: str = "staging", strategy: str = "blue-green") -> dict:
        with self._lock:
            self._deployments[deploy_id] = {
                "service": service,
                "version": version,
                "environment": environment,
                "strategy": strategy,
                "status": DeploymentStatus.PENDING.value,
                "created_at": datetime.now().isoformat(),
                "steps": [],
                "logs": [],
            }
            return {"status": "ok", "deploy_id": deploy_id}

    def start(self, deploy_id: str) -> dict:
        with self._lock:
            d = self._deployments.get(deploy_id)
            if not d:
                return {"status": "error", "error": "部署不存在"}
            d["status"] = DeploymentStatus.RUNNING.value
            d["started_at"] = datetime.now().isoformat()
            return {"status": "ok"}

    def add_step(self, deploy_id: str, step: str,
                 status: str = "running") -> dict:
        with self._lock:
            d = self._deployments.get(deploy_id)
            if not d:
                return {"status": "error", "error": "部署不存在"}
            d["steps"].append({
                "step": step, "status": status,
                "timestamp": datetime.now().isoformat(),
            })
            return {"status": "ok", "total_steps": len(d["steps"])}

    def complete_step(self, deploy_id: str, step: str,
                      status: str = "success") -> dict:
        with self._lock:
            d = self._deployments.get(deploy_id)
            if not d:
                return {"status": "error", "error": "部署不存在"}
            for s in d["steps"]:
                if s["step"] == step:
                    s["status"] = status
                    s["completed_at"] = datetime.now().isoformat()
                    return {"status": "ok"}
            return {"status": "error", "error": "步骤不存在"}

    def finish(self, deploy_id: str, status: str = "success") -> dict:
        with self._lock:
            d = self._deployments.get(deploy_id)
            if not d:
                return {"status": "error", "error": "部署不存在"}
            d["status"] = status
            d["finished_at"] = datetime.now().isoformat()
            return {"status": "ok"}

    def rollback(self, deploy_id: str) -> dict:
        with self._lock:
            d = self._deployments.get(deploy_id)
            if not d:
                return {"status": "error", "error": "部署不存在"}
            d["status"] = DeploymentStatus.ROLLED_BACK.value
            d["rolled_back_at"] = datetime.now().isoformat()
            return {"status": "ok"}

    def get(self, deploy_id: str) -> dict:
        with self._lock:
            return self._deployments.get(deploy_id, {"error": "部署不存在"})

    def list_deployments(self, service: str = "",
                         status: str = "") -> list[dict]:
        with self._lock:
            deploys = list(self._deployments.values())
        if service:
            deploys = [d for d in deploys if d["service"] == service]
        if status:
            deploys = [d for d in deploys if d["status"] == status]
        return deploys


_deployment_mgr = DeploymentManager()


# ═════════ P1051-P1060: CI/CD流水线 ═════════

class PipelineManager:
    """CI/CD流水线管理"""

    def __init__(self):
        self._pipelines: dict[str, dict] = {}
        self._runs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create_pipeline(self, name: str, stages: list[dict]) -> dict:
        with self._lock:
            self._pipelines[name] = {
                "stages": stages,
                "created_at": datetime.now().isoformat(),
                "run_count": 0,
            }
            return {"status": "ok", "pipeline": name,
                    "stages": len(stages)}

    def run(self, pipeline_name: str, trigger: str = "manual",
            params: dict | None = None) -> dict:
        with self._lock:
            p = self._pipelines.get(pipeline_name)
            if not p:
                return {"status": "error", "error": "流水线不存在"}
            run_id = f"run_{p['run_count'] + 1}_{int(time.time())}"
            p["run_count"] += 1
            self._runs[run_id] = {
                "pipeline": pipeline_name,
                "trigger": trigger,
                "params": params or {},
                "status": "running",
                "started_at": datetime.now().isoformat(),
                "stages": [
                    {"name": s["name"], "status": "pending",
                     "steps": s.get("steps", [])}
                    for s in p["stages"]
                ],
            }
            return {"status": "ok", "run_id": run_id}

    def update_stage(self, run_id: str, stage_name: str,
                     status: str, output: str = "") -> dict:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return {"status": "error", "error": "运行不存在"}
            for stage in run["stages"]:
                if stage["name"] == stage_name:
                    stage["status"] = status
                    if output:
                        stage["output"] = output
                    stage["updated_at"] = datetime.now().isoformat()
                    return {"status": "ok"}
            return {"status": "error", "error": "阶段不存在"}

    def finish_run(self, run_id: str, status: str = "success") -> dict:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return {"status": "error", "error": "运行不存在"}
            run["status"] = status
            run["finished_at"] = datetime.now().isoformat()
            return {"status": "ok"}

    def get_run(self, run_id: str) -> dict:
        with self._lock:
            return self._runs.get(run_id, {"error": "运行不存在"})

    def list_pipelines(self) -> list[dict]:
        with self._lock:
            return [{"name": k, "stages": len(v["stages"]),
                     "run_count": v["run_count"]}
                    for k, v in self._pipelines.items()]

    def recent_runs(self, limit: int = 20) -> list[dict]:
        with self._lock:
            runs = list(self._runs.values())
        return runs[-limit:][::-1]


_pipeline_mgr = PipelineManager()


# ═════════ P1061-P1070: 制品 + 镜像管理 ═════════

class ArtifactManager:
    """制品管理器"""

    def __init__(self):
        self._artifacts: dict[str, dict] = {}
        self._lock = threading.Lock()

    def publish(self, artifact_id: str, name: str, version: str,
                type: str = "jar", size_bytes: int = 0,
                checksum: str = "", metadata: dict | None = None) -> dict:
        with self._lock:
            if not checksum:
                content = f"{name}:{version}:{type}".encode()
                checksum = hashlib.sha256(content).hexdigest()
            self._artifacts[artifact_id] = {
                "name": name, "version": version,
                "type": type, "size_bytes": size_bytes,
                "checksum": checksum,
                "metadata": metadata or {},
                "published_at": datetime.now().isoformat(),
            }
            return {"status": "ok", "artifact_id": artifact_id,
                    "checksum": checksum}

    def get(self, artifact_id: str) -> dict:
        with self._lock:
            return self._artifacts.get(artifact_id, {"error": "制品不存在"})

    def verify_checksum(self, artifact_id: str, expected: str) -> dict:
        with self._lock:
            art = self._artifacts.get(artifact_id)
            if not art:
                return {"status": "error", "error": "制品不存在"}
            return {"valid": art["checksum"] == expected,
                    "actual": art["checksum"], "expected": expected}

    def search(self, name: str = "", version: str = "",
               type: str = "") -> list[dict]:
        with self._lock:
            results = []
            for aid, art in self._artifacts.items():
                if name and name not in art["name"]:
                    continue
                if version and art["version"] != version:
                    continue
                if type and art["type"] != type:
                    continue
                results.append({"artifact_id": aid, **art})
            return results

    def list_all(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return [{"artifact_id": k, **v}
                    for k, v in list(self._artifacts.items())[-limit:]]


class ImageManager:
    """容器镜像管理"""

    def __init__(self):
        self._images: dict[str, dict] = {}
        self._registry: str = "registry.local"
        self._lock = threading.Lock()

    def build(self, image_id: str, name: str, tag: str = "latest",
              base_image: str = "python:3.11", layers: list[str] | None = None,
              size_mb: float = 0) -> dict:
        with self._lock:
            self._images[image_id] = {
                "name": name, "tag": tag,
                "registry": self._registry,
                "base_image": base_image,
                "layers": layers or [],
                "size_mb": size_mb,
                "digest": "sha256:" + secrets.token_hex(32),
                "built_at": datetime.now().isoformat(),
            }
            return {"status": "ok", "image_id": image_id,
                    "image": f"{self._registry}/{name}:{tag}"}

    def push(self, image_id: str) -> dict:
        with self._lock:
            img = self._images.get(image_id)
            if not img:
                return {"status": "error", "error": "镜像不存在"}
            img["pushed"] = True
            img["pushed_at"] = datetime.now().isoformat()
            return {"status": "ok",
                    "image": f"{img['registry']}/{img['name']}:{img['tag']}"}

    def pull(self, name: str, tag: str) -> dict:
        with self._lock:
            for img in self._images.values():
                if img["name"] == name and img["tag"] == tag:
                    return {"status": "ok", "image": img}
            return {"status": "error", "error": "镜像不存在"}

    def list_images(self) -> list[dict]:
        with self._lock:
            return [{"image_id": k, **v}
                    for k, v in self._images.items()]

    def scan_vulnerabilities(self, image_id: str) -> dict:
        with self._lock:
            img = self._images.get(image_id)
            if not img:
                return {"status": "error", "error": "镜像不存在"}
        # 模拟漏洞扫描
        vulnerabilities = []
        for layer in img["layers"]:
            if "outdated" in layer.lower():
                vulnerabilities.append({
                    "layer": layer, "severity": "medium",
                    "description": "可能存在过时依赖",
                })
        return {
            "image_id": image_id,
            "scanned_at": datetime.now().isoformat(),
            "total_vulnerabilities": len(vulnerabilities),
            "by_severity": dict(Counter(v["severity"] for v in vulnerabilities)),
            "vulnerabilities": vulnerabilities,
        }


_artifact_mgr = ArtifactManager()
_image_mgr = ImageManager()


# ═════════ P1071-P1080: 环境管理 + 配置注入 ═════════

class EnvironmentManager:
    """环境管理器"""

    def __init__(self):
        self._envs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self, name: str, type: str = "staging",
               region: str = "us-east-1",
               resources: dict | None = None) -> dict:
        with self._lock:
            self._envs[name] = {
                "type": type,
                "region": region,
                "resources": resources or {"cpu": 4, "memory_gb": 16},
                "status": "active",
                "created_at": datetime.now().isoformat(),
                "configs": {},
            }
            return {"status": "ok"}

    def set_config(self, env: str, key: str, value: Any,
                   secret: bool = False) -> dict:
        with self._lock:
            e = self._envs.get(env)
            if not e:
                return {"status": "error", "error": "环境不存在"}
            e["configs"][key] = {
                "value": value if not secret else "***",
                "secret": secret,
                "updated_at": datetime.now().isoformat(),
            }
            return {"status": "ok"}

    def get_config(self, env: str, key: str) -> dict:
        with self._lock:
            e = self._envs.get(env)
            if not e:
                return {"status": "error", "error": "环境不存在"}
            return e["configs"].get(key, {"error": "配置不存在"})

    def list_configs(self, env: str) -> dict:
        with self._lock:
            e = self._envs.get(env)
            if not e:
                return {"status": "error", "error": "环境不存在"}
            return e["configs"]

    def promote(self, from_env: str, to_env: str,
                artifacts: list[str] | None = None) -> dict:
        with self._lock:
            src = self._envs.get(from_env)
            dst = self._envs.get(to_env)
            if not src or not dst:
                return {"status": "error", "error": "环境不存在"}
            # 复制配置
            promoted = 0
            for k, v in src["configs"].items():
                if k not in dst["configs"]:
                    dst["configs"][k] = {**v,
                                         "promoted_at": datetime.now().isoformat()}
                    promoted += 1
            return {"status": "ok", "promoted_configs": promoted,
                    "from": from_env, "to": to_env}

    def list_envs(self) -> list[dict]:
        with self._lock:
            return [{"name": k, **{kk: vv for kk, vv in v.items() if kk != "configs"}}
                    for k, v in self._envs.items()]

    def destroy(self, env: str) -> dict:
        with self._lock:
            if env in self._envs:
                self._envs[env]["status"] = "destroyed"
                return {"status": "ok"}
            return {"status": "error", "error": "环境不存在"}


_env_mgr = EnvironmentManager()


class ReleaseManager:
    """发布管理器"""

    def __init__(self):
        self._releases: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create_release(self, release_id: str, product: str,
                       version: str, notes: str = "",
                       artifacts: list[str] | None = None) -> dict:
        with self._lock:
            self._releases[release_id] = {
                "product": product,
                "version": version,
                "notes": notes,
                "artifacts": artifacts or [],
                "status": "draft",
                "created_at": datetime.now().isoformat(),
                "approval": {"required": True, "approved_by": [],
                             "rejected_by": []},
            }
            return {"status": "ok", "release_id": release_id}

    def approve(self, release_id: str, approver: str) -> dict:
        with self._lock:
            r = self._releases.get(release_id)
            if not r:
                return {"status": "error", "error": "发布不存在"}
            r["approval"]["approved_by"].append({
                "approver": approver,
                "at": datetime.now().isoformat(),
            })
            return {"status": "ok", "approvals": len(r["approval"]["approved_by"])}

    def reject(self, release_id: str, approver: str,
               reason: str = "") -> dict:
        with self._lock:
            r = self._releases.get(release_id)
            if not r:
                return {"status": "error", "error": "发布不存在"}
            r["approval"]["rejected_by"].append({
                "approver": approver, "reason": reason,
                "at": datetime.now().isoformat(),
            })
            r["status"] = "rejected"
            return {"status": "ok"}

    def publish(self, release_id: str) -> dict:
        with self._lock:
            r = self._releases.get(release_id)
            if not r:
                return {"status": "error", "error": "发布不存在"}
            if r["approval"]["required"] and not r["approval"]["approved_by"]:
                return {"status": "error", "error": "需先获得审批"}
            if r["approval"]["rejected_by"]:
                return {"status": "error", "error": "已被拒绝"}
            r["status"] = "published"
            r["published_at"] = datetime.now().isoformat()
            return {"status": "ok"}

    def rollback(self, release_id: str, reason: str = "") -> dict:
        with self._lock:
            r = self._releases.get(release_id)
            if not r:
                return {"status": "error", "error": "发布不存在"}
            r["status"] = "rolled_back"
            r["rollback_reason"] = reason
            r["rolled_back_at"] = datetime.now().isoformat()
            return {"status": "ok"}

    def get(self, release_id: str) -> dict:
        with self._lock:
            return self._releases.get(release_id, {"error": "发布不存在"})

    def list_releases(self, product: str = "",
                      status: str = "") -> list[dict]:
        with self._lock:
            releases = list(self._releases.values())
        if product:
            releases = [r for r in releases if r["product"] == product]
        if status:
            releases = [r for r in releases if r["status"] == status]
        return releases


_release_mgr = ReleaseManager()
