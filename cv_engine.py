"""
P331-P340: 计算机视觉(CV)基础系统
- P331: 图像元数据管理
- P332: 颜色直方图分析
- P333: 边缘检测(简化)
- P334: 颜色聚类
- P335: 图像尺寸调整算法
- P336: OCR文本提取(模拟)
- P337: 图像分类(基于颜色)
- P338: 人脸检测(模拟)
- P339: 条形码/二维码识别(模拟)
- P340: 图像哈希(感知哈希)
"""
from __future__ import annotations

import hashlib
import logging
import math
import threading
from collections import Counter, deque
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P331: 图像元数据管理 ──────────────────────────
class ImageMetadata:
    """图像元数据管理"""

    def __init__(self):
        self._metadata: dict[str, dict] = {}
        self._lock = threading.Lock()

    def set(self, image_id: str, width: int, height: int,
            format: str = "PNG", **extra) -> None:
        with self._lock:
            self._metadata[image_id] = {
                "width": width,
                "height": height,
                "format": format,
                "aspect_ratio": round(width / height, 3) if height > 0 else 0,
                "pixels": width * height,
                **extra,
            }

    def get(self, image_id: str) -> dict | None:
        with self._lock:
            return self._metadata.get(image_id)

    def list_all(self) -> list[dict]:
        with self._lock:
            return [{"image_id": k, **v} for k, v in self._metadata.items()]

    def delete(self, image_id: str) -> bool:
        with self._lock:
            return self._metadata.pop(image_id, None) is not None


_image_meta = ImageMetadata()


