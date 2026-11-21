"""
P311-P320: 机器学习(ML)基础系统
- P311: 特征向量管理
- P312: K-Means聚类
- P313: KNN分类器
- P314: 线性回归
- P315: 逻辑回归
- P316: 决策树
- P317: 朴素贝叶斯
- P318: 数据集拆分器
- P319: 模型评估器
- P320: 特征缩放器
"""
from __future__ import annotations

import logging
import math
import random
import threading
from collections import Counter, deque
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P311: 特征向量管理 ──────────────────────────
class FeatureVector:
    """特征向量管理"""

    def __init__(self):
        self._features: dict[str, list[float]] = {}
        self._labels: list[str] = []
        self._lock = threading.Lock()

    def add_sample(self, features: dict[str, float], label: str = "") -> int:
        with self._lock:
            for k, v in features.items():
                if k not in self._features:
                    self._features[k] = []
                self._features[k].append(float(v))
            self._labels.append(label)
            return len(self._labels) - 1

    def get_matrix(self) -> tuple[list[list[float]], list[str], list[str]]:
        with self._lock:
            if not self._features:
                return [], [], []
            keys = sorted(self._features.keys())
            n = len(self._labels)
            matrix = []
            for i in range(n):
                row = [self._features[k][i] for k in keys]
                matrix.append(row)
            return matrix, list(self._labels), keys

    def get_stats(self) -> dict:
        with self._lock:
            stats = {}
            for k, vals in self._features.items():
                if vals:
                    stats[k] = {
                        "count": len(vals),
                        "min": min(vals),
                        "max": max(vals),
                        "mean": sum(vals) / len(vals),
                    }
            return {"features": stats, "samples": len(self._labels)}


_feature_vec = FeatureVector()


# ─── P312: K-Means聚类 ──────────────────────────
class KMeans:
    """K-Means聚类算法"""

    def __init__(self, k: int = 3, max_iter: int = 100):
        self.k = k
        self.max_iter = max_iter
        self.centroids: list[list[float]] = []
        self.labels_: list[int] = []
        self.inertia_: float = 0.0

    def fit(self, data: list[list[float]]) -> dict:
        if not data or self.k <= 0:
            return {"status": "error", "error": "无效输入"}
        # 初始化:随机选取k个点
        random.seed(42)
        self.centroids = random.sample(data, min(self.k, len(data)))
        for iteration in range(self.max_iter):
            # 分配
            new_labels = [self._assign(point) for point in data]
            # 更新中心
            new_centroids = []
            for c in range(len(self.centroids)):
                cluster_points = [data[i] for i in range(len(data)) if new_labels[i] == c]
                if cluster_points:
                    centroid = [sum(p[d] for p in cluster_points) / len(cluster_points)
                                for d in range(len(cluster_points[0]))]
                else:
                    centroid = self.centroids[c]
                new_centroids.append(centroid)
            # 收敛检查
            if new_centroids == self.centroids:
                break
            self.centroids = new_centroids
            self.labels_ = new_labels
        # 计算惯性
        self.inertia_ = sum(
            sum((data[i][d] - self.centroids[self.labels_[i]][d]) ** 2
                for d in range(len(data[i])))
            for i in range(len(data))
        )
        return {
            "labels": self.labels_,
            "centroids": self.centroids,
            "iterations": iteration + 1,
            "inertia": round(self.inertia_, 4),
        }

    def _assign(self, point: list[float]) -> int:
        distances = [self._dist(point, c) for c in self.centroids]
        return distances.index(min(distances))

    @staticmethod
    def _dist(a: list[float], b: list[float]) -> float:
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


