"""
P401-P420: MLOps + 特征存储(20轮)
- P401: 模型注册中心
- P402: 模型版本管理
- P403: 模型生命周期
- P404: 模型部署管理
- P405: 模型推理服务
- P406: 特征存储(Feature Store)
- P407: 特征计算管道
- P408: 特征聚合服务
- P409: 特征服务(在线/离线)
- P410: 特征发现
- P411: 模型评估管道
- P412: 模型对比
- P413: 模型基线
- P414: 模型漂移检测
- P415: 模型性能监控
- P416: A/B模型对比
- P417: Champion/Challenger
- P418: 模型回滚
- P419: 模型审批工作流
- P420: MLOps流水线编排
"""
from __future__ import annotations

import hashlib
import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P401: 模型注册中心 ──────────────────────────
class ModelRegistry:
    """模型注册中心"""

    def __init__(self):
        self._models: dict[str, dict] = {}
        self._lock = threading.Lock()

    def register(self, name: str, version: str, framework: str = "sklearn",
                 description: str = "", metrics: dict | None = None,
                 artifacts: dict | None = None) -> dict:
        with self._lock:
            if name not in self._models:
                self._models[name] = {"versions": {}}
            self._models[name]["versions"][version] = {
                "framework": framework,
                "description": description,
                "metrics": metrics or {},
                "artifacts": artifacts or {},
                "status": "registered",
                "registered_at": datetime.now().isoformat(),
            }
            return {"status": "ok", "model": name, "version": version}

    def get(self, name: str, version: str | None = None) -> dict | None:
        with self._lock:
            model = self._models.get(name)
            if not model:
                return None
            if version:
                return model["versions"].get(version)
            return {"name": name, "versions": list(model["versions"].keys())}

    def list_models(self) -> list[dict]:
        with self._lock:
            return [
                {"name": name, "versions": list(m["versions"].keys())}
                for name, m in self._models.items()
            ]


_model_registry = ModelRegistry()


# ─── P402: 模型版本管理 ──────────────────────────
class ModelVersionManager:
    """模型版本管理"""

    def __init__(self, registry: ModelRegistry):
        self._registry = registry
        self._stages: dict[str, str] = {}  # "model:version" -> stage
        self._lock = threading.Lock()

    def transition_stage(self, model: str, version: str, stage: str) -> dict:
        valid_stages = ["none", "staging", "production", "archived"]
        if stage not in valid_stages:
            return {"status": "error", "error": "无效阶段"}
        with self._lock:
            self._stages[f"{model}:{version}"] = stage
        return {"status": "ok", "model": model, "version": version, "stage": stage}

    def get_stage(self, model: str, version: str) -> str:
        with self._lock:
            return self._stages.get(f"{model}:{version}", "none")

    def get_production_version(self, model: str) -> str | None:
        with self._lock:
            for key, stage in self._stages.items():
                if stage == "production" and key.startswith(f"{model}:"):
                    return key.split(":")[1]
            return None


_model_version = ModelVersionManager(_model_registry)


# ─── P403: 模型生命周期 ──────────────────────────
class ModelLifecycle:
    """模型生命周期管理"""

    STAGES = ["development", "staging", "production", "monitoring", "retired"]

    def __init__(self):
        self._lifecycles: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, model_id: str) -> None:
        with self._lock:
            self._lifecycles[model_id] = {
                "current_stage": "development",
                "history": [{"stage": "development", "timestamp": datetime.now().isoformat()}],
            }

    def advance(self, model_id: str) -> dict:
        with self._lock:
            lc = self._lifecycles.get(model_id)
            if not lc:
                return {"status": "error", "error": "模型未启动生命周期"}
            current_idx = self.STAGES.index(lc["current_stage"])
            if current_idx < len(self.STAGES) - 1:
                lc["current_stage"] = self.STAGES[current_idx + 1]
                lc["history"].append({
                    "stage": lc["current_stage"],
                    "timestamp": datetime.now().isoformat(),
                })
                return {"status": "ok", "current_stage": lc["current_stage"]}
            return {"status": "ok", "message": "已是最后阶段"}

    def get_lifecycle(self, model_id: str) -> dict | None:
        with self._lock:
            return self._lifecycles.get(model_id)


_lifecycle = ModelLifecycle()