# ─── P332: 颜色直方图分析 ──────────────────────────
class ColorHistogram:
    """颜色直方图分析"""

    @staticmethod
    def analyze(pixels: list[tuple[int, int, int]], bins: int = 8) -> dict:
        if not pixels:
            return {"r": [], "g": [], "b": [], "bins": bins}
        r_hist = [0] * bins
        g_hist = [0] * bins
        b_hist = [0] * bins
        for r, g, b in pixels:
            r_hist[min(r * bins // 256, bins - 1)] += 1
            g_hist[min(g * bins // 256, bins - 1)] += 1
            b_hist[min(b * bins // 256, bins - 1)] += 1
        total = len(pixels)
        return {
            "r": [h / total for h in r_hist],
            "g": [h / total for h in g_hist],
            "b": [h / total for h in b_hist],
            "bins": bins,
            "dominant_colors": ColorHistogram._dominant(pixels, 3),
        }

    @staticmethod
    def _dominant(pixels: list[tuple[int, int, int]], k: int = 3) -> list[dict]:
        # 简化:量化到16级
        quantized = [(r // 16 * 16, g // 16 * 16, b // 16 * 16) for r, g, b in pixels]
        counter = Counter(quantized)
        return [{"rgb": c, "count": cnt} for c, cnt in counter.most_common(k)]


# ─── P333: 边缘检测 ──────────────────────────
class EdgeDetector:
    """简化边缘检测(Sobel)"""

    SOBEL_X = [[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]]
    SOBEL_Y = [[-1, -2, -1], [0, 0, 0], [1, 2, 1]]

    @classmethod
    def detect(cls, gray_image: list[list[float]]) -> dict:
        rows = len(gray_image)
        if rows < 3:
            return {"edges": [], "threshold": 0.5}
        cols = len(gray_image[0])
        edges = [[0.0] * cols for _ in range(rows)]
        for i in range(1, rows - 1):
            for j in range(1, cols - 1):
                gx = sum(cls.SOBEL_X[ki][kj] * gray_image[i + ki - 1][j + kj - 1]
                         for ki in range(3) for kj in range(3))
                gy = sum(cls.SOBEL_Y[ki][kj] * gray_image[i + ki - 1][j + kj - 1]
                         for ki in range(3) for kj in range(3))
                edges[i][j] = math.sqrt(gx * gx + gy * gy)
        # 归一化
        max_val = max(max(row) for row in edges) or 1
        edges = [[v / max_val for v in row] for row in edges]
        return {"edges": edges, "threshold": 0.5}


# ─── P334: 颜色聚类 ──────────────────────────
class ColorClusterer:
    """颜色聚类(K-Means)"""

    @staticmethod
    def cluster(pixels: list[tuple[int, int, int]], k: int = 5) -> dict:
        if not pixels or k <= 0:
            return {"clusters": [], "centroids": []}
        # 简化K-Means
        import random
        random.seed(42)
        centroids = random.sample(pixels, min(k, len(pixels)))
        for _ in range(10):
            assignments = []
            for p in pixels:
                dists = [math.sqrt(sum((p[i] - c[i]) ** 2 for i in range(3)))
                         for c in centroids]
                assignments.append(dists.index(min(dists)))
            # 更新中心
            new_centroids = []
            for c_idx in range(len(centroids)):
                cluster_pixels = [pixels[i] for i in range(len(pixels)) if assignments[i] == c_idx]
                if cluster_pixels:
                    new_centroids.append(tuple(
                        sum(p[d] for p in cluster_pixels) // len(cluster_pixels)
                        for d in range(3)
                    ))
                else:
                    new_centroids.append(centroids[c_idx])
            if new_centroids == centroids:
                break
            centroids = new_centroids
        cluster_counts = Counter(assignments)
        return {
            "centroids": [{"rgb": c, "count": cluster_counts[i]}
                          for i, c in enumerate(centroids)],
            "k": k,
        }


# ─── P335: 图像尺寸调整 ──────────────────────────
class ImageResizer:
    """图像尺寸调整算法(最近邻/双线性)"""

    @staticmethod
    def nearest_neighbor(image: list[list[tuple[int, int, int]]],
                         new_w: int, new_h: int) -> list[list[tuple[int, int, int]]]:
        if not image or new_w <= 0 or new_h <= 0:
            return []
        old_h = len(image)
        old_w = len(image[0])
        result = [[(0, 0, 0)] * new_w for _ in range(new_h)]
        x_ratio = old_w / new_w
        y_ratio = old_h / new_h
        for i in range(new_h):
            for j in range(new_w):
                src_x = min(int(j * x_ratio), old_w - 1)
                src_y = min(int(i * y_ratio), old_h - 1)
                result[i][j] = image[src_y][src_x]
        return result

    @staticmethod
    def calculate_size(orig_w: int, orig_h: int,
                       target_w: int | None = None,
                       target_h: int | None = None,
                       scale: float | None = None) -> dict:
        if scale:
            return {"width": int(orig_w * scale), "height": int(orig_h * scale),
                    "method": "scale"}
        if target_w and target_h:
            return {"width": target_w, "height": target_h, "method": "fixed"}
        if target_w:
            ratio = target_w / orig_w
            return {"width": target_w, "height": int(orig_h * ratio), "method": "width"}
        if target_h:
            ratio = target_h / orig_h
            return {"width": int(orig_w * ratio), "height": target_h, "method": "height"}
        return {"width": orig_w, "height": orig_h, "method": "original"}


# ─── P336: OCR文本提取 ──────────────────────────
class OCRExtractor:
    """OCR文本提取(模拟,实际需要Tesseract等)"""

    # 模拟OCR结果模板
    TEMPLATES = {
        "invoice": ["发票号码", "日期", "金额", "购买方", "销售方"],
        "receipt": ["商户名称", "交易时间", "金额", "支付方式"],
        "id_card": ["姓名", "性别", "民族", "出生日期", "住址", "身份证号"],
        "document": ["标题", "正文", "页码", "作者"],
    }

    @classmethod
    def extract(cls, image_id: str, doc_type: str = "document") -> dict:
        fields = cls.TEMPLATES.get(doc_type, cls.TEMPLATES["document"])
        return {
            "image_id": image_id,
            "doc_type": doc_type,
            "fields": {f: f"[模拟_{f}]" for f in fields},
            "confidence": 0.85,
            "language": "zh-CN",
            "note": "模拟OCR结果,需接入Tesseract或云OCR服务",
        }

    @classmethod
    def list_doc_types(cls) -> list[str]:
        return list(cls.TEMPLATES.keys())


# ─── P337: 图像分类 ──────────────────────────
class ImageClassifier:
    """图像分类(基于颜色特征)"""

    CATEGORIES = {
        "outdoor": {"green": 0.3, "blue": 0.2, "brown": 0.1},
        "indoor": {"gray": 0.3, "brown": 0.2, "white": 0.2},
        "document": {"white": 0.6, "black": 0.3},
        "portrait": {"skin_tone": 0.4, "background": 0.3},
    }

    @classmethod
    def classify(cls, pixels: list[tuple[int, int, int]]) -> dict:
        if not pixels:
            return {"category": "unknown", "scores": {}}
        # 统计颜色比例
        color_ratios = Counter()
        for r, g, b in pixels:
            if g > r and g > b:
                color_ratios["green"] += 1
            elif b > r and b > g:
                color_ratios["blue"] += 1
            elif r > 200 and g > 200 and b > 200:
                color_ratios["white"] += 1
            elif r < 60 and g < 60 and b < 60:
                color_ratios["black"] += 1
            elif r > 150 and 100 < g < 200 and b < 150:
                color_ratios["skin_tone"] += 1
            elif abs(r - g) < 30 and abs(g - b) < 30:
                color_ratios["gray"] += 1
            elif r > g and r > b:
                color_ratios["brown"] += 1
        total = len(pixels)
        ratios = {k: v / total for k, v in color_ratios.items()}
        # 计算每类得分
        scores = {}
        for cat, weights in cls.CATEGORIES.items():
            score = sum(ratios.get(color, 0) * weight for color, weight in weights.items())
            scores[cat] = round(score, 3)
        best_cat = max(scores, key=scores.get) if scores else "unknown"
        return {"category": best_cat, "scores": scores, "color_ratios": ratios}


# ─── P338: 人脸检测 ──────────────────────────
class FaceDetector:
    """人脸检测(模拟)"""

    @staticmethod
    def detect(image_width: int, image_height: int) -> dict:
        # 模拟检测结果
        import random
        random.seed(42)
        face_count = random.randint(0, 3)
        faces = []
        for i in range(face_count):
            w = min(100, image_width // 4)
            h = min(120, image_height // 4)
            x = random.randint(0, max(0, image_width - w))
            y = random.randint(0, max(0, image_height - h))
            faces.append({
                "bbox": {"x": x, "y": y, "width": w, "height": h},
                "confidence": round(random.uniform(0.7, 0.99), 3),
            })
        return {
            "faces": faces,
            "count": len(faces),
            "image_size": {"width": image_width, "height": image_height},
            "note": "模拟检测结果,需接入OpenCV或MTCNN",
        }


# ─── P339: 条形码/二维码识别 ──────────────────────────
class BarcodeScanner:
    """条形码/二维码识别(模拟)"""

    @staticmethod
    def scan(image_id: str) -> dict:
        import random
        random.seed(hash(image_id) % 1000)
        code_type = random.choice(["QR_CODE", "EAN_13", "CODE_128", "UPC_A"])
        if code_type == "QR_CODE":
            data = f"https://example.com/{image_id}"
        elif code_type == "EAN_13":
            data = "".join(str(random.randint(0, 9)) for _ in range(13))
        else:
            data = "".join(str(random.randint(0, 9)) for _ in range(12))
        return {
            "image_id": image_id,
            "type": code_type,
            "data": data,
            "confidence": round(random.uniform(0.85, 0.99), 3),
            "note": "模拟扫描结果",
        }


# ─── P340: 图像哈希 ──────────────────────────
class ImageHasher:
    """图像感知哈希(pHash)"""

    @staticmethod
    def average_hash(image: list[list[int]], hash_size: int = 8) -> str:
        if not image:
            return ""
        # 缩放到hash_size x hash_size
        resized = []
        h_step = len(image) / hash_size
        w_step = len(image[0]) / hash_size if image[0] else 1
        for i in range(hash_size):
            row = []
            for j in range(hash_size):
                y = int(i * h_step)
                x = int(j * w_step)
                if y < len(image) and x < len(image[0]):
                    row.append(image[y][x])
                else:
                    row.append(0)
            resized.append(row)
        # 计算均值
        flat = [v for row in resized for v in row]
        avg = sum(flat) / len(flat) if flat else 0
        # 生成哈希
        bits = "1" if flat[0] >= avg else "0"
        for v in flat[1:]:
            bits += "1" if v >= avg else "0"
        # 转十六进制
        hex_hash = ""
        for i in range(0, len(bits), 4):
            hex_hash += hex(int(bits[i:i+4], 2))[2:]
        return hex_hash

    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        if len(hash1) != len(hash2):
            return max(len(hash1), len(hash2))
        return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))

    @staticmethod
    def similarity(hash1: str, hash2: str) -> float:
        if not hash1 or not hash2:
            return 0.0
        dist = ImageHasher.hamming_distance(hash1, hash2)
        max_len = max(len(hash1), len(hash2))
        return 1 - dist / max_len if max_len > 0 else 1.0