# ─── P313: KNN分类器 ──────────────────────────
class KNNClassifier:
    """K最近邻分类器"""

    def __init__(self, k: int = 3):
        self.k = k
        self._data: list[list[float]] = []
        self._labels: list[str] = []

    def fit(self, data: list[list[float]], labels: list[str]) -> None:
        self._data = data
        self._labels = labels

    def predict(self, point: list[float]) -> str:
        if not self._data:
            return ""
        distances = []
        for i, sample in enumerate(self._data):
            d = math.sqrt(sum((a - b) ** 2 for a, b in zip(point, sample)))
            distances.append((d, self._labels[i]))
        distances.sort(key=lambda x: x[0])
        k = min(self.k, len(distances))
        top_labels = [d[1] for d in distances[:k]]
        return Counter(top_labels).most_common(1)[0][0]

    def predict_proba(self, point: list[float]) -> dict:
        if not self._data:
            return {}
        distances = []
        for i, sample in enumerate(self._data):
            d = math.sqrt(sum((a - b) ** 2 for a, b in zip(point, sample)))
            distances.append((d, self._labels[i]))
        distances.sort(key=lambda x: x[0])
        k = min(self.k, len(distances))
        top_labels = [d[1] for d in distances[:k]]
        counts = Counter(top_labels)
        return {label: count / k for label, count in counts.items()}


# ─── P314: 线性回归 ──────────────────────────
class LinearRegression:
    """线性回归(最小二乘法)"""

    def __init__(self):
        self.slope: float = 0.0
        self.intercept: float = 0.0
        self.r_squared: float = 0.0

    def fit(self, x: list[float], y: list[float]) -> dict:
        n = len(x)
        if n < 2 or n != len(y):
            return {"status": "error", "error": "数据不足或不匹配"}
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        den = sum((xi - mean_x) ** 2 for xi in x)
        if den == 0:
            return {"status": "error", "error": "x方差为0"}
        self.slope = num / den
        self.intercept = mean_y - self.slope * mean_x
        # R²
        ss_tot = sum((yi - mean_y) ** 2 for yi in y)
        ss_res = sum((yi - (self.slope * xi + self.intercept)) ** 2
                     for xi, yi in zip(x, y))
        self.r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        return {
            "slope": round(self.slope, 6),
            "intercept": round(self.intercept, 6),
            "r_squared": round(self.r_squared, 6),
        }

    def predict(self, x: float) -> float:
        return self.slope * x + self.intercept


# ─── P315: 逻辑回归 ──────────────────────────
class LogisticRegression:
    """逻辑回归(梯度下降)"""

    def __init__(self, lr: float = 0.01, epochs: int = 1000):
        self.lr = lr
        self.epochs = epochs
        self.weights: list[float] = []
        self.bias: float = 0.0

    @staticmethod
    def _sigmoid(z: float) -> float:
        if z >= 0:
            return 1 / (1 + math.exp(-z))
        exp_z = math.exp(z)
        return exp_z / (1 + exp_z)

    def fit(self, X: list[list[float]], y: list[int]) -> dict:
        n = len(X)
        if n == 0:
            return {"status": "error", "error": "无数据"}
        d = len(X[0])
        self.weights = [0.0] * d
        self.bias = 0.0
        for _ in range(self.epochs):
            for i in range(n):
                z = sum(self.weights[j] * X[i][j] for j in range(d)) + self.bias
                pred = self._sigmoid(z)
                err = pred - y[i]
                for j in range(d):
                    self.weights[j] -= self.lr * err * X[i][j]
                self.bias -= self.lr * err
        return {"weights": [round(w, 6) for w in self.weights],
                "bias": round(self.bias, 6)}

    def predict(self, x: list[float]) -> int:
        z = sum(w * xi for w, xi in zip(self.weights, x)) + self.bias
        return 1 if self._sigmoid(z) >= 0.5 else 0

    def predict_proba(self, x: list[float]) -> float:
        z = sum(w * xi for w, xi in zip(self.weights, x)) + self.bias
        return self._sigmoid(z)


# ─── P316: 决策树 ──────────────────────────
class DecisionTreeNode:
    __slots__ = ("feature", "threshold", "left", "right", "label")

    def __init__(self):
        self.feature: int = -1
        self.threshold: float = 0.0
        self.left: Optional["DecisionTreeNode"] = None
        self.right: Optional["DecisionTreeNode"] = None
        self.label: str = ""