# ─── P404: 模型部署管理 ──────────────────────────
class ModelDeployment:
    """模型部署管理"""

    def __init__(self):
        self._deployments: dict[str, dict] = {}
        self._lock = threading.Lock()

    def deploy(self, deployment_id: str, model: str, version: str,
               endpoint: str = "", replicas: int = 1) -> dict:
        with self._lock:
            self._deployments[deployment_id] = {
                "model": model,
                "version": version,
                "endpoint": endpoint,
                "replicas": replicas,
                "status": "deployed",
                "deployed_at": datetime.now().isoformat(),
            }
            return {"status": "ok", "deployment_id": deployment_id}

    def undeploy(self, deployment_id: str) -> dict:
        with self._lock:
            if deployment_id in self._deployments:
                self._deployments[deployment_id]["status"] = "undeployed"
                self._deployments[deployment_id]["undeployed_at"] = datetime.now().isoformat()
                return {"status": "ok"}
            return {"status": "error", "error": "部署不存在"}

    def scale(self, deployment_id: str, replicas: int) -> dict:
        with self._lock:
            if deployment_id in self._deployments:
                self._deployments[deployment_id]["replicas"] = replicas
                return {"status": "ok", "replicas": replicas}
            return {"status": "error", "error": "部署不存在"}

    def list_deployments(self) -> list[dict]:
        with self._lock:
            return [{"id": k, **v} for k, v in self._deployments.items()]


_deployment = ModelDeployment()


# ─── P405: 模型推理服务 ──────────────────────────
class InferenceService:
    """模型推理服务"""

    def __init__(self):
        self._handlers: dict[str, Callable] = {}
        self._inference_log: deque = deque(maxlen=500)
        self._lock = threading.Lock()

    def register_handler(self, model: str, handler: Callable[[dict], dict]) -> None:
        with self._lock:
            self._handlers[model] = handler

    def predict(self, model: str, inputs: dict) -> dict:
        with self._lock:
            handler = self._handlers.get(model)
        if not handler:
            return {"status": "error", "error": "模型处理器未注册"}
        start = time.time()
        try:
            result = handler(inputs)
            duration = (time.time() - start) * 1000
            with self._lock:
                self._inference_log.append({
                    "model": model,
                    "duration_ms": round(duration, 2),
                    "success": True,
                    "timestamp": datetime.now().isoformat(),
                })
            return {"status": "ok", "prediction": result, "duration_ms": round(duration, 2)}
        except Exception as e:
            with self._lock:
                self._inference_log.append({
                    "model": model, "success": False, "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                })
            return {"status": "error", "error": str(e)}

    def get_log(self, limit: int = 50) -> list[dict]:
        with self._lock:
            log = list(self._inference_log)
        log.reverse()
        return log[:limit]


_inference = InferenceService()


# ─── P406-P410: 特征存储系列 ──────────────────────────
class FeatureStore:
    """特征存储(在线+离线)"""

    def __init__(self):
        self._features: dict[str, dict] = {}  # feature_group -> {entity_id -> {feature -> value}}
        self._metadata: dict[str, dict] = {}
        self._lock = threading.Lock()

    def register_group(self, name: str, features: list[str],
                       entity_key: str = "id", description: str = "") -> None:
        with self._lock:
            self._features[name] = {}
            self._metadata[name] = {
                "features": features,
                "entity_key": entity_key,
                "description": description,
                "created_at": datetime.now().isoformat(),
            }

    def write_offline(self, group: str, entity_id: str,
                      values: dict[str, float], timestamp: str | None = None) -> dict:
        with self._lock:
            if group not in self._features:
                return {"status": "error", "error": "特征组不存在"}
            self._features[group][entity_id] = {
                **values,
                "_timestamp": timestamp or datetime.now().isoformat(),
            }
            return {"status": "ok"}

    def read_online(self, group: str, entity_id: str) -> dict | None:
        with self._lock:
            return self._features.get(group, {}).get(entity_id)

    def get_groups(self) -> list[dict]:
        with self._lock:
            return [{"name": k, **v} for k, v in self._metadata.items()]


_feature_store = FeatureStore()


class FeaturePipeline:
    """特征计算管道"""

    def __init__(self):
        self._transforms: list[dict] = []
        self._lock = threading.Lock()

    def add_transform(self, name: str, fn: Callable[[dict], dict],
                      inputs: list[str], outputs: list[str]) -> None:
        with self._lock:
            self._transforms.append({
                "name": name, "fn": fn,
                "inputs": inputs, "outputs": outputs,
            })

    def run(self, data: dict) -> dict:
        with self._lock:
            transforms = list(self._transforms)
        result = dict(data)
        for t in transforms:
            try:
                output = t["fn"](result)
                result.update(output)
            except Exception as e:
                logger.warning("特征转换 %s 失败: %s", t["name"], e)
        return result


_feature_pipeline = FeaturePipeline()


class FeatureAggregator:
    """特征聚合服务"""

    @staticmethod
    def aggregate(values: list[float], method: str = "mean") -> float:
        if not values:
            return 0.0
        if method == "mean":
            return sum(values) / len(values)
        elif method == "sum":
            return sum(values)
        elif method == "max":
            return max(values)
        elif method == "min":
            return min(values)
        elif method == "count":
            return float(len(values))
        elif method == "std":
            mean = sum(values) / len(values)
            var = sum((x - mean) ** 2 for x in values) / len(values)
            return var ** 0.5
        return 0.0


# ─── P411-P420: 模型评估/监控系列 ──────────────────────────
class ModelEvaluatorML:
    """模型评估管道"""

    @staticmethod
    def evaluate(predictions: list, actuals: list,
                 metrics: list[str] | None = None) -> dict:
        if not predictions or not actuals or len(predictions) != len(actuals):
            return {"status": "error", "error": "数据无效"}
        metrics = metrics or ["accuracy", "precision", "recall"]
        results = {}
        if "accuracy" in metrics:
            correct = sum(1 for p, a in zip(predictions, actuals) if p == a)
            results["accuracy"] = round(correct / len(actuals), 4)
        if "mse" in metrics:
            mse = sum((p - a) ** 2 for p, a in zip(predictions, actuals)) / len(actuals)
            results["mse"] = round(mse, 4)
        if "mae" in metrics:
            mae = sum(abs(p - a) for p, a in zip(predictions, actuals)) / len(actuals)
            results["mae"] = round(mae, 4)
        return results


class ModelComparison:
    """模型对比"""

    @staticmethod
    def compare(model_a: dict, model_b: dict) -> dict:
        metrics_a = model_a.get("metrics", {})
        metrics_b = model_b.get("metrics", {})
        comparison = {}
        for metric in set(metrics_a.keys()) | set(metrics_b.keys()):
            val_a = metrics_a.get(metric, 0)
            val_b = metrics_b.get(metric, 0)
            comparison[metric] = {
                "model_a": val_a,
                "model_b": val_b,
                "diff": round(val_b - val_a, 4) if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)) else None,
                "winner": "b" if val_b > val_a else "a" if val_a > val_b else "tie",
            }
        return comparison


