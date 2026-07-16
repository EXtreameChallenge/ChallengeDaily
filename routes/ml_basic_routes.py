"""P311-P320: 机器学习基础路由"""
from flask import Blueprint, request, jsonify
from ml_basic import (
    _feature_vec, KMeans, KNNClassifier, LinearRegression, LogisticRegression,
    DecisionTree, NaiveBayes, DatasetSplitter, ModelEvaluator, _scaler,
)

bp = Blueprint("ml_basic", __name__, url_prefix="/api/ml")


@bp.route("/features/sample", methods=["POST"])
def feature_add():
    data = request.get_json(silent=True) or {}
    idx = _feature_vec.add_sample(data.get("features", {}), data.get("label", ""))
    return jsonify({"index": idx})


@bp.route("/features/stats", methods=["GET"])
def feature_stats():
    return jsonify(_feature_vec.get_stats())


@bp.route("/kmeans", methods=["POST"])
def kmeans():
    data = request.get_json(silent=True) or {}
    X = data.get("data", [])
    k = data.get("k", 3)
    model = KMeans(k=k)
    return jsonify(model.fit(X))


@bp.route("/knn", methods=["POST"])
def knn():
    data = request.get_json(silent=True) or {}
    X = data.get("X", [])
    y = data.get("y", [])
    point = data.get("point", [])
    k = data.get("k", 3)
    model = KNNClassifier(k=k)
    model.fit(X, y)
    return jsonify({"prediction": model.predict(point),
                    "proba": model.predict_proba(point)})


@bp.route("/linear-regression", methods=["POST"])
def linreg():
    data = request.get_json(silent=True) or {}
    x = data.get("x", [])
    y = data.get("y", [])
    model = LinearRegression()
    return jsonify(model.fit(x, y))


@bp.route("/logistic-regression", methods=["POST"])
def logreg():
    data = request.get_json(silent=True) or {}
    X = data.get("X", [])
    y = data.get("y", [])
    lr = data.get("lr", 0.01)
    epochs = data.get("epochs", 1000)
    model = LogisticRegression(lr=lr, epochs=epochs)
    return jsonify(model.fit(X, y))


@bp.route("/decision-tree", methods=["POST"])
def dtree():
    data = request.get_json(silent=True) or {}
    X = data.get("X", [])
    y = data.get("y", [])
    point = data.get("point", [])
    model = DecisionTree()
    model.fit(X, y)
    return jsonify({"prediction": model.predict(point)})


@bp.route("/naive-bayes", methods=["POST"])
def nb():
    data = request.get_json(silent=True) or {}
    X = data.get("X", [])
    y = data.get("y", [])
    point = data.get("point", [])
    model = NaiveBayes()
    return jsonify(model.fit(X, y) | {"prediction": model.predict(point)})


@bp.route("/split", methods=["POST"])
def split():
    data = request.get_json(silent=True) or {}
    return jsonify(DatasetSplitter.train_test_split(
        data.get("X", []), data.get("y", []),
        data.get("test_size", 0.2), data.get("random_state")))


@bp.route("/evaluate", methods=["POST"])
def evaluate():
    data = request.get_json(silent=True) or {}
    y_true = data.get("y_true", [])
    y_pred = data.get("y_pred", [])
    return jsonify({
        "accuracy": ModelEvaluator.accuracy(y_true, y_pred),
        "confusion_matrix": ModelEvaluator.confusion_matrix(y_true, y_pred),
        "prf1": ModelEvaluator.precision_recall_f1(y_true, y_pred, data.get("positive", "1")),
    })


@bp.route("/scaler", methods=["POST"])
def scale():
    data = request.get_json(silent=True) or {}
    X = data.get("X", [])
    method = data.get("method", "standard")
    if method == "minmax":
        _scaler.fit_minmax(X)
        return jsonify({"scaled": _scaler.transform_minmax(X)})
    else:
        _scaler.fit_standard(X)
        return jsonify({"scaled": _scaler.transform_standard(X)})