class DecisionTree:
    """简易决策树(CART)"""

    def __init__(self, max_depth: int = 5, min_samples: int = 2):
        self.max_depth = max_depth
        self.min_samples = min_samples
        self.root: Optional[DecisionTreeNode] = None

    def fit(self, X: list[list[float]], y: list[str]) -> None:
        self.root = self._build(X, y, 0)

    def _build(self, X: list[list[float]], y: list[str], depth: int) -> DecisionTreeNode:
        node = DecisionTreeNode()
        if depth >= self.max_depth or len(X) < self.min_samples or len(set(y)) == 1:
            node.label = Counter(y).most_common(1)[0][0]
            return node
        best_feat, best_thresh = self._best_split(X, y)
        if best_feat < 0:
            node.label = Counter(y).most_common(1)[0][0]
            return node
        node.feature = best_feat
        node.threshold = best_thresh
        left_X, left_y, right_X, right_y = [], [], [], []
        for i in range(len(X)):
            if X[i][best_feat] <= best_thresh:
                left_X.append(X[i])
                left_y.append(y[i])
            else:
                right_X.append(X[i])
                right_y.append(y[i])
        node.left = self._build(left_X, left_y, depth + 1)
        node.right = self._build(right_X, right_y, depth + 1)
        return node

    def _best_split(self, X: list[list[float]], y: list[str]) -> tuple[int, float]:
        best_gini = 1.0
        best_feat = -1
        best_thresh = 0.0
        for feat in range(len(X[0])):
            thresholds = sorted(set(row[feat] for row in X))
            for t in thresholds:
                left = [y[i] for i in range(len(X)) if X[i][feat] <= t]
                right = [y[i] for i in range(len(X)) if X[i][feat] > t]
                if not left or not right:
                    continue
                gini = (len(left) * self._gini(left) + len(right) * self._gini(right)) / len(X)
                if gini < best_gini:
                    best_gini = gini
                    best_feat = feat
                    best_thresh = t
        return best_feat, best_thresh

    @staticmethod
    def _gini(labels: list[str]) -> float:
        n = len(labels)
        if n == 0:
            return 0
        counts = Counter(labels)
        return 1 - sum((c / n) ** 2 for c in counts.values())

    def predict(self, x: list[float]) -> str:
        node = self.root
        while node and node.label == "":
            if x[node.feature] <= node.threshold:
                node = node.left
            else:
                node = node.right
        return node.label if node else ""


# ─── P317: 朴素贝叶斯 ──────────────────────────
class NaiveBayes:
    """高斯朴素贝叶斯"""

    def __init__(self):
        self._classes: list[str] = []
        self._mean: dict[str, list[float]] = {}
        self._var: dict[str, list[float]] = {}
        self._prior: dict[str, float] = {}

    def fit(self, X: list[list[float]], y: list[str]) -> dict:
        self._classes = list(set(y))
        n = len(X)
        for cls in self._classes:
            indices = [i for i in range(n) if y[i] == cls]
            cls_X = [X[i] for i in indices]
            self._mean[cls] = [sum(col) / len(col) for col in zip(*cls_X)]
            self._var[cls] = [sum((x - m) ** 2 for x in col) / len(col)
                              for col, m in zip(zip(*cls_X), self._mean[cls])]
            self._prior[cls] = len(indices) / n
        return {"classes": self._classes, "priors": self._prior}

    def predict(self, x: list[float]) -> str:
        best_cls = ""
        best_prob = float("-inf")
        for cls in self._classes:
            prob = math.log(self._prior[cls])
            for i in range(len(x)):
                mean = self._mean[cls][i]
                var = self._var[cls][i] + 1e-9
                prob += -0.5 * math.log(2 * math.pi * var) - (x[i] - mean) ** 2 / (2 * var)
            if prob > best_prob:
                best_prob = prob
                best_cls = cls
        return best_cls