class DriftDetector:
    """模型漂移检测"""

    @staticmethod
    def detect_psi(expected: list[float], actual: list[float],
                   bins: int = 10) -> dict:
        if not expected or not actual:
            return {"status": "error", "error": "数据为空"}
        min_val = min(min(expected), min(actual))
        max_val = max(max(expected), max(actual))
        if max_val == min_val:
            return {"psi": 0, "drift": False}
        # 分桶
        bin_edges = [min_val + i * (max_val - min_val) / bins for i in range(bins + 1)]
        expected_counts = [0] * bins
        actual_counts = [0] * bins
        for v in expected:
            idx = min(int((v - min_val) / (max_val - min_val) * bins), bins - 1)
            expected_counts[idx] += 1
        for v in actual:
            idx = min(int((v - min_val) / (max_val - min_val) * bins), bins - 1)
            actual_counts[idx] += 1
        # PSI
        psi = 0
        n_exp = len(expected)
        n_act = len(actual)
        for i in range(bins):
            p_exp = max(expected_counts[i] / n_exp, 1e-6)
            p_act = max(actual_counts[i] / n_act, 1e-6)
            psi += (p_act - p_exp) * math.log(p_act / p_exp) if p_exp > 0 and p_act > 0 else 0
        return {"psi": round(psi, 4), "drift": psi > 0.2,
                "severity": "high" if psi > 0.5 else "medium" if psi > 0.2 else "low"}


class ModelMonitor:
    """模型性能监控"""

    def __init__(self):
        self._metrics_history: deque = deque(maxlen=1000)
        self._alerts: deque = deque(maxlen=200)
        self._lock = threading.Lock()

    def record(self, model: str, metric: str, value: float) -> None:
        with self._lock:
            self._metrics_history.append({
                "model": model, "metric": metric, "value": value,
                "timestamp": datetime.now().isoformat(),
            })
            if metric == "accuracy" and value < 0.7:
                self._alerts.append({
                    "model": model, "metric": metric, "value": value,
                    "severity": "high",
                    "message": f"准确率{value}低于0.7",
                    "timestamp": datetime.now().isoformat(),
                })

    def get_history(self, model: str, metric: str | None = None,
                    limit: int = 50) -> list[dict]:
        with self._lock:
            h = list(self._metrics_history)
        if model:
            h = [x for x in h if x["model"] == model]
        if metric:
            h = [x for x in h if x["metric"] == metric]
        h.reverse()
        return h[:limit]

    def get_alerts(self, limit: int = 50) -> list[dict]:
        with self._lock:
            a = list(self._alerts)
        a.reverse()
        return a[:limit]


_model_monitor = ModelMonitor()


