"""P331-P340: 计算机视觉路由"""
from flask import Blueprint, request, jsonify
from cv_engine import (
    _image_meta, ColorHistogram, EdgeDetector, ColorClusterer,
    ImageResizer, OCRExtractor, ImageClassifier, FaceDetector,
    BarcodeScanner, ImageHasher,
)

bp = Blueprint("cv", __name__, url_prefix="/api/cv")


@bp.route("/metadata", methods=["POST"])
def cv_set_meta():
    data = request.get_json(silent=True) or {}
    _image_meta.set(
        data.get("image_id", ""),
        int(data.get("width", 0)),
        int(data.get("height", 0)),
        data.get("format", "PNG"),
        source=data.get("source", ""),
    )
    return jsonify({"status": "ok"})


@bp.route("/metadata/<image_id>", methods=["GET"])
def cv_get_meta(image_id: str):
    return jsonify(_image_meta.get(image_id) or {"error": "未找到"})


@bp.route("/histogram", methods=["POST"])
def cv_histogram():
    data = request.get_json(silent=True) or {}
    pixels = [tuple(p) for p in data.get("pixels", [])]
    bins = int(data.get("bins", 8))
    return jsonify(ColorHistogram.analyze(pixels, bins))


@bp.route("/edge-detect", methods=["POST"])
def cv_edge():
    data = request.get_json(silent=True) or {}
    gray = data.get("gray_image", [])
    return jsonify(EdgeDetector.detect(gray))


@bp.route("/color-cluster", methods=["POST"])
def cv_cluster():
    data = request.get_json(silent=True) or {}
    pixels = [tuple(p) for p in data.get("pixels", [])]
    k = int(data.get("k", 5))
    return jsonify(ColorClusterer.cluster(pixels, k))


@bp.route("/resize", methods=["POST"])
def cv_resize():
    data = request.get_json(silent=True) or {}
    return jsonify(ImageResizer.calculate_size(
        int(data.get("orig_w", 0)),
        int(data.get("orig_h", 0)),
        data.get("target_w"),
        data.get("target_h"),
        data.get("scale"),
    ))


@bp.route("/ocr", methods=["POST"])
def cv_ocr():
    data = request.get_json(silent=True) or {}
    return jsonify(OCRExtractor.extract(data.get("image_id", ""), data.get("doc_type", "document")))


@bp.route("/ocr/types", methods=["GET"])
def cv_ocr_types():
    return jsonify({"types": OCRExtractor.list_doc_types()})


@bp.route("/classify", methods=["POST"])
def cv_classify():
    data = request.get_json(silent=True) or {}
    pixels = [tuple(p) for p in data.get("pixels", [])]
    return jsonify(ImageClassifier.classify(pixels))


@bp.route("/face-detect", methods=["POST"])
def cv_face():
    data = request.get_json(silent=True) or {}
    return jsonify(FaceDetector.detect(int(data.get("width", 640)), int(data.get("height", 480))))


@bp.route("/barcode", methods=["POST"])
def cv_barcode():
    data = request.get_json(silent=True) or {}
    return jsonify(BarcodeScanner.scan(data.get("image_id", "")))


@bp.route("/hash", methods=["POST"])
def cv_hash():
    data = request.get_json(silent=True) or {}
    image = data.get("image", [])
    return jsonify({"hash": ImageHasher.average_hash(image)})


@bp.route("/hash/compare", methods=["POST"])
def cv_hash_compare():
    data = request.get_json(silent=True) or {}
    h1 = data.get("hash1", "")
    h2 = data.get("hash2", "")
    return jsonify({"distance": ImageHasher.hamming_distance(h1, h2),
                    "similarity": round(ImageHasher.similarity(h1, h2), 4)})