# ─── P318: 数据集拆分器 ──────────────────────────
class DatasetSplitter:
    """数据集拆分器"""

    @staticmethod
    def train_test_split(X: list, y: list, test_size: float = 0.2,
                         random_state: int | None = None) -> dict:
        n = len(X)
        if n != len(y):
            return {"status": "error", "error": "X和y长度不匹配"}
        if random_state is not None:
            random.seed(random_state)
        indices = list(range(n))
        random.shuffle(indices)
        split = int(n * (1 - test_size))
        train_idx = indices[:split]
        test_idx = indices[split:]
        return {
            "X_train": [X[i] for i in train_idx],
            "X_test": [X[i] for i in test_idx],
            "y_train": [y[i] for i in train_idx],
            "y_test": [y[i] for i in test_idx],
            "train_size": len(train_idx),
            "test_size": len(test_idx),
        }

    @staticmethod
    def k_fold(n: int, k: int, random_state: int | None = None) -> list[dict]:
        if random_state is not None:
            random.seed(random_state)
        indices = list(range(n))
        random.shuffle(indices)
        fold_size = n // k
        folds = []
        for i in range(k):
            start = i * fold_size
            end = (i + 1) * fold_size if i < k - 1 else n
            test_idx = indices[start:end]
            train_idx = indices[:start] + indices[end:]
            folds.append({"train": train_idx, "test": test_idx})
        return folds


# ─── P319: 模型评估器 ──────────────────────────
class ModelEvaluator:
    """模型评估器"""

    @staticmethod
    def accuracy(y_true: list, y_pred: list) -> float:
        if not y_true:
            return 0.0
        correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
        return correct / len(y_true)

    @staticmethod
    def precision_recall_f1(y_true: list, y_pred: list, positive: str = "1") -> dict:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == positive and p == positive)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != positive and p == positive)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == positive and p != positive)
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        return {"precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "tp": tp, "fp": fp, "fn": fn}

    @staticmethod
    def confusion_matrix(y_true: list, y_pred: list) -> dict:
        labels = sorted(set(y_true) | set(y_pred))
        matrix = {l1: {l2: 0 for l2 in labels} for l1 in labels}
        for t, p in zip(y_true, y_pred):
            matrix[t][p] += 1
        return matrix

    @staticmethod
    def mse(y_true: list[float], y_pred: list[float]) -> float:
        if not y_true:
            return 0.0
        return sum((t - p) ** 2 for t, p in zip(y_true, y_pred)) / len(y_true)


_evaluator = ModelEvaluator()


# ─── P320: 特征缩放器 ──────────────────────────
class FeatureScaler:
    """特征缩放器(标准化/归一化)"""

    def __init__(self):
        self._mean: list[float] = []
        self._std: list[float] = []
        self._min: list[float] = []
        self._max: list[float] = []

    def fit_standard(self, X: list[list[float]]) -> None:
        if not X:
            return
        n_cols = len(X[0])
        self._mean = [sum(row[i] for row in X) / len(X) for i in range(n_cols)]
        self._std = [math.sqrt(sum((row[i] - self._mean[i]) ** 2 for row in X) / len(X))
                     for i in range(n_cols)]

    def transform_standard(self, X: list[list[float]]) -> list[list[float]]:
        return [[(row[i] - self._mean[i]) / (self._std[i] + 1e-9)
                 for i in range(len(row))] for row in X]

    def fit_minmax(self, X: list[list[float]]) -> None:
        if not X:
            return
        n_cols = len(X[0])
        self._min = [min(row[i] for row in X) for i in range(n_cols)]
        self._max = [max(row[i] for row in X) for i in range(n_cols)]

    def transform_minmax(self, X: list[list[float]]) -> list[list[float]]:
        return [[(row[i] - self._min[i]) / (self._max[i] - self._min[i] + 1e-9)
                 for i in range(len(row))] for row in X]


_scaler = FeatureScaler()