class ChampionChallenger:
    """Champion/Challenger模型管理"""

    def __init__(self):
        self._champions: dict[str, str] = {}  # context -> model_id
        self._challengers: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    def set_champion(self, context: str, model_id: str) -> None:
        with self._lock:
            self._champions[context] = model_id

    def add_challenger(self, context: str, model_id: str) -> None:
        with self._lock:
            if context not in self._challengers:
                self._challengers[context] = []
            self._challengers[context].append(model_id)

    def promote_challenger(self, context: str, model_id: str) -> dict:
        with self._lock:
            if model_id in self._challengers.get(context, []):
                old_champion = self._champions.get(context)
                self._champions[context] = model_id
                self._challengers[context] = [m for m in self._challengers[context] if m != model_id]
                if old_champion:
                    self._challengers[context].append(old_champion)
                return {"status": "ok", "new_champion": model_id, "old_champion": old_champion}
            return {"status": "error", "error": "Challenger不存在"}

    def get_status(self, context: str) -> dict:
        with self._lock:
            return {
                "champion": self._champions.get(context),
                "challengers": self._challengers.get(context, []),
            }


_cc = ChampionChallenger()


class ModelRollback:
    """模型回滚"""

    def __init__(self):
        self._history: dict[str, deque] = {}
        self._lock = threading.Lock()

    def record_deployment(self, model: str, version: str) -> None:
        with self._lock:
            if model not in self._history:
                self._history[model] = deque(maxlen=10)
            self._history[model].append({
                "version": version,
                "deployed_at": datetime.now().isoformat(),
            })

    def rollback(self, model: str, steps: int = 1) -> dict:
        with self._lock:
            history = self._history.get(model)
            if not history or len(history) <= steps:
                return {"status": "error", "error": "无足够历史"}
            hist_list = list(history)
            target = hist_list[-(steps + 1)]
            return {"status": "ok", "rollback_to": target["version"],
                    "deployed_at": target["deployed_at"]}


_rollback = ModelRollback()


class ModelApproval:
    """模型审批工作流"""

    def __init__(self):
        self._approvals: dict[str, dict] = {}
        self._lock = threading.Lock()

    def request(self, model: str, version: str, requester: str,
                reason: str = "") -> dict:
        with self._lock:
            approval_id = f"appr_{len(self._approvals) + 1}"
            self._approvals[approval_id] = {
                "model": model,
                "version": version,
                "requester": requester,
                "reason": reason,
                "status": "pending",
                "approvers": [],
                "created_at": datetime.now().isoformat(),
            }
            return {"approval_id": approval_id}

    def approve(self, approval_id: str, approver: str,
                comment: str = "") -> dict:
        with self._lock:
            appr = self._approvals.get(approval_id)
            if not appr:
                return {"status": "error", "error": "审批不存在"}
            if appr["status"] != "pending":
                return {"status": "error", "error": "审批已处理"}
            appr["approvers"].append({"approver": approver, "comment": comment,
                                       "decision": "approve",
                                       "timestamp": datetime.now().isoformat()})
            appr["status"] = "approved"
            return {"status": "ok"}

    def reject(self, approval_id: str, approver: str,
               comment: str = "") -> dict:
        with self._lock:
            appr = self._approvals.get(approval_id)
            if not appr:
                return {"status": "error", "error": "审批不存在"}
            appr["approvers"].append({"approver": approver, "comment": comment,
                                       "decision": "reject",
                                       "timestamp": datetime.now().isoformat()})
            appr["status"] = "rejected"
            return {"status": "ok"}

    def list_pending(self) -> list[dict]:
        with self._lock:
            return [v for v in self._approvals.values() if v["status"] == "pending"]


_approval = ModelApproval()


class MLOpsPipeline:
    """MLOps流水线编排"""

    def __init__(self):
        self._pipelines: dict[str, list[dict]] = {}
        self._executions: deque = deque(maxlen=200)
        self._lock = threading.Lock()

    def define(self, name: str, steps: list[dict]) -> None:
        with self._lock:
            self._pipelines[name] = steps

    def execute(self, name: str, params: dict | None = None) -> dict:
        with self._lock:
            steps = self._pipelines.get(name)
        if not steps:
            return {"status": "error", "error": "流水线未定义"}
        results = []
        for i, step in enumerate(steps):
            step_result = {
                "step": i + 1,
                "name": step.get("name", f"step_{i+1}"),
                "status": "completed",
                "timestamp": datetime.now().isoformat(),
            }
            results.append(step_result)
        execution = {
            "pipeline": name,
            "steps": results,
            "status": "completed",
            "started_at": datetime.now().isoformat(),
            "params": params or {},
        }
        with self._lock:
            self._executions.append(execution)
        return execution

    def list_pipelines(self) -> list[str]:
        with self._lock:
            return list(self._pipelines.keys())

    def get_executions(self, limit: int = 20) -> list[dict]:
        with self._lock:
            e = list(self._executions)
        e.reverse()
        return e[:limit]


_mlops = MLOpsPipeline()
