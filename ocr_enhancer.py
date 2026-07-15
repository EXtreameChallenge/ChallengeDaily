"""
P9-1：OCR 增强 + 图像特征提取

设计思路：
- 优先尝试 PaddleOCR（若已安装），对截图中的文字区域做识别
- 若 PaddleOCR 不可用，回退到 PIL 提取图像统计特征（主色调、亮度、对比度）
  作为辅助信号，让 AI 知道"这是代码界面（深色高对比）"还是"文档（浅色低对比）"
- 结果注入 AI prompt，辅助分类
- 所有操作失败安全，绝不影响主采集流程
"""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# OCR 调用结果缓存（按文件路径），避免同一截图重复 OCR
_OCR_CACHE: dict[str, str] = {}
_OCR_CACHE_MAX = 20

# PaddleOCR 实例懒加载
_paddle_ocr = None
_paddle_checked = False


def _get_paddle_ocr():
    """懒加载 PaddleOCR 实例（若可用）"""
    global _paddle_ocr, _paddle_checked
    if _paddle_checked:
        return _paddle_ocr
    _paddle_checked = True
    try:
        from paddleocr import PaddleOCR  # type: ignore
        _paddle_ocr = PaddleOCR(use_angle_cls=False, lang="ch", show_log=False)
        logger.info("PaddleOCR 已加载，OCR 增强启用")
    except ImportError:
        logger.info("PaddleOCR 未安装，OCR 增强使用 PIL 图像特征回退")
    except Exception as e:
        logger.warning(f"PaddleOCR 加载失败: {e}")
    return _paddle_ocr


def _extract_image_stats(image_path: str) -> str:
    """用 PIL 提取图像统计特征作为辅助信号

    返回人类可读的描述，例如：
      "深色高对比界面（可能是 IDE/代码编辑器）"
      "浅色低对比界面（可能是文档/网页）"
    """
    try:
        from PIL import Image  # type: ignore
        import numpy as np  # type: ignore
        img = Image.open(image_path).convert("RGB")
        # 缩小到 64x64 加速统计
        img_small = img.resize((64, 64))
        arr = np.array(img_small)
        mean_brightness = float(arr.mean())
        std_contrast = float(arr.std())
        # 判断主色调
        r, g, b = arr[:, :, 0].mean(), arr[:, :, 1].mean(), arr[:, :, 2].mean()
        # 简单分类
        if mean_brightness < 60:
            theme = "深色界面（可能是 IDE/代码编辑器/终端）"
        elif mean_brightness > 200:
            theme = "浅色界面（可能是文档/网页/办公软件）"
        elif std_contrast > 70:
            theme = "高对比界面（可能是代码或图表）"
        else:
            theme = "中等亮度界面（可能是普通应用）"
        # 颜色偏移提示
        if b > r + 20 and b > g + 10:
            color_hint = "，偏蓝色调"
        elif r > b + 20 and r > g + 10:
            color_hint = "，偏红色调"
        elif g > r + 10 and g > b + 10:
            color_hint = "，偏绿色调"
        else:
            color_hint = ""
        return f"{theme}{color_hint}，平均亮度 {mean_brightness:.0f}/255，对比度 {std_contrast:.0f}"
    except ImportError:
        return "PIL 未安装，无法提取图像特征"
    except Exception as e:
        return f"图像特征提取失败: {e}"


def extract_text_from_image(image_path: str) -> str:
    """对截图做 OCR 识别 + 图像特征提取

    返回拼接文本，供 AI prompt 注入：
      - 若 PaddleOCR 可用：返回识别到的关键文字（前 500 字符）
      - 始终附加图像统计特征作为辅助信号
    """
    if not os.path.exists(image_path):
        return ""

    # 缓存命中
    if image_path in _OCR_CACHE:
        return _OCR_CACHE[image_path]

    parts: list[str] = []

    # 1. 尝试 PaddleOCR
    paddle = _get_paddle_ocr()
    if paddle is not None:
        try:
            result = paddle.ocr(image_path, cls=False)
            texts: list[str] = []
            if result and result[0]:
                for line in result[0]:
                    if line and len(line) >= 2:
                        txt = line[1][0] if isinstance(line[1], (list, tuple)) and len(line[1]) >= 1 else ""
                        if txt:
                            texts.append(str(txt))
            if texts:
                # 拼接前 500 字符，避免 prompt 过长
                joined = " ".join(texts)[:500]
                parts.append(f"[OCR 识别文字]\n{joined}")
        except Exception as e:
            logger.debug(f"PaddleOCR 识别失败: {e}")

    # 2. 始终附加图像统计特征
    stats = _extract_image_stats(image_path)
    if stats:
        parts.append(f"[图像特征]\n{stats}")

    result_text = "\n".join(parts)

    # 写入缓存（LRU）
    if len(_OCR_CACHE) >= _OCR_CACHE_MAX:
        # 删除最早的一个
        try:
            oldest_key = next(iter(_OCR_CACHE))
            del _OCR_CACHE[oldest_key]
        except StopIteration:
            pass
    _OCR_CACHE[image_path] = result_text

    return result_text


def clear_cache() -> None:
    """清空 OCR 缓存"""
    _OCR_CACHE.clear()
